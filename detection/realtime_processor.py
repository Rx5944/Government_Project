import os
import logging
import ee
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from lands.models import LandParcel, EncroachmentAlert, District

logger = logging.getLogger('glrms.monitoring')

_GEE_INITIALIZED = False

def initialize_gee():
    """Initializes Google Earth Engine with Service Account."""
    global _GEE_INITIALIZED
    if _GEE_INITIALIZED:
        return True
    
    try:
        key_path = getattr(settings, 'GEE_KEY_PATH', 'gee_key.json')
        if os.path.exists(key_path):
            import json
            with open(key_path, 'r') as f:
                key_data = json.load(f)
            credentials = ee.ServiceAccountCredentials(key_data['client_email'], key_path)
            ee.Initialize(credentials)
            logger.info(f"GEE Initialized via Service Account: {key_data['client_email']}")
            _GEE_INITIALIZED = True
            return True
        else:
            logger.error(f"GEE Key not found at {key_path}")
            return False
    except Exception as e:
        logger.error(f"GEE Initialization failed: {e}")
        return False

def mask_s2_clouds(image):
    """Masks clouds in Sentinel-2 image using QA60 band."""
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
           qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000)

def compute_ndvi(image):
    """Computes NDVI for a Sentinel-2 image."""
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')

def run_real_time_scan():
    """Main function to trigger GEE-based real-time land monitoring."""
    if not initialize_gee():
        return {"status": "error", "message": "GEE Authentication Failed"}

    # 1. Fetch Government Land Boundaries
    parcels = LandParcel.objects.all()
    if not parcels.exists():
        return {"status": "warning", "message": "No land parcels in database"}

    # Combine all parcel boundaries into a single ee.FeatureCollection
    features = []
    for parcel in parcels:
        if parcel.latitude and parcel.longitude:
            # For simplicity, if we don't have GeoJSON polygons, we use small buffers around points
            # In a real system, we prefer parcel.boundary_geojson
            if parcel.boundary_geojson:
                geom = ee.Geometry(parcel.boundary_geojson)
            else:
                geom = ee.Geometry.Point([parcel.longitude, parcel.latitude]).buffer(100).bounds()
            features.append(ee.Feature(geom, {'id': parcel.id, 'survey': parcel.survey_number}))

    if not features:
        return {"status": "error", "message": "No valid geometries found"}

    gov_land_fc = ee.FeatureCollection(features)
    roi = gov_land_fc.geometry().buffer(1000).bounds() # Scan area + 1km buffer

    # 2. Set Time Windows
    now = datetime.now()
    t1_end = now
    t1_start = now - timedelta(days=5)
    t2_end = now - timedelta(days=10)
    t2_start = now - timedelta(days=15)

    # 3. Fetch Satellite Data (Sentinel-2 SR)
    def fetch_collection(start, end):
        return (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(roi)
                .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                .map(mask_s2_clouds))

    coll_current = fetch_collection(t1_start, t1_end)
    coll_previous = fetch_collection(t2_start, t2_end)

    if coll_current.size().getInfo() == 0 or coll_previous.size().getInfo() == 0:
        logger.warning("Satellite imagery not available for the specified windows.")
        return {"status": "warning", "message": "Satellite imagery unavailable for windows"}

    img_current = coll_current.median()
    img_previous = coll_previous.median()

    # 4. Compute NDVI Difference
    ndvi_current = compute_ndvi(img_current)
    ndvi_previous = compute_ndvi(img_previous)
    ndvi_diff = ndvi_current.subtract(ndvi_previous).rename('NDVI_DIFF')

    # 5. Detect Vegetation Loss (Threshold < -0.2)
    loss_mask = ndvi_diff.lt(-0.2) # 1 where loss occurred

    # 6. Spatial Overlay Classification (RED, GREEN, BLUE)
    # RED = Loss inside Gov Land
    # BLUE = Loss outside Gov Land (in ROI)
    # GREEN = No change inside Gov Land
    
    # Rasterize Gov Land Boundaries (1 inside, 0 outside)
    gov_raster = ee.Image().paint(gov_land_fc, 1)
    
    # Classification logic:
    # 2 (RED)   : Loss (loss_mask==1) AND Gov Land (gov_raster==1)
    # 3 (BLUE)  : Loss (loss_mask==1) AND Private (gov_raster==0)
    # 1 (GREEN) : No Loss (loss_mask==0) AND Gov Land (gov_raster==1)
    
    classified = (ee.Image(0)
                  .where(loss_mask.eq(1).And(gov_raster.eq(1)), 2)
                  .where(loss_mask.eq(1).And(gov_raster.eq(0)), 3)
                  .where(loss_mask.eq(0).And(gov_raster.eq(1)), 1)
                  .clip(roi))

    # 7. Generate and Store Output Image (risk_map.png)
    output_image_path = os.path.join(settings.BASE_DIR, 'lands', 'static', 'lands', 'risk_map.png')
    
    # Generate a thumbnail URL from ee
    # Palette: 0: Transparent, 1: Green, 2: Red, 3: Blue
    vis_params = {
        'min': 0,
        'max': 3,
        'palette': ['ffffff00', '2ecc71', 'e74c3c', '3498db']
    }
    
    try:
        url = classified.getThumbURL({
            'dimensions': 1024,
            'region': roi,
            'format': 'png',
            **vis_params
        })
        
        logger.info(f"Downloading risk map: {url}")
        img_data = requests.get(url).content
        with open(output_image_path, 'wb') as f:
            f.write(img_data)
        logger.info(f"Risk map updated at {output_image_path}")
    except Exception as e:
        logger.error(f"Failed to generate risk_map image: {e}")

    # 8. Update Database & Create Alerts
    # We use GEE to identify which parcels intersect with Red areas (loss==1 inside)
    # We do a server-side reduction to get a list of parcel IDs with loss
    
    stats = loss_mask.reduceRegions(
        collection=gov_land_fc,
        reducer=ee.Reducer.mean(),
        scale=10
    ).filter(ee.Filter.gt('mean', 0.05)).getInfo() # If >5% area is loss

    affected_survey_ids = [feat['properties']['id'] for feat in stats['features']]
    
    alerts_created = 0
    for parcel_id in affected_survey_ids:
        parcel = LandParcel.objects.get(id=parcel_id)
        if parcel.status != 'ENCROACHED':
            parcel.status = 'ENCROACHED'
            parcel.encroachment_risk_score = 0.95
            parcel.last_satellite_scan = timezone.now()
            parcel.save()
            
            # Create Alert
            EncroachmentAlert.objects.create(
                parcel=parcel,
                alert_type='CONSTRUCTION',
                detection_method='ML_AUTO',
                severity='CRITICAL',
                status='OPEN',
                description=f"REAL-TIME SATELLITE ALERT: Heavy vegetation loss detected within survey {parcel.survey_number} boundaries using Sentinel-2 NDVI temporal differencing.",
                ml_confidence_score=0.95,
                change_percentage=25.0 # Estimate
            )
            alerts_created += 1

    # Update scan time for all parcels
    LandParcel.objects.all().update(last_checked=timezone.now())

    return {
        "status": "success",
        "parcels_scanned": parcels.count(),
        "encroached_found": len(affected_survey_ids),
        "alerts_created": alerts_created,
        "scan_date": timezone.now().strftime('%Y-%m-%d %H:%M')
    }

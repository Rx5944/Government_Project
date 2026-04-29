import os
import logging
import ee
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from lands.models import LandParcel, EncroachmentAlert

logger = logging.getLogger('glrms.monitoring')

_GEE_INITIALIZED = False

def initialize_gee():
    """Initializes Google Earth Engine with the specific project ID provided."""
    global _GEE_INITIALIZED
    if _GEE_INITIALIZED:
        return True
    
    try:
        # User specified project ID
        PROJECT_ID = 'probable-scout-437605-n3'
        
        key_path = getattr(settings, 'GEE_KEY_PATH', 'gee_key.json')
        if os.path.exists(key_path):
            import json
            with open(key_path, 'r') as f:
                key_data = json.load(f)
            credentials = ee.ServiceAccountCredentials(key_data['client_email'], key_path)
            # Initialize with the project ID to ensure correct billing and resource access
            ee.Initialize(credentials, project=PROJECT_ID)
            logger.info(f"GEE Initialized via Project: {PROJECT_ID}")
            _GEE_INITIALIZED = True
            return True
        else:
            # Fallback to default auth if key not found (development)
            ee.Initialize(project=PROJECT_ID)
            _GEE_INITIALIZED = True
            return True
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

def get_ndvi(image):
    """Computes NDVI as requested: (B8 - B4) / (B8 + B4)"""
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')

def run_analysis():
    """
    Main analysis function to fetch Sentinel-2 data, compute changes,
    and update the database via the modular ML service.
    """
    if not initialize_gee():
        return {"status": "error", "message": "GEE Initialization Failed"}

    # 1. Fetch Government Land Boundaries
    parcels = LandParcel.objects.all()
    if not parcels.exists():
        return {"status": "warning", "message": "No parcels found in database"}

    features = []
    import json
    for p in parcels:
        if p.geom:
            geom_json = json.loads(p.geom.json)
            geom_ee = ee.Geometry(geom_json)
            features.append(ee.Feature(geom_ee, {'id': p.id, 'survey': p.survey_number}))

    if not features:
        return {"status": "error", "message": "No valid geometries to analyze. Ensure parcels have Polygon geometries."}

    gov_land_fc = ee.FeatureCollection(features)
    roi = gov_land_fc.geometry().bounds() # Analysis ROI bounding box

    # 2. Set Time Windows
    now = datetime.now()
    t1_end = now
    t1_start = now - timedelta(days=5)
    t2_end = now - timedelta(days=10)
    t2_start = now - timedelta(days=15)

    # 3. Fetch Satellite Data
    def get_collection(start, end):
        return (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(roi)
                .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                .map(mask_s2_clouds))

    coll_current = get_collection(t1_start, t1_end)
    coll_previous = get_collection(t2_start, t2_end)

    if coll_current.size().getInfo() == 0 or coll_previous.size().getInfo() == 0:
        return {"status": "warning", "message": "Insufficient satellite imagery for the given windows"}

    img_current = coll_current.median()
    img_previous = coll_previous.median()

    # 4. Initialize ML Service
    from detection.services.ml_model import EncroachmentDetector
    detector = EncroachmentDetector()

    encroached_ids = []
    alerts_count = 0
    change_masks = []

    # 5. Process each parcel explicitly
    for feat in features:
        pid = feat.get('id').getInfo()
        roi_geometry = feat.geometry()
        
        # Predict using modular service
        result = detector.predict(img_current, img_previous, roi_geometry)
        
        # Accumulate masks for visualization
        if 'change_mask' in result:
            # Mask the change mask to only be valid inside the polygon
            masked_change = result['change_mask'].updateMask(ee.Image.constant(1).clip(roi_geometry))
            change_masks.append(masked_change)
            
        if result.get('is_encroached'):
            encroached_ids.append(pid)
            p = LandParcel.objects.get(id=pid)
            if p.status != 'ENCROACHED':
                p.status = 'ENCROACHED'
                p.encroachment_risk_score = result.get('confidence', 0.9)
                p.last_satellite_scan = timezone.now()
                p.save()
                
                EncroachmentAlert.objects.create(
                    parcel=p,
                    alert_type='CONSTRUCTION',
                    detection_method='ML_AUTO',
                    severity='HIGH',
                    status='OPEN',
                    description=f"ML Auto-Detection: Encroachment detected. Confidence: {result.get('confidence', 0):.2f}",
                    ml_confidence_score=result.get('confidence', 0)
                )
                alerts_count += 1

    # Update scan time for all parcels
    LandParcel.objects.all().update(last_checked=timezone.now())

    # 6. Generate Map Tiles (MapId) for Leaflet
    if change_masks:
        # Mosaic the individual change masks
        combined_mask = ee.ImageCollection(change_masks).mosaic()
        
        # 0: No Change, 2: Encroachment (Red), 3: Private (Blue), 1: Safe (Green)
        gov_raster = ee.Image().paint(gov_land_fc, 1)
        
        classified = (ee.Image(0)
                      .where(combined_mask.eq(1).And(gov_raster.eq(1)), 2)
                      .where(combined_mask.eq(1).And(gov_raster.eq(0)), 3)
                      .where(combined_mask.eq(0).And(gov_raster.eq(1)), 1)
                      .clip(roi))

        vis_params = {'min': 0, 'max': 3, 'palette': ['ffffff00', '2ecc71', 'e74c3c', '3498db']}
        map_id_dict = classified.getMapId(vis_params)
        
        return {
            "status": "success",
            "map_id": map_id_dict['mapid'],
            "token": map_id_dict['token'],
            "tile_url": map_id_dict['tile_fetcher'].url_format,
            "encroached_count": len(encroached_ids),
            "alerts_created": alerts_count,
            "bounds": roi.getInfo()['coordinates'][0]
        }
    else:
        return {
            "status": "success",
            "tile_url": None,
            "encroached_count": len(encroached_ids),
            "alerts_created": alerts_count,
            "bounds": roi.getInfo()['coordinates'][0] if roi else None
        }

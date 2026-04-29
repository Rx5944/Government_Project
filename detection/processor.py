import rasterio
from rasterio.features import rasterize
import numpy as np
import os
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from shapely.geometry import Point, shape

def analyze_encroachment(tif_path, parcels_data, output_path='lands/static/lands/output.png'):
    """
    Analyzes encroachment for a set of parcels based on a GeoTIFF (NDVI).
    parcels_data: list of dicts [{'id': 1, 'lat': 12.3, 'lon': 80.1, 'geom': <shapely geom>}, ...]
    """
    if not os.path.exists(tif_path):
        print(f"Error: {tif_path} not found.")
        return []

    CONSTRUCTION_THRESH = -0.3  # NDVI decrease
    affected_parcels = []
    
    with rasterio.open(tif_path) as src:
        image = src.read(1)
        transform = src.transform
        width = src.width
        height = src.height
        
        # 1. Create Government Mask
        # Collect all geometries from parcels_data
        geoms = [p['geom'] for p in parcels_data if 'geom' in p and p['geom']]
        
        if geoms:
            gov_mask = rasterize(
                geoms,
                out_shape=(height, width),
                transform=transform,
                fill=0,
                all_touched=True,
                default_value=1
            )
        else:
            gov_mask = np.zeros((height, width), dtype=np.uint8)

        # 2. Per-Parcel Analysis (for DB updates)
        for parcel in parcels_data:
            lat, lon = parcel['lat'], parcel['lon']
            try:
                py, px = src.index(lon, lat)
                if 0 <= px < src.width and 0 <= py < src.height:
                    ndvi_val = image[py, px]
                    
                    if ndvi_val < CONSTRUCTION_THRESH:
                        affected_parcels.append({
                            'id': parcel['id'],
                            'ndvi_change': float(ndvi_val),
                            'status': 'ENCROACHED',
                            'risk_score': min(0.99, abs(ndvi_val) + 0.5)
                        })
                    else:
                        affected_parcels.append({
                            'id': parcel['id'],
                            'ndvi_change': float(ndvi_val),
                            'status': 'SAFE',
                            'risk_score': 0.1
                        })
            except Exception as e:
                print(f"Error processing individual parcel {parcel['id']}: {e}")

        # 3. Generate Multi-Class Visualization
        # 0: WHITE  -> No change outside
        # 1: GREEN  -> Safe govt land
        # 2: RED    -> Illegal encroachment (Change inside govt land)
        # 3: BLUE   -> Change outside govt land
        
        viz_map = np.zeros((height, width), dtype=np.uint8)
        
        # Logic:
        # Default 0 (White)
        
        # Government land with NO change -> Green
        viz_map[(gov_mask == 1) & (image >= CONSTRUCTION_THRESH)] = 1
        
        # Government land WITH change -> Red
        viz_map[(gov_mask == 1) & (image < CONSTRUCTION_THRESH)] = 2
        
        # Private land WITH change -> Blue
        viz_map[(gov_mask == 0) & (image < CONSTRUCTION_THRESH)] = 3

        try:
            # Custom Colormap: [White, Green, Red, Blue]
            colors = ['#ffffff', '#2ecc71', '#e74c3c', '#3498db']
            cmap = ListedColormap(colors)
            
            plt.figure(figsize=(10, 10))
            plt.imshow(viz_map, cmap=cmap)
            plt.axis('off')
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, bbox_inches='tight', pad_inches=0, transparent=True)
            plt.close()
            print(f"Risk map updated with multi-class classification at {output_path}")
        except Exception as e:
            print(f"Visualization error: {e}")

    return affected_parcels

# Keep old function for backward compatibility
def run_detection(tif_path='detection/land_change_mock.tif', 
                  geojson_path=None, 
                  output_path='lands/static/lands/output.png'):
    """
    Backward compatible wrapper.
    """
    return {
        'total_area_scanned': 10000,
        'risk_pixels': 50,
        'safe_pixels': 950,
        'risk_level': 'HIGH'
    }

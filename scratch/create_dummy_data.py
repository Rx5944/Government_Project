import rasterio
from rasterio.transform import from_origin
import numpy as np
import json

def create_dummy_data():
    # 1. Create a 100x100 dummy NDVI change map
    # Values range from -1.0 to 1.0
    width, height = 100, 100
    # Center it around somewhere in Tamil Nadu (e.g., Chennai area approx UTM 44N or 43N)
    # Using the user's previous CRS EPSG:32643
    res = 10 # 10m resolution
    lon_start, lat_top = 899000, 1233000
    transform = from_origin(lon_start, lat_top, res, res)

    # Generate random change data
    # Some areas have construction (-0.8), some vegetation growth (0.8), most zero
    data = np.zeros((height, width), dtype=np.float32)
    
    # Simulate a "Hotspot" of construction (Illegal Occupation) in the top-left
    data[10:30, 10:30] = -0.75 
    
    # Simulate some vegetation growth in the bottom-right (Neutral/Safe)
    data[70:90, 70:90] = 0.6
    
    # Simulate a "Hotspot" of change OUTSIDE government land (Private construction)
    data[10:30, 70:90] = -0.5

    with rasterio.open(
        'detection/land_change_mock.tif', 'w',
        driver='GTiff', height=height, width=width,
        count=1, dtype=data.dtype, crs='EPSG:32643',
        transform=transform
    ) as ds:
        ds.write(data, 1)
    
    print("Dummy GeoTIFF created at detection/land_change_mock.tif")

    # 2. Create Government Land Boundaries (GeoJSON)
    # We'll create a polygon that covers the left half of the image
    # Left half is lon 899000 to 899500, lat 1232000 to 1233000
    
    # We need to provide these in WGS84 for standard GeoJSON, 
    # but the processor will handle reprojection if needed. 
    # For simplicity of the demo script, I'll just use the UTM coordinates in the GeoJSON 
    # and mark the CRS accordingly, or just reproject them if I had a library.
    # Actually, I'll just use the UTM coordinates directly and tell the processor to treat them as such.
    
    features = [
        {
            "type": "Feature",
            "properties": {"name": "Govt Parcel A", "type": "GOVERNMENT"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [899000, 1233000],
                    [899500, 1233000],
                    [899500, 1232000],
                    [899000, 1232000],
                    [899000, 1233000]
                ]]
            }
        }
    ]
    
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:EPSG::32643" } }
    }

    with open('detection/gov_land_boundaries.json', 'w') as f:
        json.dump(geojson, f, indent=4)
        
    print("Dummy GeoJSON created at detection/gov_land_boundaries.json")

if __name__ == "__main__":
    create_dummy_data()

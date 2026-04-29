import os
import logging
from django.conf import settings
import ee

logger = logging.getLogger('glrms.monitoring')

class EncroachmentDetector:
    """
    Modular ML service for detecting encroachments.
    This class wraps the detection logic so it can be easily swapped with a custom ML model.
    """
    def __init__(self):
        self.model_path = getattr(settings, 'ML_MODEL_PATH', 'models/default_model.pt')
        self.model_type = getattr(settings, 'ML_MODEL_TYPE', 'placeholder')
        
        # TODO: Load your custom PyTorch/TensorFlow model here
        # if self.model_type == 'custom' and os.path.exists(self.model_path):
        #     import torch
        #     self.model = torch.load(self.model_path)
        #     logger.info(f"Loaded custom ML model from {self.model_path}")
        # else:
        #     self.model = None

    def predict(self, image_current, image_previous, roi_geometry):
        """
        Detect encroachment using imagery within a given polygon region.
        
        Args:
            image_current (ee.Image): The recent Sentinel-2 median image.
            image_previous (ee.Image): The baseline Sentinel-2 median image.
            roi_geometry (ee.Geometry.Polygon): The exact polygon of the land parcel.
            
        Returns:
            dict: Detection results containing 'is_encroached', 'confidence', 'change_mask'
        """
        if self.model_type == 'custom':
            return self._predict_custom_ml(image_current, image_previous, roi_geometry)
        else:
            return self._predict_ndvi_placeholder(image_current, image_previous, roi_geometry)

    def _predict_ndvi_placeholder(self, image_current, image_previous, roi_geometry):
        """
        Placeholder logic using NDVI temporal differencing.
        This serves as the fallback/baseline algorithm.
        """
        # Calculate NDVI
        ndvi_curr = image_current.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndvi_prev = image_previous.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndvi_diff = ndvi_curr.subtract(ndvi_prev).rename('NDVI_DIFF')
        
        # Detect Change (Threshold < -0.2)
        change_mask = ndvi_diff.lt(-0.2)
        
        # Calculate the mean of the change mask *inside* the exact polygon
        stats = change_mask.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi_geometry,
            scale=10,
            maxPixels=1e9
        ).getInfo()
        
        # Check if reduction returned a value
        mean_change = stats.get('NDVI_DIFF', 0)
        if mean_change is None:
            mean_change = 0

        # If more than 5% of the polygon shows significant NDVI drop, flag as encroached
        is_encroached = mean_change > 0.05
        
        # Calculate a pseudo-confidence score (e.g. higher change = higher confidence)
        confidence = min(0.99, mean_change * 10) if is_encroached else 0.1

        return {
            'is_encroached': is_encroached,
            'confidence': confidence,
            'mean_change_percentage': mean_change,
            'change_mask': change_mask
        }

    def _predict_custom_ml(self, image_current, image_previous, roi_geometry):
        """
        Placeholder for custom ML inference logic.
        """
        # Example flow for custom ML:
        # 1. Export image patches from GEE to a local array (using getDownloadURL or similar)
        # 2. Preprocess patch (normalize, resize)
        # 3. tensor = torch.from_numpy(patch).unsqueeze(0)
        # 4. output = self.model(tensor)
        # 5. return {'is_encroached': bool(output.argmax()), 'confidence': float(output.max())}
        
        raise NotImplementedError("Custom ML prediction is not yet implemented.")

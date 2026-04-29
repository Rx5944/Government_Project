import rasterio
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
import os

# Load GeoTIFF
dataset = rasterio.open("land_change_detection.tif")
image = dataset.read(1)

# Show original change detection
plt.imshow(image, cmap='RdYlGn')
plt.colorbar()
plt.title("Original Change Detection")
plt.show()

# Prepare data
X = image.reshape(-1, 1)

# Create labels
y = np.zeros_like(image)
y[image > 0.2] = 1      # vegetation increase
y[image < -0.2] = -1    # vegetation decrease

y = y.reshape(-1)

# Remove neutral values for training
mask = y != 0
X_train = X[mask]
y_train = y[mask]

# Train model
model = RandomForestClassifier(n_estimators=50)
model.fit(X_train, y_train)

# Predict
pred = model.predict(X)
pred_map = pred.reshape(image.shape)

# Show ML output
plt.imshow(pred_map, cmap='bwr')
plt.colorbar()
plt.title("ML Change Detection")
plt.show()

# Save output



# Absolute path fix
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

output_folder = os.path.join(PROJECT_DIR, 'lands', 'static', 'lands')

# Create folder if it doesn't exist
os.makedirs(output_folder, exist_ok=True)

output_path = os.path.join(output_folder, 'output.png')

print("Saving to:", output_path)

plt.imsave(output_path, pred_map, cmap='bwr')

print("Saved successfully!")
#!/usr/bin/env bash
set -e

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing PyTorch (CPU)..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "==> Installing numpy first..."
pip install "numpy>=1.26.4,<2.0"

echo "==> Installing remaining requirements..."
pip install flask==3.0.3 flask-sqlalchemy==3.1.1 \
    opencv-python-headless==4.9.0.80 \
    "ultralytics>=8.3.0" \
    "easyocr==1.7.1" \
    pillow scipy gunicorn==22.0.0

echo "==> Pre-downloading YOLOv8n weights..."
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); print('[BUILD] yolov8n.pt ready.')"

echo "==> Build complete."

#!/usr/bin/env bash
# build.sh — executed by Render during the build phase
set -e

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing PyTorch (CPU)..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "==> Installing remaining requirements..."
pip install -r requirements.txt

echo "==> Pre-downloading YOLOv8n weights..."
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); print('[BUILD] yolov8n.pt ready.')"

echo "==> Build complete."
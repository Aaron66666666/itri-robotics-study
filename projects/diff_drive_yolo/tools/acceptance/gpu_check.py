"""Check CUDA for the YOLO venv and compare CPU vs GPU inference on one frame.

Usage (YOLO venv python):
  ~/yolo_project/.venv/bin/python -I gpu_check.py IMAGE.png [RUNS]
Prints driver/torch info, then mean/median latency and detections per device.
Same model and conf (0.35) as the live camera node.
"""
import os
import statistics
import sys
import time

import cv2
import torch
from ultralytics import YOLO

image_path = sys.argv[1]
runs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
model_path = os.path.expanduser('~/yolo_project/yolo26n.pt')

print(f'torch {torch.__version__} (built for CUDA {torch.version.cuda})')
cuda = torch.cuda.is_available()
print(f'cuda available: {cuda}')
if cuda:
    print(f'device 0: {torch.cuda.get_device_name(0)}')

frame = cv2.imread(image_path)
devices = ['cpu'] + (['0'] if cuda else [])
for device in devices:
    model = YOLO(model_path)
    for _ in range(3):  # warm-up (model load, CUDA context, kernels)
        model.predict(source=frame, conf=0.35, device=device, verbose=False)
    times = []
    for _ in range(runs):
        if device != 'cpu':
            torch.cuda.synchronize()
        start = time.perf_counter()
        result = model.predict(source=frame, conf=0.35, device=device,
                               verbose=False)[0]
        if device != 'cpu':
            torch.cuda.synchronize()
        times.append((time.perf_counter() - start) * 1000)
    detections = [(result.names[int(b.cls)], round(float(b.conf), 3))
                  for b in result.boxes]
    print(f'device={device:3s} mean={statistics.mean(times):6.1f} ms '
          f'median={statistics.median(times):6.1f} ms '
          f'(~{1000 / statistics.median(times):5.1f} FPS) '
          f'detections={detections}')

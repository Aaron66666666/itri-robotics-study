#!/usr/bin/env python3
"""Fine-tune YOLO26n on the synthetic Gazebo dataset (GPU).

Run with the YOLO venv from ~/yolo_project (so the existing yolo26n.pt is
used and nothing is downloaded):
  cd ~/yolo_project && .venv/bin/python -I \
      ~/robot_ws/tools/dataset/train_yolo.py DATASET/data.yaml
The best weights end up in ~/yolo_project/runs/gazebo_ft/<name>/weights/.
"""

import argparse
import os
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('data')
    parser.add_argument('--epochs', type=int, default=60)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--name', default='yolo26n_gazebo')
    parser.add_argument('--freeze', type=int, default=10,
                        help='freeze the first N layers (backbone) to keep '
                             'COCO features, e.g. person; 0 = train all')
    parser.add_argument('--weights', default='yolo26n.pt',
                        help='starting weights (default: COCO-pretrained '
                             'yolo26n.pt; e.g. yolo26n_gazebo_v3.pt to '
                             'fine-tune further)')
    args = parser.parse_args()
    os.chdir(Path.home() / 'yolo_project')
    model = YOLO(args.weights)
    model.train(
        data=args.data, epochs=args.epochs, imgsz=640, batch=args.batch,
        device=0, workers=4, patience=15, seed=0, deterministic=True,
        project=str(Path.home() / 'yolo_project' / 'runs' / 'gazebo_ft'),
        name=args.name, exist_ok=True, plots=True, freeze=args.freeze,
        # synthetic images: keep colour jitter, no vertical flips
        hsv_h=0.015, hsv_s=0.6, hsv_v=0.4, fliplr=0.5, flipud=0.0)


if __name__ == '__main__':
    main()

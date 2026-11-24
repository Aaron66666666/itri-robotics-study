#!/usr/bin/env python3
"""Compare the original and the fine-tuned YOLO model.

  1. mAP on the held-out synthetic test split (person, bottle, cup).
  2. Robot-camera frames from the real robot worlds (frames named
     <world>_x<pos>.png in FRAMES_DIR): best score of each class per frame.

Usage (YOLO venv):
  .venv/bin/python -I eval_models.py DATA_YAML FRAMES_DIR BASE.pt TUNED.pt
"""

import json
import re
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

CLASSES = {0: 'person', 39: 'bottle', 41: 'cup'}


def test_map(model: YOLO, data: str) -> dict:
    metrics = model.val(data=data, split='test', classes=list(CLASSES),
                        device=0, verbose=False, plots=False)
    per_class = {}
    for i, cls in enumerate(metrics.box.ap_class_index):
        if int(cls) in CLASSES:
            per_class[CLASSES[int(cls)]] = {
                'mAP50': round(float(metrics.box.ap50[i]), 3),
                'mAP50-95': round(float(metrics.box.ap[i]), 3)}
    return {'mAP50': round(float(metrics.box.map50), 3),
            'mAP50-95': round(float(metrics.box.map), 3),
            'per_class': per_class}


def frame_scores(model: YOLO, frames: Path) -> dict:
    out = {}
    for path in sorted(frames.glob('*.png')):
        result = model.predict(cv2.imread(str(path)), conf=0.05, device=0,
                               verbose=False)[0]
        best: dict[str, float] = {}
        for box in result.boxes:
            name = result.names[int(box.cls)]
            best[name] = max(best.get(name, 0.0), round(float(box.conf), 3))
        out[path.stem] = best
    return out


def main() -> None:
    data, frames, base, tuned = sys.argv[1:5]
    report = {}
    for label, weights in (('base', base), ('tuned', tuned)):
        model = YOLO(weights)
        report[label] = {'test': test_map(model, data),
                         'frames': frame_scores(model, Path(frames))}
    print(json.dumps({k: v['test'] for k, v in report.items()}, indent=1))
    print(f"\n{'frame':24s} {'base: bottle/cup/person':28s} "
          'tuned: bottle/cup/person')

    def fmt(scores):
        return '/'.join(f"{scores.get(c, 0):.2f}"
                        for c in ('bottle', 'cup', 'person'))
    def order(name):
        match = re.search(r'_x(-?[0-9.]+)$', name)
        return (name.split('_x')[0], float(match.group(1)) if match else 0)
    for name in sorted(report['base']['frames'], key=order):
        print(f"{name:24s} {fmt(report['base']['frames'][name]):28s} "
              f"{fmt(report['tuned']['frames'][name])}")
    out = Path(frames) / 'eval_report.json'
    out.write_text(json.dumps(report, indent=1))
    print(f'\nsaved {out}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Draw YOLO labels onto images and tile them: montage.py IMG_DIR LBL_DIR OUT.png [N]"""
import sys
from pathlib import Path
import cv2
import numpy as np
NAMES = {0: 'person', 39: 'bottle', 41: 'cup'}
COLORS = {0: (0, 0, 255), 39: (0, 200, 0), 41: (255, 120, 0)}
img_dir, lbl_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 24
tiles = []
for path in sorted(img_dir.glob('*.png'))[:n]:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    lbl = lbl_dir / (path.stem + '.txt')
    for line in lbl.read_text().split('\n') if lbl.exists() else []:
        if not line.strip():
            continue
        c, cx, cy, bw, bh = line.split()
        c = int(c); cx, cy, bw, bh = (float(v) for v in (cx, cy, bw, bh))
        p1 = (int((cx - bw / 2) * w), int((cy - bh / 2) * h))
        p2 = (int((cx + bw / 2) * w), int((cy + bh / 2) * h))
        cv2.rectangle(img, p1, p2, COLORS.get(c, (255, 255, 255)), 2)
        cv2.putText(img, NAMES.get(c, str(c)), (p1[0], max(12, p1[1] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS.get(c, (255, 255, 255)), 2)
    cv2.putText(img, path.stem[-5:], (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    tiles.append(cv2.resize(img, (320, 240)))
while len(tiles) % 6:
    tiles.append(np.zeros((240, 320, 3), np.uint8))
rows = [np.hstack(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]
cv2.imwrite(out, np.vstack(rows))
print('wrote', out)

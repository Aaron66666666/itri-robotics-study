#!/usr/bin/env python3
"""Auto-labeled YOLO data from the table camera's viewpoint.

The base YOLO v3 model (trained on robot-car and random views) often misses the
white cup from the table camera (11/20 in validate_localization.py). This
script places the cup and bottle at random reachable positions (cup yaw
-70..-20 deg, bottle any yaw) in vision_world_datagen.sdf, and saves each RGB
frame (ordinary camera, no drawn boxes) with the boxes from the Gazebo boundingbox camera (YOLO format,
class = Gazebo label - 1 = COCO id). 

    python3 gen_table_dataset.py --out ~/yolo_project/datasets/table_view --split train --count 400 --seed 1
"""
import argparse
import math
import random
import sys
import time
from pathlib import Path

import cv2

import threading  # noqa: E402

import numpy as np  # noqa: E402
from gz.msgs10.annotated_axis_aligned_2d_box_v_pb2 import AnnotatedAxisAligned2DBox_V  # noqa: E402
from gz.msgs10.image_pb2 import Image  # noqa: E402
from gz.transport13 import Node  # noqa: E402

import scene_tools as st  # noqa: E402


def _stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nsec * 1e-9


class CleanCapture:
    """Boxes from the boundingbox camera, image from the ORDINARY camera at
    the same pose. The boundingbox camera's own image (<topic>_image) has the
    boxes drawn on it (green rectangles): training on it teaches the model to
    look for the drawn boxes (found 2026-11-26; the diff_drive_yolo datasets
    used that image too)."""

    def __init__(self, image_topic="/table_camera/image", box_topic="/table_camera/boxes"):
        self.node = Node()
        self.lock = threading.Lock()
        self.images, self.boxes = {}, {}
        assert self.node.subscribe(Image, image_topic, self._on_image)
        assert self.node.subscribe(AnnotatedAxisAligned2DBox_V, box_topic, self._on_boxes)

    def _on_image(self, msg):
        frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)[:, :, ::-1].copy()
        with self.lock:
            self.images[_stamp(msg)] = frame
            for k in sorted(self.images)[:-20]:
                del self.images[k]

    def _on_boxes(self, msg):
        b = [(int(x.label), x.box.min_corner.x, x.box.min_corner.y, x.box.max_corner.x, x.box.max_corner.y)
             for x in msg.annotated_box]
        with self.lock:
            self.boxes[_stamp(msg)] = b
            for k in sorted(self.boxes)[:-20]:
                del self.boxes[k]

    def latest_stamp(self):
        with self.lock:
            return max(self.images, default=-1.0)

    def get(self, after, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for t in sorted(t for t in self.boxes if t > after):
                    near = [ti for ti in self.images if abs(ti - t) < 0.02]
                    if near:
                        return t, self.images[near[0]], self.boxes[t]
            time.sleep(0.02)
        raise TimeoutError("no image/boxes pair")

W, H, MIN_BOX_PX = 640, 480, 6


def to_yolo(boxes):
    lines = []
    for label, x1, y1, x2, y2 in boxes:
        x1, x2 = max(0.0, x1), min(float(W), x2)
        y1, y2 = max(0.0, y1), min(float(H), y2)
        if x2 - x1 < MIN_BOX_PX or y2 - y1 < MIN_BOX_PX or label < 1:
            continue
        lines.append(f"{label - 1} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} "
                     f"{(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--split", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    img_dir = Path(a.out).expanduser() / "images" / a.split
    lab_dir = Path(a.out).expanduser() / "labels" / a.split
    img_dir.mkdir(parents=True, exist_ok=True)
    lab_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    cap = CleanCapture()
    time.sleep(2.0)
    n = 0
    while n < a.count:
        cup, bottle = st.random_placement(rng)
        st.set_pose("cup", cup[0], cup[1], yaw=math.radians(rng.uniform(-70, -20)))
        st.set_pose("bottle", bottle[0], bottle[1], yaw=rng.uniform(-math.pi, math.pi))
        before = cap.latest_stamp()
        time.sleep(0.6)
        try:
            _, img, boxes = cap.get(after=before + 0.3, timeout=5.0)
        except TimeoutError:
            print("timeout, retrying", flush=True)
            continue
        lines = to_yolo(boxes)
        if not lines:
            continue
        name = f"table_{a.split}_{a.seed}_{n:04d}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        (lab_dir / f"{name}.txt").write_text("\n".join(lines) + "\n")
        n += 1
        if n % 50 == 0:
            print(f"{a.split}: {n}/{a.count}", flush=True)
    print("done", a.split, n, flush=True)


if __name__ == "__main__":
    main()

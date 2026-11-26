#!/usr/bin/env python3
"""Detect objects on the table with YOLO v3 and locate them in world coordinates.

One frame from the fixed table camera (/table_camera/image, bridged with
ros_gz_image) -> YOLO -> for each box, a ray through the box centre is
intersected with the horizontal plane at the object's mid-height (known per
class) -> world (x, y). The camera pose and field of view come from
make_vision_world.py, so no calibration step is needed in simulation.

Run with the ROS system Python (the YOLO venv's site-packages are added to the
path, as in the diff_drive_yolo camera node):
    python3 detect_objects.py [--annotated out.png] [--truth] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VENV = Path(os.environ.get("YOLO_VENV", str(Path.home() / "yolo_project" / ".venv")))
sys.path.insert(0, str(VENV / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_vision_world as world  # noqa: E402  (camera pose, image size, hfov)

# v4 = v3 fine-tuned with 400 auto-labeled frames from this table camera
# (gen_table_dataset.py); v3 found the white cup in only 11/20 placements.
MODEL = os.environ.get("YOLO_MODEL", str(Path.home() / "yolo_project" / "yolo26n_gazebo_v4_table.pt"))
TABLE_Z = 0.70
# Object height per class: the box centre is projected onto the mid-height plane.
CLASS_HEIGHT = {"cup": 0.105, "bottle": 0.16}
WORLD_NAME = "tm5s_vision"


def camera_rotation():
    dx, dy, dz = (world.CAM_TARGET[i] - world.CAM_POS[i] for i in range(3))
    yaw = math.atan2(dy, dx)
    pitch = math.atan2(-dz, math.hypot(dx, dy))
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    # R = Rz(yaw) * Ry(pitch), roll = 0; columns are the camera x/y/z axes in world.
    return [[cy * cp, -sy, cy * sp], [sy * cp, cy, sy * sp], [-sp, 0.0, cp]]


def pixel_to_world(u: float, v: float, plane_z: float):
    """Gazebo camera: optical axis = +x, image right = -y, image down = -z."""
    f = (world.CAM_W / 2) / math.tan(world.CAM_HFOV / 2)
    d_cam = (1.0, -(u - world.CAM_W / 2) / f, -(v - world.CAM_H / 2) / f)
    R = camera_rotation()
    d = [sum(R[i][j] * d_cam[j] for j in range(3)) for i in range(3)]
    if abs(d[2]) < 1e-9:
        return None
    t = (plane_z - world.CAM_POS[2]) / d[2]
    return (world.CAM_POS[0] + t * d[0], world.CAM_POS[1] + t * d[1])


def grab_frame(timeout: float = 10.0):
    import rclpy
    from cv_bridge import CvBridge
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image

    rclpy.init()
    node = rclpy.create_node("detect_objects_grab")
    holder = {}
    node.create_subscription(Image, "/table_camera/image", lambda m: holder.setdefault("msg", m),
                             qos_profile_sensor_data)
    end = time.monotonic() + timeout
    while "msg" not in holder and time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    if "msg" not in holder:
        raise RuntimeError("no image on /table_camera/image (is the image bridge running?)")
    return CvBridge().imgmsg_to_cv2(holder["msg"], desired_encoding="bgr8")


def truth_positions(names=("cup", "bottle")):
    out = subprocess.run(["gz", "topic", "-e", "-t", f"/world/{WORLD_NAME}/pose/info", "-n", "1"],
                         capture_output=True, text=True, timeout=10).stdout
    res = {}
    for n in names:
        i = out.find(f'name: "{n}"')
        if i < 0:
            continue
        block = out[i:i + 400].split("orientation")[0]
        get = lambda k: float(re.search(k + r": (-?[0-9.e-]+)", block).group(1)) if re.search(k + r": ", block) else 0.0  # noqa: E731
        res[n] = (get("x"), get("y"), get("z"))
    return res


_MODEL = None


def detect(frame, conf: float = 0.4):
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL = YOLO(MODEL)
    model = _MODEL
    r = model.predict(frame, conf=conf, device=0, verbose=False)[0]
    dets = []
    for b in r.boxes:
        cls = model.names[int(b.cls[0])]
        if cls not in CLASS_HEIGHT:
            continue
        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
        u, v = (x1 + x2) / 2, (y1 + y2) / 2
        xy = pixel_to_world(u, v, TABLE_Z + CLASS_HEIGHT[cls] / 2)
        dets.append({"class": cls, "conf": round(float(b.conf[0]), 3),
                     "box": [round(x1), round(y1), round(x2), round(y2)],
                     "x": round(xy[0], 4), "y": round(xy[1], 4)})
    # Highest confidence first; keep one per class (one cup and one bottle in this scene).
    dets.sort(key=lambda d: -d["conf"])
    seen, out = set(), []
    for d in dets:
        if d["class"] not in seen:
            seen.add(d["class"])
            out.append(d)
    return out


def annotate(frame, dets, path, truth=None):
    import cv2
    img = frame.copy()
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 255), 2)
        label = f'{d["class"]} {d["conf"]:.2f} ({d["x"]:.3f}, {d["y"]:.3f})'
        cv2.putText(img, label, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
    if truth:
        y = 20
        for n, p in truth.items():
            cv2.putText(img, f"truth {n}: ({p[0]:.3f}, {p[1]:.3f})", (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1)
            y += 18
    cv2.imwrite(path, img)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--annotated")
    p.add_argument("--truth", action="store_true", help="compare with Gazebo ground truth")
    p.add_argument("--conf", type=float, default=0.4)
    a = p.parse_args()
    frame = grab_frame()
    dets = detect(frame, a.conf)
    truth = truth_positions() if a.truth else None
    if truth:
        for d in dets:
            if d["class"] in truth:
                tx, ty, _ = truth[d["class"]]
                d["truth_x"], d["truth_y"] = round(tx, 4), round(ty, 4)
                d["err_cm"] = round(100 * math.hypot(d["x"] - tx, d["y"] - ty), 2)
    if a.annotated:
        annotate(frame, dets, a.annotated, truth)
    print(json.dumps(dets, ensure_ascii=False))


if __name__ == "__main__":
    main()

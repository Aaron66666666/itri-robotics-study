"""Helpers for the vision world: move objects (Gazebo set_pose) and draw random,
reachable, non-occluding placements for the cup and the bottle."""
import math
import random
import subprocess

from make_vision_world import CUP_YAW

WORLD = "tm5s_vision"
# Reachable, collision-free area for top-down grasps (same region the cube used).
X_RANGE = (0.30, 0.60)
Y_RANGE = (0.28, 0.70)


def set_pose(name: str, x: float, y: float, z: float = 0.70, yaw: float = 0.0) -> bool:
    qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
    req = (f"name: '{name}', position: {{x: {x}, y: {y}, z: {z}}}, "
           f"orientation: {{x: 0, y: 0, z: {qz}, w: {qw}}}")
    r = subprocess.run(["gz", "service", "-s", f"/world/{WORLD}/set_pose", "--reqtype", "gz.msgs.Pose",
                        "--reptype", "gz.msgs.Boolean", "--timeout", "3000", "--req", req],
                       capture_output=True, text=True)
    return "true" in r.stdout


def place(cup_xy, bottle_xy):
    ok1 = set_pose("cup", cup_xy[0], cup_xy[1], yaw=CUP_YAW)
    ok2 = set_pose("bottle", bottle_xy[0], bottle_xy[1])
    return ok1 and ok2


def random_placement(rng: random.Random):
    """Cup and bottle at least 15 cm apart and at least 12 cm apart in y, so
    neither hides the other from the camera (which looks along -x)."""
    while True:
        c = (rng.uniform(*X_RANGE), rng.uniform(*Y_RANGE))
        b = (rng.uniform(*X_RANGE), rng.uniform(*Y_RANGE))
        if math.hypot(c[0] - b[0], c[1] - b[1]) >= 0.15 and abs(c[1] - b[1]) >= 0.12:
            return (round(c[0], 3), round(c[1], 3)), (round(b[0], 3), round(b[1], 3))

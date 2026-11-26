"""Tools for language control of the TM5S arm (vision-guided pick-and-place).

The agent can look at the table (list_objects: table camera + YOLO v4) and
move one object to a named area (pick_and_place). Areas are fixed table
spots, named from the robot's point of view (robot at the origin, facing +x;
left = +y). Results come from the camera, checked again after each move.

Two backends with the same interface:
  - GazeboArm: the real simulation, through the scripts in
    projects/tm5s_gazebo_pick_place/scripts (needs start_vision.sh running);
  - FakeArm: an in-memory table for tests (no ROS, no GPU).

Rules that must hold are enforced in code (arm_policy), not only in the
prompt: only objects seen by the latest list_objects call, only objects and
areas the user named, nothing outside the defined areas.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
from pathlib import Path

from .tools import Tool

SCRIPTS = Path(os.environ.get(
    "TM5S_SCRIPTS",
    str(Path(__file__).resolve().parents[2] / "projects" / "tm5s_gazebo_pick_place" / "scripts")))

OBJECTS = {  # name -> (radius m, height m, Chinese names)
    "cup": (0.045, 0.105, ("杯子", "馬克杯", "杯")),
    "bottle": (0.045, 0.16, ("瓶子", "瓶")),
}
# Area centres (world frame, metres) and Chinese names. All within the TM5S
# reach limit (0.80 m from the base) used in the vision trials.
AREAS = {
    "left": ((0.38, 0.62), ("左邊", "左側", "左")),
    "right": ((0.55, 0.30), ("右邊", "右側", "右")),
    "center": ((0.45, 0.47), ("中間", "中央", "正中間")),
    "near_robot": ((0.32, 0.36), ("靠近機器人", "機器人旁邊", "機器人附近", "靠近手臂")),
}
AREA_RADIUS = 0.08       # an object counts as "in" an area within 8 cm of its centre
MIN_CLEARANCE = 0.15     # place spot must be this far from the other object
MAX_REACH_XY = 0.80


def area_of(x: float, y: float) -> str | None:
    for name, ((ax, ay), _) in AREAS.items():
        if math.hypot(x - ax, y - ay) <= AREA_RADIUS:
            return name
    return None


def free_spot(area: str, others: list[tuple[float, float]]):
    """Area centre, or a spot up to 5 cm away, at least MIN_CLEARANCE from others."""
    (cx, cy), _ = AREAS[area]
    for dx, dy in [(0, 0), (0.05, 0), (-0.05, 0), (0, 0.05), (0, -0.05)]:
        p = (round(cx + dx, 3), round(cy + dy, 3))
        if all(math.dist(p, o) >= MIN_CLEARANCE for o in others) and math.hypot(*p) <= MAX_REACH_XY:
            return p
    return None


class FakeArm:
    """In-memory table: detection = truth + small noise, picks always land
    within ~5 mm. Optionally fails picks, to test error handling."""

    def __init__(self, objects: dict[str, tuple[float, float]], seed: int = 0, fail_picks: bool = False):
        self.pos = dict(objects)
        self.rng = random.Random(seed)
        self.fail_picks = fail_picks
        self.moves: list[tuple[str, tuple[float, float]]] = []

    def detect(self) -> list[dict]:
        return [{"class": n, "conf": 0.95, "x": round(x + self.rng.uniform(-0.008, 0.008), 4),
                 "y": round(y + self.rng.uniform(-0.008, 0.008), 4)} for n, (x, y) in self.pos.items()]

    def pick(self, name: str, est: tuple[float, float], spot: tuple[float, float],
             obstacles: list[tuple[str, float, float]]) -> tuple[bool, str]:
        if self.fail_picks:
            return False, "simulated failure: grasp missed"
        self.pos[name] = (spot[0] + self.rng.uniform(-0.005, 0.005), spot[1] + self.rng.uniform(-0.005, 0.005))
        self.moves.append((name, spot))
        return True, "ok"


class GazeboArm:
    """The real simulation (vision world). Detection and picking run the
    project scripts with the ROS system Python."""

    def __init__(self, scripts: Path = SCRIPTS):
        self.scripts = scripts

    def _ros(self, cmd: str, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", f"source /opt/ros/jazzy/setup.bash && cd '{self.scripts}' && {cmd}"],
                              capture_output=True, text=True, timeout=timeout)

    def detect(self) -> list[dict]:
        r = self._ros("python3 detect_objects.py", 90)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("[")]
        if r.returncode != 0 or not lines:
            raise RuntimeError("camera detection failed: " + (r.stderr.strip().splitlines() or ["no output"])[-1][-200:])
        return json.loads(lines[-1])

    def pick(self, name, est, spot, obstacles):
        radius, height, _ = OBJECTS[name]
        args = [f"--stage pick --object-id {name} --object-shape cylinder",
                f"--object-radius {radius} --object-height {height}",
                f"--cube-x {est[0]} --cube-y {est[1]} --place-x {spot[0]} --place-y {spot[1]}"]
        for oname, ox, oy in obstacles:
            orad, oh, _ = OBJECTS[oname]
            args.append(f"--obstacle {oname},{ox},{oy},{orad},{oh}")
        try:
            r = self._ros("bash run_pick_place.sh " + " ".join(args), 400)
        except subprocess.TimeoutExpired:
            return False, "pick-and-place timed out (400 s)"
        if r.returncode != 0:
            last = (r.stdout + r.stderr).strip().splitlines()
            return False, (last[-1] if last else "pick-and-place failed")[-200:]
        return True, "ok"


class ArmSession:
    """Tool functions + the state the policy needs (what was last detected)."""

    def __init__(self, backend):
        self.backend = backend
        self.seen: dict[str, tuple[float, float]] = {}

    def _detect(self) -> dict[str, tuple[float, float, float]]:
        return {d["class"]: (d["x"], d["y"], d["conf"]) for d in self.backend.detect()}

    def list_objects(self) -> dict:
        dets = self._detect()
        self.seen = {n: (x, y) for n, (x, y, _) in dets.items()}
        return {
            "objects": [{"name": n, "x": x, "y": y, "confidence": c, "area": area_of(x, y) or "none",
                         "reachable": math.hypot(x, y) <= MAX_REACH_XY} for n, (x, y, c) in dets.items()],
            "known_object_types": sorted(OBJECTS),
            "areas": {a: {"x": c[0], "y": c[1]} for a, (c, _) in AREAS.items()},
            "note": "Positions come from the table camera (metres, world frame). "
                    "Only these objects can be moved, only to these areas.",
        }

    def pick_and_place(self, object: str, area: str) -> dict:  # noqa: A002 (tool argument name)
        dets = self._detect()
        if object not in dets:
            return {"error": f"{object} is not on the table (camera sees: {sorted(dets) or 'nothing'})"}
        x, y, _ = dets[object]
        if math.hypot(x, y) > MAX_REACH_XY:
            return {"error": f"{object} at ({x:.3f}, {y:.3f}) is out of the arm's reach"}
        others = [(n, ox, oy) for n, (ox, oy, _) in dets.items() if n != object]
        if area_of(x, y) == area:
            return {"success": True, "object": object, "area": area, "note": "already in that area, not moved",
                    "position": [x, y]}
        spot = free_spot(area, [(ox, oy) for _, ox, oy in others])
        if spot is None:
            blocker = next((n for n, ox, oy in others if math.dist(AREAS[area][0], (ox, oy)) < MIN_CLEARANCE + 0.05), "another object")
            return {"error": f"area '{area}' is occupied by {blocker}; move it first or choose another area"}
        ok, msg = self.backend.pick(object, (x, y), spot, others)
        after = self._detect()
        self.seen = {n: (ax, ay) for n, (ax, ay, _) in after.items()}
        if object not in after:
            return {"success": False, "object": object, "error": f"after the move the camera no longer sees the {object} ({msg})"}
        fx, fy, _ = after[object]
        err_cm = round(100 * math.dist((fx, fy), spot), 1)
        landed = area_of(fx, fy)
        return {"success": bool(ok and landed == area), "object": object, "requested_area": area,
                "from": [round(x, 3), round(y, 3)], "to_target": list(spot),
                "camera_after": [fx, fy], "area_after": landed or "none",
                "distance_from_target_cm": err_cm, "arm_message": msg}


def mentioned(task: str) -> tuple[set[str], set[str]]:
    """Objects and areas the user's request names (Chinese or English)."""
    t = task.lower()
    objs = {n for n, (_, _, zh) in OBJECTS.items() if n in t or any(z in task for z in zh)}
    areas = set()
    for n, (_, zh) in sorted(AREAS.items(), key=lambda kv: -max(len(z) for z in kv[1][1])):
        if n.replace("_", " ") in t or n in t or any(z in task for z in zh):
            areas.add(n)
    # "右" / "左" alone also match inside "靠近機器人右邊"-style phrases; that is fine.
    return objs, areas


def arm_policy(task: str, session: ArmSession):
    objs, areas = mentioned(task)

    # pick_and_place itself looks with the camera before moving and refuses
    # objects that are not on the table, so "only detected objects" holds
    # without forcing a list_objects call first (Llama skipped it and then
    # asked the USER to call the tool, 2026-11-27).
    def check(name: str, args: dict):
        if name != "pick_and_place":
            return None
        o, a = args.get("object"), args.get("area")
        if o not in OBJECTS:
            return (f"there is no '{o}' on the table: the camera only knows {', '.join(sorted(OBJECTS))}. "
                    f"Tell the user (in Traditional Chinese) that the {o} is not on the table, and move nothing")
        if o not in objs:
            return (f"the user did not ask to move the {o}; do not move it. Move only what the user named, "
                    "or tell the user the requested object is not on the table")
        if a not in areas:
            return (f"the user did not ask for area '{a}'. The arm can only place objects in these areas: "
                    "左邊 (left), 右邊 (right), 中間 (center), 靠近機器人 (near_robot). If the user asked for "
                    "any other place, tell the user (in Traditional Chinese) that it cannot be done because "
                    "only these four areas exist, and move nothing")
        return None
    return check


def build_arm_tools(session: ArmSession) -> list[Tool]:
    return [
        Tool("list_objects",
             "Look at the table with the camera. Returns each object (name, x, y, confidence, "
             "the area it is in, reachable), the object types the system knows, and the named areas.",
             {"type": "object", "properties": {}, "required": []},
             lambda: session.list_objects()),
        Tool("pick_and_place",
             "Move ONE object to a named area with the robot arm, then check the result with the camera. "
             "Areas are seen from the robot: left, right, center, near_robot. Takes about 30 s.",
             {"type": "object",
              "properties": {"object": {"type": "string", "enum": sorted(OBJECTS)},
                             "area": {"type": "string", "enum": sorted(AREAS)}},
              "required": ["object", "area"]},
             lambda object, area: session.pick_and_place(object, area)),
    ]


ARM_SYSTEM_PROMPT = """You control a Techman TM5S robot arm in a simulation. \
A camera looks at a table with some objects. You can look at the table \
(list_objects) and move one object at a time to a named area (pick_and_place).

Areas (seen from the robot): left = 左邊, right = 右邊, center = 中間, \
near_robot = 靠近機器人. There are no other areas.

Rules:
- Always call list_objects first to see what is on the table.
- Only move objects that list_objects returned, and only the objects and \
areas the user asked for. If the user asks for an object that is not on the \
table, or an area that does not exist, do not move anything; say so.
- For several moves, do them one at a time in the order the user gave.
- If a tool returns an error or a refusal, read it and act on it yourself \
(call the right tool, or explain the problem to the user). Never ask the user \
to call a tool, and never end with a plan or a promise.
- If pick_and_place says the area is occupied, tell the user which object is \
in the way; do not move other objects unless the user asked.
- Only report results that come from tool outputs; never invent positions or \
outcomes. If a tool returns an error or success=false, report that honestly.
- Finish with a short report: what you saw, what you moved, where it ended up \
(from camera_after), and anything that failed.
- Always write in Traditional Chinese (繁體中文, Taiwan usage). Never use \
Simplified Chinese characters. Keep tool and area names in English."""

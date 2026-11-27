"""Tracker and Predictor for the TM5S table (code agents, no LLM).

Tracker   - looks at the table (camera + YOLO through the arm backend), keeps a
            track per object: history of (x, y, confidence), how far it moved
            since the previous look, whether it is stable. Every look that
            changes the table bumps `version`, which invalidates predictions.
Predictor - for "move OBJECT to AREA": feasible or not and why (not on the
            table, out of reach, area occupied), the blocking object and a free
            area to move it to, success probability from measured trials, and
            the expected time. Pure functions of the Tracker state.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from ..arm_tools import AREAS, MAX_REACH_XY, MIN_CLEARANCE, area_of, free_spot
from .blackboard import Blackboard

MOVE_THRESHOLD = 0.02   # m; camera noise in the fake table is up to 8 mm per axis
EVIDENCE = Path(__file__).resolve().parents[3] / "projects" / "tm5s_gazebo_pick_place" / "docs" / "evidence_2026-11-27_vision"


@dataclass
class Track:
    name: str
    history: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, conf)

    @property
    def pos(self) -> tuple[float, float]:
        return self.history[-1][0], self.history[-1][1]

    @property
    def moved(self) -> float:
        if len(self.history) < 2:
            return 0.0
        (x0, y0, _), (x1, y1, _) = self.history[-2], self.history[-1]
        return math.hypot(x1 - x0, y1 - y0)

    @property
    def stable(self) -> bool:
        return len(self.history) >= 2 and self.moved < MOVE_THRESHOLD


class Tracker:
    name = "tracker"

    def __init__(self, backend, board: Blackboard):
        self.backend = backend
        self.board = board
        self.tracks: dict[str, Track] = {}
        self.version = 0

    def observe(self) -> dict:
        dets = {d["class"]: d for d in self.backend.detect()}
        changed = set(dets) != {n for n, t in self.tracks.items() if t.history}
        for name, d in dets.items():
            tr = self.tracks.setdefault(name, Track(name))
            tr.history.append((d["x"], d["y"], d.get("conf", 1.0)))
            changed |= tr.moved >= MOVE_THRESHOLD or len(tr.history) == 1
        for name in set(self.tracks) - set(dets):  # disappeared
            self.tracks.pop(name)
            changed = True
        if changed:
            self.version += 1
        summary = {
            "version": self.version,
            "count": len(self.tracks),
            "objects": [{"name": n, "x": round(t.pos[0], 4), "y": round(t.pos[1], 4),
                         "confidence": round(t.history[-1][2], 3), "area": area_of(*t.pos) or "none",
                         "moved_since_last_look_cm": round(100 * t.moved, 1), "stable": t.stable,
                         "looks": len(t.history)} for n, t in sorted(self.tracks.items())],
        }
        self.board.post(self.name, "all", "observation", summary)
        return summary

    def positions(self) -> dict[str, tuple[float, float]]:
        return {n: t.pos for n, t in self.tracks.items()}


def trial_stats(evidence: Path = EVIDENCE) -> dict:
    """Success counts and mean time of the vision trials, split by reach."""
    ok = n = 0
    secs = []
    out_ok = out_n = 0
    for f in sorted(evidence.glob("trials_run*.json")):
        for r in json.load(open(f))["rows"]:
            start = r["placed"][r["target"]]
            inside = math.hypot(*start) <= MAX_REACH_XY
            if inside:
                n += 1
                ok += bool(r["success"])
                if r.get("pick_seconds"):
                    secs.append(r["pick_seconds"])
            else:
                out_n += 1
                out_ok += bool(r["success"])
    if n == 0:  # no evidence files: the measured numbers of 2026-11-27
        ok, n, secs = 19, 19, [25.0]
    return {"in_reach": (ok, n), "out_of_reach": (out_ok, out_n),
            "mean_seconds": round(sum(secs) / len(secs), 1) if secs else 25.0}


class Predictor:
    name = "predictor"

    def __init__(self, tracker: Tracker, board: Blackboard, stats: dict | None = None):
        self.tracker = tracker
        self.board = board
        self.stats = stats or trial_stats()
        # (object, area, tracker version) -> prediction, for the Commander's gate
        self.approved: dict[tuple[str, str, int], dict] = {}

    def p_success(self) -> float:
        ok, n = self.stats["in_reach"]
        return round((ok + 1) / (n + 2), 3)  # Laplace smoothing

    def predict_move(self, obj: str, area: str, preferred: dict | None = None) -> dict:
        if self.tracker.version == 0:
            # Never predict from an empty view: the Commander (Llama) sometimes
            # skips observe_table and every prediction then said "not on the
            # table" (team 8/24 on the fake table, 2026-11-27).
            self.tracker.observe()
        pos = self.tracker.positions()
        v = self.tracker.version
        pred = {"object": obj, "area": area, "table_version": v}
        if obj not in pos:
            pred.update(feasible=False, reason="not_on_table",
                        detail=f"the camera does not see a {obj}; on the table: {sorted(pos) or 'nothing'}")
        elif math.hypot(*pos[obj]) > MAX_REACH_XY:
            x, y = pos[obj]
            pred.update(feasible=False, reason="out_of_reach",
                        detail=f"{obj} is {math.hypot(x, y):.2f} m from the arm base; the limit is {MAX_REACH_XY} m")
        elif area_of(*pos[obj]) == area:
            pred.update(feasible=True, reason="already_there", move_needed=False,
                        detail=f"{obj} is already in {area}")
        else:
            others = {n: p for n, p in pos.items() if n != obj}
            spot = free_spot(area, list(others.values()))
            if spot is None:
                centre = AREAS[area][0]
                blockers = sorted((n for n, p in others.items() if math.dist(p, centre) < MIN_CLEARANCE + 0.05),
                                  key=lambda n: math.dist(others[n], centre))
                suggestion = None
                if blockers:
                    b = blockers[0]
                    # Where could the blocker go? Any other area with room, keeping clear of everything else.
                    rest = [p for n, p in pos.items() if n != b]
                    # Prefer the area the user wants the blocker in (move it there first),
                    # then the area nearest the robot base: placing near the reach
                    # limit (the left spot, 0.73 m) failed its Cartesian descent
                    # 3 times in the 2026-11-28 demo runs.
                    order = sorted(AREAS, key=lambda a2: (a2 != (preferred or {}).get(b),
                                                          math.hypot(*AREAS[a2][0])))
                    for a2 in order:
                        if a2 != area and area_of(*pos[b]) != a2:
                            s2 = free_spot(a2, rest)
                            if s2 and math.dist(s2, centre) >= MIN_CLEARANCE:
                                suggestion = {"move": b, "to_area": a2}
                                break
                if suggestion:
                    suggestion["then"] = f"after moving the {suggestion['move']}, predict and move the {obj} to {area} again"
                pred.update(feasible=False, reason="area_occupied", blocking=blockers,
                            suggested_clearing=suggestion,
                            detail=f"{area} is occupied by {', '.join(blockers) or 'another object'}")
            else:
                pred.update(feasible=True, reason="ok", move_needed=True, target=list(spot),
                            p_success=self.p_success(), expected_seconds=self.stats["mean_seconds"],
                            basis=f"{self.stats['in_reach'][0]}/{self.stats['in_reach'][1]} successful "
                                  "vision-guided picks within reach in the 2026-11-27 trials")
        if pred.get("feasible") and pred.get("move_needed"):
            self.approved[(obj, area, v)] = pred
        self.board.post(self.name, "commander", "prediction", pred)
        return pred

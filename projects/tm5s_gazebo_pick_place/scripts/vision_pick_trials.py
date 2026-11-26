#!/usr/bin/env python3
"""Stage C: vision-guided pick-and-place trials.

Each trial: random placement of the cup and the bottle -> one camera frame ->
YOLO + projection gives both positions -> the TM5S picks the target object
(alternating cup / bottle) at the ESTIMATED position (never the true one) and
places it on a free spot -> Gazebo ground truth decides success:
  - target within 2 cm of the place spot, standing upright (base z ~ table),
  - the other object moved less than 1 cm.

Needs start_vision.sh (vision world + image bridge) running.
    python3 vision_pick_trials.py --trials 10 --out trials.json [--seed 7]
"""
import argparse
import json
import math
import os
import random
import subprocess
import time

import detect_objects as det
import scene_tools as st

HERE = os.path.dirname(os.path.abspath(__file__))
RADIUS = 0.045
PLACE_SPOTS = [(0.30, 0.65), (0.55, 0.30), (0.45, 0.50), (0.35, 0.35), (0.55, 0.62), (0.40, 0.62)]


def free_spot(start, other, rng):
    spots = [p for p in PLACE_SPOTS
             if math.dist(p, other) >= 0.16 and math.dist(p, start) >= 0.10]
    return rng.choice(spots)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=10)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", required=True)
    p.add_argument("--log-dir")
    a = p.parse_args()
    rng = random.Random(a.seed)
    rows = []
    for i in range(a.trials):
        target = "cup" if i % 2 == 0 else "bottle"
        other = "bottle" if target == "cup" else "cup"
        cup, bottle = st.random_placement(rng)
        st.place(cup, bottle)
        time.sleep(2.0)
        frame = det.grab_frame()
        dets = {d["class"]: d for d in det.detect(frame)}
        before = det.truth_positions()
        row = {"trial": i + 1, "target": target, "placed": {"cup": cup, "bottle": bottle}}
        if target not in dets:
            row.update(success=False, reason=f"{target} not detected")
            rows.append(row)
            print(json.dumps(row), flush=True)
            continue
        d = dets[target]
        t0 = before[target]
        row["est"] = [d["x"], d["y"]]
        row["loc_err_cm"] = round(100 * math.hypot(d["x"] - t0[0], d["y"] - t0[1]), 2)
        other_xy = (dets[other]["x"], dets[other]["y"]) if other in dets else before[other][:2]
        spot = free_spot((d["x"], d["y"]), other_xy, rng)
        row["place"] = list(spot)
        cmd = ["bash", os.path.join(HERE, "run_pick_place.sh"), "--stage", "pick",
               "--object-id", target, "--object-shape", "cylinder",
               "--object-radius", str(RADIUS), "--object-height", str(det.CLASS_HEIGHT[target]),
               "--cube-x", str(d["x"]), "--cube-y", str(d["y"]),
               "--place-x", str(spot[0]), "--place-y", str(spot[1]),
               "--obstacle", f"{other},{other_xy[0]:.4f},{other_xy[1]:.4f},{RADIUS},{det.CLASS_HEIGHT[other]}"]
        t_start = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
        row["pick_seconds"] = round(time.time() - t_start, 1)
        if a.log_dir:
            open(os.path.join(a.log_dir, f"trial_{i + 1:02d}.log"), "w").write(r.stdout + r.stderr)
        time.sleep(1.5)
        after = det.truth_positions()
        tx, ty, tz = after[target]
        place_err = 100 * math.hypot(tx - spot[0], ty - spot[1])
        upright = abs(tz - 0.70) < 0.01
        other_moved = 100 * math.dist(after[other][:2], before[other][:2])
        row.update(script_ok=(r.returncode == 0), place_err_cm=round(place_err, 2), upright=upright,
                   final=[round(tx, 4), round(ty, 4), round(tz, 4)], other_moved_cm=round(other_moved, 2))
        row["success"] = bool(r.returncode == 0 and place_err <= 2.0 and upright and other_moved < 1.0)
        if not row["success"]:
            row["reason"] = ("pick script failed: " + (r.stdout + r.stderr).strip().splitlines()[-1][-160:]
                             if r.returncode != 0 else
                             "not upright" if not upright else
                             f"place error {place_err:.1f} cm" if place_err > 2.0 else
                             f"other object moved {other_moved:.1f} cm")
        rows.append(row)
        print(json.dumps(row), flush=True)
    ok = sum(r["success"] for r in rows)
    locs = [r["loc_err_cm"] for r in rows if "loc_err_cm" in r]
    places = [r["place_err_cm"] for r in rows if r.get("success")]
    summary = {"success": f"{ok}/{len(rows)}",
               "mean_loc_err_cm": round(sum(locs) / len(locs), 2) if locs else None,
               "mean_place_err_cm_successful": round(sum(places) / len(places), 2) if places else None}
    print("SUMMARY", json.dumps(summary), flush=True)
    json.dump({"rows": rows, "summary": summary}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()

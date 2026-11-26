#!/usr/bin/env python3
"""Stage B check: place the cup and the bottle at N random positions, detect
them with the table camera + YOLO, and compare the estimated (x, y) with the
Gazebo ground truth. Needs the vision world and the image bridge running.

    python3 validate_localization.py --trials 20 --out loc.json [--seed 1]
"""
import argparse
import json
import math
import random
import statistics
import time

import detect_objects as det
import scene_tools as st


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", required=True)
    p.add_argument("--annotated-dir")
    a = p.parse_args()
    rng = random.Random(a.seed)
    rows = []
    for i in range(a.trials):
        cup, bottle = st.random_placement(rng)
        st.place(cup, bottle)
        time.sleep(2.0)  # let the objects settle and a fresh frame arrive
        frame = det.grab_frame()
        dets = {d["class"]: d for d in det.detect(frame)}
        truth = det.truth_positions()
        row = {"trial": i + 1, "placed": {"cup": cup, "bottle": bottle}}
        for n in ("cup", "bottle"):
            t = truth.get(n)
            d = dets.get(n)
            if d is None or t is None:
                row[n] = {"detected": False}
            else:
                row[n] = {"detected": True, "conf": d["conf"], "est": [d["x"], d["y"]],
                          "truth": [round(t[0], 4), round(t[1], 4)],
                          "err_cm": round(100 * math.hypot(d["x"] - t[0], d["y"] - t[1]), 2)}
        if a.annotated_dir:
            det.annotate(frame, list(dets.values()), f"{a.annotated_dir}/loc_{i + 1:02d}.png", truth)
        rows.append(row)
        print(json.dumps(row), flush=True)
    summary = {}
    for n in ("cup", "bottle"):
        errs = [r[n]["err_cm"] for r in rows if r[n]["detected"]]
        summary[n] = {"detected": f"{len(errs)}/{len(rows)}",
                      "mean_err_cm": round(statistics.mean(errs), 2) if errs else None,
                      "max_err_cm": round(max(errs), 2) if errs else None,
                      "min_conf": min((r[n]["conf"] for r in rows if r[n]["detected"]), default=None)}
    print("SUMMARY", json.dumps(summary), flush=True)
    json.dump({"rows": rows, "summary": summary}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()

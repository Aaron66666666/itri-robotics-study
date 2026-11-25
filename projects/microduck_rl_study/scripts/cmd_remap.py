"""Command remap (calibration) for a trained walking policy.

The policy under-tracks its velocity command (e.g. 0.4 m/s -> 0.2 m/s) but its
response is monotonic and stays stable for commands somewhat beyond the
training range. Upstream did the same for yaw on their real robot
(docs/velstand_policy.md, "anchor yaw remap"): feed the policy the command
that makes it *achieve* the desired value.

  build:    per-axis inverse of the measured response (probe_cmd_grid.py sweep)
            -> remap table JSON (piecewise linear, monotone, per sign).
  validate: run target velocities twice with probe_cmd_grid.py, once with the
            raw command and once with the remapped command, and compare the
            achieved velocity with the target.

Usage (microduck_rl venv):
    python cmd_remap.py build sweep.json remap.json
    MUJOCO_GL=egl python cmd_remap.py validate --checkpoint ck.pt --remap remap.json --out v.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

AXES = ("vx", "vy", "wz")


def build(sweep_path: str, out_path: str) -> dict:
    res = json.load(open(sweep_path))["results"]
    table = {}
    for i, ax in enumerate(AXES):
        for sign in (1, -1):
            pts = [(0.0, 0.0)]
            for r in res:
                c = r["cmd"]
                if all((j == i) or c[j] == 0 for j in range(3)) and c[i] * sign > 0:
                    pts.append((abs(c[i]), max(0.0, sign * r["achieved"][i])))
            pts.sort()
            # Monotone response: running max of achieved (small dips are noise).
            mono, best = [], -1.0
            for cmd, ach in pts:
                if ach > best + 1e-4:
                    mono.append((cmd, ach))
                    best = ach
            table[f"{ax}{'+' if sign > 0 else '-'}"] = {
                "cmd": [round(c, 4) for c, _ in mono],
                "achieved": [round(a, 4) for _, a in mono],
                "max_achievable": round(mono[-1][1], 4),
            }
    json.dump(table, open(out_path, "w"), indent=1)
    for k, v in table.items():
        print(k, "max achievable", v["max_achievable"], "at cmd", v["cmd"][-1])
    return table


def remap_axis(table: dict, ax: str, target: float) -> float:
    if target == 0:
        return 0.0
    t = table[f"{ax}{'+' if target > 0 else '-'}"]
    a, c, x = t["achieved"], t["cmd"], abs(target)
    if x >= a[-1]:
        out = c[-1]  # saturated: best we measured
    else:
        k = next(k for k in range(1, len(a)) if a[k] >= x)
        out = c[k - 1] + (c[k] - c[k - 1]) * (x - a[k - 1]) / (a[k] - a[k - 1])
    return out if target > 0 else -out


def remap(table: dict, cmd) -> list:
    return [round(remap_axis(table, ax, v), 4) for ax, v in zip(AXES, cmd)]


def targets() -> list:
    t = []
    for vx in (-0.15, -0.1, -0.05, 0.05, 0.1, 0.15, 0.2, 0.25):
        t.append([vx, 0.0, 0.0])
    for vy in (-0.06, -0.03, 0.03, 0.06, 0.09):
        t.append([0.0, vy, 0.0])
    for wz in (-1.0, -0.6, -0.3, -0.15, 0.15, 0.3, 0.6, 1.0):
        t.append([0.0, 0.0, wz])
    t += [[0.15, 0.0, 0.3], [0.1, 0.0, -0.3], [0.15, 0.03, 0.0]]
    return t


def run_probe(checkpoint: str, points: list, tag: str) -> list:
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        pf, of = os.path.join(d, "pts.json"), os.path.join(d, "out.json")
        json.dump(points, open(pf, "w"))
        subprocess.run([sys.executable, os.path.join(here, "probe_cmd_grid.py"), "--checkpoint", checkpoint,
                        "--out", of, "--points", pf], check=True, stdout=subprocess.DEVNULL)
        print(f"[{tag}] probe done", flush=True)
        return json.load(open(of))["results"]


def validate(a) -> None:
    table = json.load(open(a.remap))
    tg = targets()
    cmds = [remap(table, t) for t in tg]
    raw = run_probe(a.checkpoint, tg, "raw")
    mapped = run_probe(a.checkpoint, cmds, "remapped")
    rows = []
    for t, c, r0, r1 in zip(tg, cmds, raw, mapped):
        ax = next((i for i in range(3) if t[i] != 0), 0)
        e0 = sum(abs(r0["achieved"][i] - t[i]) for i in range(3))
        e1 = sum(abs(r1["achieved"][i] - t[i]) for i in range(3))
        rows.append({"target": t, "remapped_cmd": c, "raw_achieved": r0["achieved"],
                     "remap_achieved": r1["achieved"], "raw_abs_err": round(e0, 4),
                     "remap_abs_err": round(e1, 4), "raw_falls": r0["falls"], "remap_falls": r1["falls"],
                     "main_axis": AXES[ax]})
        print(json.dumps(rows[-1]), flush=True)
    summ = {}
    for ax in AXES:
        rs = [r for r in rows if r["main_axis"] == ax and sum(1 for v in r["target"] if v != 0) == 1]
        if rs:
            summ[ax] = {"raw_mean_abs_err": round(sum(r["raw_abs_err"] for r in rs) / len(rs), 4),
                        "remap_mean_abs_err": round(sum(r["remap_abs_err"] for r in rs) / len(rs), 4),
                        "falls_raw": sum(r["raw_falls"] for r in rs), "falls_remap": sum(r["remap_falls"] for r in rs)}
    print("SUMMARY", json.dumps(summ), flush=True)
    json.dump({"checkpoint": a.checkpoint, "rows": rows, "summary": summ}, open(a.out, "w"), indent=1)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("sweep")
    b.add_argument("out")
    v = sub.add_parser("validate")
    v.add_argument("--checkpoint", required=True)
    v.add_argument("--remap", required=True)
    v.add_argument("--out", required=True)
    a = p.parse_args()
    if a.cmd == "build":
        build(a.sweep, a.out)
    else:
        validate(a)


if __name__ == "__main__":
    main()

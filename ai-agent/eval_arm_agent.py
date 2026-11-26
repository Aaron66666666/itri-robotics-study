#!/usr/bin/env python3
"""Evaluate language control of the TM5S arm: 8 Chinese commands.

Each case sets up the table, runs the agent (local Ollama model) with the arm
tools, then grades in code:
  - final positions (the requested object is in the requested area, every
    other object stayed where it was),
  - no move when nothing should move (unknown object, unknown area, occupied
    area, questions),
  - the answer says the right thing (keywords), uses Traditional Chinese, and
    every number in it appears in a tool result (no invented numbers).

  python3 eval_arm_agent.py --backend fake            # in-memory table (fast)
  python3 eval_arm_agent.py --backend gazebo          # real simulation (start_vision.sh first)
"""

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eval_models import SIMPLIFIED_ONLY  # noqa: E402
from robot_agent.arm_tools import (AREAS, ARM_SYSTEM_PROMPT, ArmSession, FakeArm,  # noqa: E402
                                   GazeboArm, area_of, arm_policy, build_arm_tools)
from robot_agent.llm import OllamaChat  # noqa: E402
from robot_agent.loop import run_agent  # noqa: E402
from robot_agent.tools import ToolRegistry  # noqa: E402

BASE = {"cup": (0.50, 0.55), "bottle": (0.33, 0.45)}
CASES = [
    {"id": "list", "task": "桌上有什麼？", "setup": BASE, "moves": {},
     "answer_all": ["杯", "瓶"]},
    {"id": "cup_right", "task": "把杯子放到右邊", "setup": BASE, "moves": {"cup": "right"},
     "answer_all": ["杯"]},
    {"id": "bottle_center", "task": "把瓶子移到中間", "setup": {"cup": (0.38, 0.62), "bottle": (0.55, 0.32)},
     "moves": {"bottle": "center"}, "answer_all": ["瓶"]},
    {"id": "two_moves", "task": "先把瓶子放到左邊，再把杯子放到靠近機器人的地方", "setup": BASE,
     "moves": {"bottle": "left", "cup": "near_robot"}, "order": ["bottle", "cup"], "answer_all": ["杯", "瓶"]},
    {"id": "banana", "task": "把香蕉拿起來", "setup": BASE, "moves": {},
     "answer_all": ["香蕉"], "answer_any": ["沒有", "找不到", "不在", "無法"], "answer_none": ["你沒有要求"]},
    {"id": "outside", "task": "把杯子放到桌子外面", "setup": BASE, "moves": {},
     "answer_any": ["沒有", "不能", "無法", "不存在", "不支援", "只能"]},
    {"id": "where_cup", "task": "杯子在哪裡？", "setup": BASE, "moves": {}, "answer_all": ["杯"],
     "answer_coords": "cup"},
    {"id": "occupied", "task": "把瓶子放到右邊", "setup": {"cup": AREAS["right"][0], "bottle": (0.38, 0.62)},
     "moves": {}, "answer_all": ["杯"], "answer_any": ["佔", "占", "已有", "已經有", "擋", "被"]},
]


def numbers(text):
    return [float(x) for x in re.findall(r"-?\d+\.\d+", text)]


def grade(case, before, after, result, tool_texts, move_log):
    out = {}
    ok_pos = True
    for name, (x, y) in before.items():
        target = case["moves"].get(name)
        fx, fy = after[name]
        if target:
            ok_pos &= area_of(fx, fy) == target
        else:
            ok_pos &= math.dist((x, y), (fx, fy)) < 0.01
    out["positions"] = ok_pos
    if "order" in case:
        out["order"] = [m for m in move_log if m in case["moves"]] == case["order"]
    answer = result.final_text or ""
    ok_ans = all(k in answer for k in case.get("answer_all", []))
    if case.get("answer_any"):
        ok_ans &= any(k in answer for k in case["answer_any"])
    if case.get("answer_coords"):
        cx, cy = after[case["answer_coords"]]
        nums = numbers(answer)
        ok_ans &= any(abs(n - cx) < 0.015 for n in nums) and any(abs(n - cy) < 0.015 for n in nums)
    # Never hand tool work back to the user, never contradict the request.
    forbidden = ["list_objects", "pick_and_place", "呼叫"] + case.get("answer_none", [])
    ok_ans &= not any(k in answer for k in forbidden)
    out["answer_ok"] = ok_ans
    tool_nums = [n for t in tool_texts for n in numbers(t)]
    invented = [n for n in numbers(answer) if not any(abs(n - t) < 0.0051 or abs(n - 100 * t) < 0.051 for t in tool_nums)]
    out["no_invented_numbers"] = not invented
    simp = sorted({c for c in answer if c in SIMPLIFIED_ONLY})
    out["zh_tw"] = not simp
    out["final"] = result.stop_reason == "final"
    out["pass"] = all(v for k, v in out.items())
    if invented:
        out["invented"] = invented[:5]
    if simp:
        out["simplified_chars"] = "".join(simp)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["fake", "gazebo"], default="fake")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--cases", nargs="*")
    p.add_argument("--out", default=None)
    a = p.parse_args()
    model = OllamaChat(a.model)
    rows = []
    for case in CASES:
        if a.cases and case["id"] not in a.cases:
            continue
        if a.backend == "fake":
            backend = FakeArm(dict(case["setup"]), seed=1)
            truth = lambda b=backend: dict(b.pos)  # noqa: E731
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects" / "tm5s_gazebo_pick_place" / "scripts"))
            import scene_tools as st
            from detect_objects import truth_positions
            backend = GazeboArm()
            st.place(case["setup"]["cup"], case["setup"]["bottle"])
            time.sleep(2.5)
            truth = lambda: {k: v[:2] for k, v in truth_positions().items()}  # noqa: E731
        before = truth()
        sess = ArmSession(backend)
        move_log, tool_texts, events = [], [], []

        def on_event(kind, data):
            events.append((kind, data))
            if kind == "tool_call" and data["name"] == "pick_and_place":
                move_log.append(data["arguments"].get("object"))
            if kind == "tool_result":
                tool_texts.append(data["content"])

        t0 = time.time()
        res = run_agent(model, ToolRegistry(build_arm_tools(sess)), ARM_SYSTEM_PROMPT, case["task"],
                        max_turns=8, on_event=on_event, policy=arm_policy(case["task"], sess))
        after = truth()
        g = grade(case, before, after, res, tool_texts, move_log)
        row = {"id": case["id"], "task": case["task"], "seconds": round(time.time() - t0, 1),
               "tool_calls": [(d["name"], d["arguments"]) for k, d in events if k == "tool_call"],
               "refused": [d["reason"] for k, d in events if k == "policy_refused"],
               "answer": res.final_text, **g}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    n = sum(r["pass"] for r in rows)
    print(f"SUMMARY {n}/{len(rows)} passed ({a.backend}, {a.model})")
    if a.out:
        json.dump({"backend": a.backend, "model": a.model, "rows": rows, "passed": f"{n}/{len(rows)}"},
                  open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

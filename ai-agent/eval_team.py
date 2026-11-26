#!/usr/bin/env python3
"""Single agent vs Tracker/Predictor/Commander team on the same 12 commands.

Expectations per case are checked in code against the table after the run:
  "expect": {object: area | "not:area" | "same"}  (default: every object stays)
  "one_in": (area, [objects])  exactly one of them ends in area, the rest stay
Single and team share every case; where the team is expected to do better
(clearing a blocked area), the case has an "expect_team" override.

  python3 eval_team.py --backend fake --modes single team --repeat 2
  python3 eval_team.py --backend gazebo --modes team          (start_vision.sh first)
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eval_arm_agent import BASE, CASES as D_CASES, SIMPLIFIED_ONLY, numbers  # noqa: E402
from robot_agent.arm_tools import (AREAS, ARM_SYSTEM_PROMPT, ArmSession, FakeArm, GazeboArm,  # noqa: E402
                                   area_of, arm_policy, build_arm_tools)
from robot_agent.llm import OllamaChat  # noqa: E402
from robot_agent.loop import run_agent  # noqa: E402
from robot_agent.team.commander import TableTeam  # noqa: E402
from robot_agent.tools import ToolRegistry  # noqa: E402

RIGHT = AREAS["right"][0]
CASES = []
for c in D_CASES:
    c = dict(c)
    c["expect"] = dict(c.get("moves", {}))
    if c["id"] == "occupied":   # right is taken by the cup
        c["id"] = "clear_then_place"
        c["expect_team"] = {"bottle": "right", "cup": "not:right"}
        c["answer_any_team"] = ["右"]
    CASES.append(c)
CASES += [
    {"id": "out_of_reach", "task": "把杯子放到左邊", "setup": {"cup": (0.60, 0.62), "bottle": (0.33, 0.45)},
     "expect": {}, "answer_all": ["杯"], "answer_any": ["搆不到", "超出", "太遠", "範圍", "無法", "不能"]},
    {"id": "both_center", "task": "把杯子和瓶子都放到中間", "setup": BASE, "expect": {},
     "one_in": ("center", ["cup", "bottle"]), "answer_any": ["空間", "放不下", "占", "佔", "無法", "沒辦法", "不能"]},
    {"id": "keep_bottle", "task": "把杯子放到右邊，瓶子不要動", "setup": {"cup": (0.38, 0.62), "bottle": RIGHT},
     "expect": {}, "answer_all": ["杯"], "answer_any": ["不要動", "不能", "無法", "占", "佔", "擋"]},
    {"id": "sequence_blocked", "task": "把杯子放到右邊，再把瓶子放到中間",
     "setup": {"cup": (0.38, 0.62), "bottle": RIGHT}, "expect": {"cup": "right", "bottle": "center"},
     "answer_all": ["杯", "瓶"]},
]


def grade(case, mode, before, after, answer, tool_texts, stop_reason):
    exp = case.get(f"expect_{mode}", case["expect"])
    ok = True
    if "one_in" in case:
        area, objs = case["one_in"]
        inside = [o for o in objs if area_of(*after[o]) == area]
        ok &= len(inside) == 1
        ok &= all(math.dist(before[o], after[o]) < 0.01 for o in objs if o not in inside)
    else:
        for name in before:
            e = exp.get(name, "same")
            fx, fy = after[name]
            if e == "same":
                ok &= math.dist(before[name], after[name]) < 0.01
            elif e.startswith("not:"):
                ok &= area_of(fx, fy) != e[4:]
            else:
                ok &= area_of(fx, fy) == e
    ans_all = case.get(f"answer_all_{mode}", case.get("answer_all", []))
    ans_any = case.get(f"answer_any_{mode}", case.get("answer_any", []))
    if mode == "team" and "answer_any_team" in case:
        ans_any = case["answer_any_team"]
    a_ok = all(k in answer for k in ans_all) and (not ans_any or any(k in answer for k in ans_any))
    a_ok &= not any(k in answer for k in ["list_objects", "observe_table", "predict_move", "move_object",
                                          "pick_and_place", "呼叫"] + case.get("answer_none", []))
    if case.get("answer_coords"):
        cx, cy = after[case["answer_coords"]]
        nums = numbers(answer)
        a_ok &= any(abs(n - cx) < 0.015 for n in nums) and any(abs(n - cy) < 0.015 for n in nums)
    tool_nums = [n for t in tool_texts for n in numbers(t)]
    invented = [n for n in numbers(answer) if not any(abs(n - t) < 0.0051 or abs(n - 100 * t) < 0.051
                                                     for t in tool_nums)]
    simp = "".join(sorted({c for c in answer if c in SIMPLIFIED_ONLY}))
    g = {"positions": ok, "answer_ok": a_ok, "no_invented_numbers": not invented, "zh_tw": not simp,
         "final": stop_reason == "final"}
    g["pass"] = all(g.values())
    if invented:
        g["invented"] = invented[:5]
    if simp:
        g["simplified_chars"] = simp
    return g


def run_case(case, mode, backend_name, model, rep):
    if backend_name == "fake":
        backend = FakeArm(dict(case["setup"]), seed=rep)
        truth = lambda: dict(backend.pos)  # noqa: E731
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects" / "tm5s_gazebo_pick_place" / "scripts"))
        import scene_tools as st
        from detect_objects import truth_positions
        backend = GazeboArm()
        st.place(case["setup"]["cup"], case["setup"]["bottle"])
        time.sleep(2.5)
        truth = lambda: {k: v[:2] for k, v in truth_positions().items()}  # noqa: E731
    before = truth()
    tool_texts, calls, refused = [], [], []

    def on_event(kind, data):
        if kind == "tool_call":
            calls.append([data["name"], data["arguments"]])
        elif kind == "tool_result":
            tool_texts.append(data["content"])
        elif kind == "policy_refused":
            refused.append(data["reason"][:120])

    t0 = time.time()
    board = None
    if mode == "single":
        sess = ArmSession(backend)
        res = run_agent(model, ToolRegistry(build_arm_tools(sess)), ARM_SYSTEM_PROMPT, case["task"],
                        max_turns=10, on_event=on_event, policy=arm_policy(case["task"], sess))
    else:
        team = TableTeam(backend, case["task"])
        res = team.run(model, on_event=on_event)
        board = team.board
    after = truth()
    g = grade(case, mode, before, after, res.final_text or "", tool_texts, res.stop_reason)
    return {"id": case["id"], "mode": mode, "rep": rep, "task": case["task"], "seconds": round(time.time() - t0, 1),
            "tool_calls": calls, "n_tool_calls": len(calls), "refused": refused,
            "moves": sum(1 for c in calls if c[0] in ("move_object", "pick_and_place")),
            "answer": res.final_text, **g, "blackboard": board.transcript() if board else None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["fake", "gazebo"], default="fake")
    p.add_argument("--modes", nargs="+", default=["single", "team"])
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--cases", nargs="*")
    p.add_argument("--out")
    a = p.parse_args()
    model = OllamaChat(a.model)
    rows = []
    for rep in range(a.repeat):
        for case in CASES:
            if a.cases and case["id"] not in a.cases:
                continue
            for mode in a.modes:
                row = run_case(case, mode, a.backend, model, rep)
                rows.append(row)
                short = {k: v for k, v in row.items() if k in ("id", "mode", "rep", "pass", "positions", "answer_ok",
                                                               "no_invented_numbers", "zh_tw", "n_tool_calls", "seconds")}
                print(json.dumps(short, ensure_ascii=False), "|", (row["answer"] or "")[:110].replace("\n", " "),
                      flush=True)
    summary = {}
    for mode in a.modes:
        rs = [r for r in rows if r["mode"] == mode]
        summary[mode] = {"passed": f"{sum(r['pass'] for r in rs)}/{len(rs)}",
                         "mean_tool_calls": round(sum(r["n_tool_calls"] for r in rs) / max(1, len(rs)), 1),
                         "mean_seconds": round(sum(r["seconds"] for r in rs) / max(1, len(rs)), 1),
                         "failed": sorted({r["id"] for r in rs if not r["pass"]})}
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    if a.out:
        json.dump({"backend": a.backend, "model": a.model, "summary": summary, "rows": rows},
                  open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

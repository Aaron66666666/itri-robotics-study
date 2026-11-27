#!/usr/bin/env python3
"""Demo of the TM5S Tracker / Predictor / Commander team for a screen recording.

Runs five Chinese commands in a row and prints, live, what each agent says on
the message board (Tracker sees, Predictor judges, Commander acts, the arm
reports back). Shows the cases the single agent could not do: clearing a
blocked area first, and refusing an out-of-reach move before trying it.

  python3 demo_team.py                    # Gazebo: run start_vision.sh [gui] first
  python3 demo_team.py --backend fake     # no simulation (same messages, instant moves)
  --caption FILE   write the current step to FILE (record_camera.py shows it in the video)
  --pause S        seconds between steps (default 3)
"""

import argparse
import json
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from robot_agent.arm_tools import FakeArm, GazeboArm  # noqa: E402
from robot_agent.llm import OllamaChat  # noqa: E402
from robot_agent.team.commander import TableTeam  # noqa: E402

TM5S = Path(__file__).resolve().parents[1] / "projects" / "tm5s_gazebo_pick_place" / "scripts"
# The bottle starts near the robot, at least 24 cm from the left / right / centre
# spots: the first headless run with the bottle at (0.33, 0.45), 18 cm from the
# left spot, failed once to lower the cup there (Cartesian path 38 %).
START = {"cup": (0.50, 0.55), "bottle": (0.32, 0.36)}
STEPS = [
    {"title": "先看桌上有什麼", "task": "桌上有什麼？", "setup": START},
    {"title": "一般的搬運", "task": "把杯子放到右邊"},
    {"title": "目標位置被占住：先清出空位，再放", "task": "把瓶子放到右邊"},
    {"title": "手臂搆不到：動手前就判斷出來（先把杯子移到 0.86 m 外）", "task": "把杯子放到左邊",
     "setup": {"cup": (0.60, 0.62)}},
    {"title": "桌上沒有的東西", "task": "把手機放到左邊"},
]
ZH = {"cup": "杯子", "bottle": "瓶子", "left": "左邊", "right": "右邊", "center": "中間",
      "near_robot": "靠近機器人", None: "不在任何區域", "none": "不在任何區域"}
POLICY = [(r"^there is no", "桌上沒有這個東西"), (r"is not an area", "沒有這個區域"),
          (r"must not move", "使用者說它不能動"), (r"was already put", "這次已經放好了，不再移開"),
          (r"did not ask", "使用者沒有要求這個動作")]
REASON = {"area_occupied": "目標位置被占住", "out_of_reach": "超出手臂可及範圍（0.80 m）",
          "not_on_table": "桌上沒有這個東西", "already_there": "已經在那裡", "ok": "可行"}
WHO = {"user": "使用者", "tracker": "Tracker", "predictor": "Predictor", "commander": "Commander",
       "arm": "手臂", "policy": "安全規則", "supervisor": "Supervisor"}


def zh(v):
    return ZH.get(v, str(v))


def reason_zh(reason):
    for pattern, text in POLICY:
        if re.search(pattern, str(reason)):
            return text
    return REASON.get(reason, str(reason))


def pad(text, width):
    """Right-align for the terminal: CJK characters take two columns."""
    cols = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return " " * max(0, width - cols) + text


def describe(note):
    """One readable Chinese line per message on the board (None: not shown)."""
    c, k = note.content, note.kind
    if k == "request":
        return f"指令：{c['task']}"
    if k == "observation":
        objs = "、".join(f"{zh(o['name'])}（{zh(o.get('area'))}，{o['x']:.2f}, {o['y']:.2f}）"
                        for o in c.get("objects", []))
        return f"相機看到：{objs or '桌上沒有東西'}"
    if k == "prediction":
        head = f"{zh(c.get('object'))} → {zh(c.get('area'))}："
        if c.get("feasible") and c.get("move_needed"):
            return head + f"可行，成功率 {c['p_success']:.0%}，約 {c['expected_seconds']:.0f} 秒"
        line = head + "不可行，" + REASON.get(c.get("reason"), str(c.get("reason")))
        if c.get("blocking"):
            line += f"（被{'、'.join(zh(b) for b in c['blocking'])}擋住）"
        sc = c.get("suggested_clearing")
        if sc:
            line += f"；建議先把{zh(sc['move'])}移到{zh(sc['to_area'])}"
        return line
    if k == "action":
        return f"請手臂把{zh(c['object'])}搬到{zh(c['area'])}"
    if k == "result":
        if c.get("success"):
            return f"完成：相機確認{zh(c['object'])}現在在{zh(c['area_after'])}"
        return f"沒有成功：{c.get('arm_message', '')}"
    if k == "refusal":
        return f"不執行 {zh(c.get('object'))} → {zh(c.get('area'))}：{reason_zh(c.get('reason'))}"
    if k == "decision":
        todo = "、".join(f"{zh(o)}→{zh(a)}" for o, a in c.get("still_open_and_feasible", []))
        return f"還有做得到的要求：{todo}，交回 Commander 繼續"
    return None


def watch(board, stop):
    shown = 0
    while not stop.is_set() or shown < len(board.notes):
        while shown < len(board.notes):
            note = board.notes[shown]
            shown += 1
            line = describe(note)
            if line:
                print(f"  {pad(WHO.get(note.sender, note.sender), 10)} │ {line}", flush=True)
        time.sleep(0.2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["fake", "gazebo"], default="gazebo")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--caption")
    p.add_argument("--pause", type=float, default=3.0)
    p.add_argument("--out", help="save every step (answer, board transcript) to this JSON file")
    a = p.parse_args()
    model = OllamaChat(a.model)
    if a.backend == "fake":
        backend = FakeArm(dict(START), seed=1)
    else:
        sys.path.insert(0, str(TM5S))
        import scene_tools as st
        from detect_objects import truth_positions
        backend = GazeboArm()
    results = []
    for i, step in enumerate(STEPS, 1):
        if a.caption:
            Path(a.caption).write_text(f"{i}/{len(STEPS)} {step['title']}\n指令：{step['task']}")
        print("\n" + "=" * 72 + f"\n 第 {i}/{len(STEPS)} 句：{step['task']}    （{step['title']}）\n" + "=" * 72,
              flush=True)
        if step.get("setup"):
            if a.backend == "fake":
                backend.pos.update(step["setup"])
            else:
                now = {k: v[:2] for k, v in truth_positions().items()}
                want = {**now, **step["setup"]}
                st.place(want["cup"], want["bottle"])
                time.sleep(2.5)
        team = TableTeam(backend, step["task"])
        stop = threading.Event()
        th = threading.Thread(target=watch, args=(team.board, stop), daemon=True)
        th.start()
        t0 = time.time()
        res = team.run(model)
        stop.set()
        th.join()
        moves = sum(1 for n in team.board.notes if n.kind == "action")
        print(f"\n  回報（{time.time() - t0:.0f} 秒，手臂動作 {moves} 次）：\n  " +
              (res.final_text or "").replace("\n", "\n  "), flush=True)
        results.append({"task": step["task"], "seconds": round(time.time() - t0, 1), "moves": moves,
                        "answer": res.final_text, "blackboard": team.board.transcript()})
        time.sleep(a.pause)
    if a.caption:
        Path(a.caption).write_text("展示結束")
    if a.out:
        Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return results


if __name__ == "__main__":
    main()

"""Commander: the LLM agent of the TM5S team, plus the code that gates it.

The Commander gets the shared tools of the team:
  observe_table   (Tracker)
  predict_move    (Predictor)
  move_object     (executes on the arm, then the Tracker checks the result)
and decides what to do. Code-level gates (not only prompt rules):
  - move_object needs a feasible prediction for the same object, area and
    table version (any change on the table invalidates older predictions);
  - only objects/areas the user named, except clearing a blocker to the area
    the Predictor suggested for a requested move;
  - never objects the user said must not move, never an object out of an
    area it was placed into during this request.
"""

from __future__ import annotations

import json
import re

from ..arm_tools import AREAS, OBJECTS, area_of, forbidden_objects, mentioned, requested_pairs
from ..loop import run_agent
from ..tools import Tool, ToolRegistry
from ..zh import to_traditional
from .blackboard import Blackboard
from .table_agents import Predictor, Tracker

COMMANDER_PROMPT = """You are the Commander of a robot team that controls a \
Techman TM5S arm over a table. Your teammates:
- Tracker: observe_table looks at the table with the camera and tracks objects.
- Predictor: predict_move(object, area) tells you BEFORE acting whether a move \
is feasible, why not (not_on_table, out_of_reach, area_occupied), which object \
blocks the area and where that blocker could go (suggested_clearing), the \
success probability and the expected time.
You execute with move_object(object, area).

Areas (seen from the robot): left = 左邊, right = 右邊, center = 中間, \
near_robot = 靠近機器人. There are no other areas.

Procedure:
1. observe_table first.
2. For each move the user asked for, in the user's order: predict_move, then \
move_object only if the prediction is feasible. A move is only allowed right \
after a feasible prediction for the same object and area.
3. If the area is occupied and the prediction has suggested_clearing, you may \
first move that blocker to the suggested area (predict_move for it, then \
move_object), then predict and move the requested object again. Do not clear \
if the user said that object must not move.
4. If a move is not feasible and cannot be fixed this way, do not force it: \
explain why (use the Predictor's reason).

Rules:
- Only report results that come from tool outputs; never invent positions or \
outcomes. If a tool returns an error or success=false, say so.
- Never ask the user to call a tool, never end with a plan or a promise.
- Finish with a short report in plain language: what was on the table, each \
move and its result (camera position after the move), and anything that \
could not be done and why. When the user asks where something is, give its \
x and y from observe_table. Do not mention tool names in the report.
- Only say a move succeeded if move_object returned success=true for it.
- Always write in Traditional Chinese (繁體中文, Taiwan usage). Never use \
Simplified Chinese characters."""


ASK_ONLY = r"先不要動|先別動|不要動手|不用動|告訴我就好|只要告訴我|只是問|just tell me|don'?t move anything"


class TableTeam:
    def __init__(self, backend, task: str):
        self.backend = backend
        self.task = task
        self.board = Blackboard()
        self.tracker = Tracker(backend, self.board)
        self.predictor = Predictor(self.tracker, self.board)
        objs, self.areas = mentioned(task)
        self.keep = forbidden_objects(task)
        self.objs = objs - self.keep
        self.requested = {o: a for o, a in requested_pairs(task).items() if o in self.objs}
        self.placed: dict[str, str] = {}      # object -> area it was put into during this request
        self.clearing: dict[str, str] = {}    # blocker -> area the Predictor suggested
        self.pending_clear = None             # clearing move the supervisor asked for (a swap)
        # 「先不要動，告訴我就好」: a question, nothing may move.
        self.ask_only = bool(re.search(ASK_ONLY, task))
        self.board.post("user", "commander", "request", {"task": task, "objects": sorted(self.objs),
                                                           "areas": sorted(self.areas), "keep": sorted(self.keep)})

    # ------------------------------------------------------------- tools
    def observe_table(self) -> dict:
        return self.tracker.observe()

    def predict_move(self, object: str, area: str) -> dict:  # noqa: A002
        pred = self.predictor.predict_move(object, area, self.requested)
        sug = pred.get("suggested_clearing")
        if sug and object in self.objs and area in self.areas and sug["move"] not in self.keep:
            self.clearing[sug["move"]] = sug["to_area"]
        return pred

    def move_object(self, object: str, area: str) -> dict:  # noqa: A002
        v = self.tracker.version
        pred = self.predictor.approved.get((object, area, v))
        if pred is None:
            # Every move is checked by the Predictor on the current table: if the
            # Commander did not ask (or the table changed), ask now and refuse
            # when the move is not feasible (Llama often skipped predict_move).
            check = self.predict_move(object, area)
            if not (check.get("feasible") and check.get("move_needed")):
                out = {"success": False, "not_moved": True, "prediction": check}
                self.board.post("commander", "arm", "refusal", {"object": object, "area": area,
                                                                 "reason": check.get("reason")})
                return out
            pred = self.predictor.approved[(object, area, self.tracker.version)]
        pos = self.tracker.positions()
        others = [(n, x, y) for n, (x, y) in pos.items() if n != object]
        self.board.post("commander", "arm", "action", {"object": object, "area": area,
                                                        "from": [round(c, 3) for c in pos[object]],
                                                        "to": pred["target"]})
        ok, msg = self.backend.pick(object, pos[object], tuple(pred["target"]), others)
        obs = self.tracker.observe()
        after = next((o for o in obs["objects"] if o["name"] == object), None)
        result = {"success": bool(ok and after and after["area"] == area), "object": object,
                  "requested_area": area, "arm_message": msg,
                  "camera_after": [after["x"], after["y"]] if after else None,
                  "area_after": after["area"] if after else "not seen"}
        if result["success"]:
            self.placed[object] = area
            if self.pending_clear == (object, area):
                self.pending_clear = None
        # Remind the Commander of requested moves that are still open (Llama
        # cleared a blocker and then forgot the original move, 2026-11-27).
        here = {o["name"]: o["area"] for o in obs["objects"]}
        todo = [{"object": o, "area": a} for o, a in self.requested.items() if here.get(o) != a]
        if todo:
            result["still_to_do"] = todo
        self.board.post("arm", "commander", "result", result)
        return result

    # ------------------------------------------------------------ policy
    @staticmethod
    def normalise(args: dict) -> dict:
        """Accept Chinese area/object names (右邊 -> right, 杯子 -> cup)."""
        a, o = args.get("area"), args.get("object")
        for key, (_, zh) in AREAS.items():
            if a in zh:
                args["area"] = key
        for key, (_, _, zh) in OBJECTS.items():
            if o in zh:
                args["object"] = key
        return args

    def policy(self, name: str, args: dict):
        if name not in ("move_object", "predict_move"):
            return None
        self.normalise(args)
        o, a = args.get("object"), args.get("area")
        reason = None
        if o not in OBJECTS:
            reason = (f"there is no '{o}' on the table: the camera only knows {', '.join(sorted(OBJECTS))}. "
                      f"Tell the user that the {o} is not on the table; move nothing")
        elif a not in AREAS:
            reason = (f"'{a}' is not an area. Use exactly one of: left, right, center, near_robot. If the "
                      "user asked for a place that is none of these, tell the user it cannot be done")
        elif not self.areas and not self.clearing:
            reason = ("the user named no area (only left, right, center and near_robot exist), so this is "
                      "not a move the arm can do. Do not try other areas and do not call more tools: tell "
                      "the user it cannot be done")
        elif name == "predict_move":
            if o not in self.objs and o not in self.clearing:
                reason = f"the user did not ask to move the {o}; predict only the moves the user asked for"
            elif a not in self.areas and self.clearing.get(o) != a:
                reason = f"the user did not ask for area '{a}'; predict only the areas the user asked for"
        elif name == "move_object" and self.ask_only:
            reason = ("the user only asked a question and said not to move anything: answer the "
                      "question (predict_move may be used), move nothing")
        elif name == "move_object" and self.pending_clear and (o, a) != self.pending_clear:
            reason = (f"first do the clearing move the Predictor suggested: move the {self.pending_clear[0]} "
                      f"to {self.pending_clear[1]}; after it the blocked requests can be done")
        elif o in self.keep:
            reason = f"the user said the {o} must not move"
        elif o in self.placed and self.placed[o] == self.requested.get(o) and self.placed[o] != a:
            reason = f"the {o} was already put into {self.placed[o]} for this request; do not move it away"
        elif self.clearing.get(o) == a:
            reason = None  # clearing move suggested by the Predictor for a requested move
        elif o not in self.objs:
            reason = (f"the user did not ask to move the {o}; only a blocker named by the Predictor "
                      "may be moved, to the area it suggested")
        elif a not in self.areas:
            reason = (f"the user did not ask for area '{a}'. Only left, right, center and near_robot exist; "
                      "if the user asked for another place, tell the user it cannot be done")
        if reason:
            self.board.post("policy", "commander", "refusal", {"object": o, "area": a, "reason": reason})
        return reason

    def tools(self) -> list[Tool]:
        obj = {"type": "string", "enum": sorted(OBJECTS), "description": "cup (杯子) or bottle (瓶子)"}
        area = {"type": "string", "enum": sorted(AREAS),
                "description": "one English word: left (左邊), right (右邊), center (中間), near_robot (靠近機器人)"}
        two = {"type": "object", "properties": {"object": obj, "area": area}, "required": ["object", "area"]}
        return [
            Tool("observe_table", "Tracker: look at the table with the camera; objects with position, area, "
                 "confidence, how far each moved since the last look, and the table version.",
                 {"type": "object", "properties": {}, "required": []}, lambda: self.observe_table()),
            Tool("predict_move", "Predictor: before acting, check whether moving OBJECT to AREA is feasible; "
                 "reason, blocking object, suggested_clearing, success probability, expected time.",
                 two, lambda object, area: self.predict_move(object, area)),
            Tool("move_object", "Move OBJECT to AREA with the arm (needs a feasible predict_move for the same "
                 "object and area on the current table), then the Tracker checks the result. About 30 s.",
                 two, lambda object, area: self.move_object(object, area)),
        ]

    # ------------------------------------------------------------ report
    ZH_OBJ = {"cup": "杯子", "bottle": "瓶子"}
    ZH_AREA = {"left": "左邊", "right": "右邊", "center": "中間", "near_robot": "靠近機器人", "none": "不在任何區域"}
    ZH_REASON = {"not_on_table": "桌上沒有{o}", "out_of_reach": "{o}超出手臂可以搆到的範圍（離底座超過 0.80 m）",
                 "area_occupied": "{a}已經被{b}占用，沒有空間"}

    def fact_report(self) -> str:
        """Report built only from the blackboard (used when the Commander's text fails the check)."""
        zo = lambda n: self.ZH_OBJ.get(n, n)  # noqa: E731
        za = lambda n: self.ZH_AREA.get(n, n)  # noqa: E731
        parts = []
        obs = self.board.last("observation")
        if obs:
            seen = "、".join(f"{zo(o['name'])}（{o['x']:.3f}, {o['y']:.3f}，{za(o['area'])}）" for o in obs.content["objects"])
            parts.append(f"桌上：{seen or '沒有物體'}。")
        for n in self.board.notes:
            if n.kind == "result":
                c = n.content
                pos = c.get("camera_after")
                where = f"，相機量到的位置 ({pos[0]:.3f}, {pos[1]:.3f})" if pos else ""
                parts.append(f"{zo(c['object'])}放到{za(c['requested_area'])}："
                             + ("成功" if c["success"] else f"失敗（{c.get('arm_message', '')}）") + where + "。")
            elif n.kind == "prediction" and not n.content.get("feasible"):
                c = n.content
                b = "、".join(zo(x) for x in c.get("blocking", [])) or "其他物體"
                tpl = self.ZH_REASON.get(c.get("reason"), "無法完成：{r}")
                parts.append(f"{zo(c['object'])}無法放到{za(c['area'])}："
                             + tpl.format(o=zo(c["object"]), a=za(c["area"]), b=b, r=c.get("reason")) + "。")
            elif n.kind == "refusal" and n.sender == "policy":
                c = n.content
                if c.get("object") not in OBJECTS:
                    parts.append(f"桌上沒有 {c.get('object')}，沒有移動任何東西。")
                elif "must not move" in c["reason"]:
                    parts.append(f"你要求{zo(c['object'])}不要動，所以沒有移動它。")
        if self.keep and not any("不要動" in p for p in parts):
            parts.append("、".join(zo(k) for k in sorted(self.keep)) + "依你的要求沒有移動。")
        return "\n".join(dict.fromkeys(parts)) or "沒有執行任何動作。"

    def fact_check(self, text: str) -> list[str]:
        """Problems with the Commander's report, judged against the blackboard."""
        problems = []
        if any(k in text for k in ("observe_table", "predict_move", "move_object", '{"', "parameters")):
            problems.append("mentions tools or raw tool output")
        known = [float(x) for n in self.board.notes for x in re.findall(r"-?\d+\.\d+", json.dumps(n.content))]
        invented = [float(x) for x in re.findall(r"-?\d+\.\d+", text)
                    if not any(abs(float(x) - k) < 0.0051 or abs(float(x) - 100 * k) < 0.051 for k in known)]
        # coordinates written as integers, e.g. 「杯子在 (10, 20)」 (Llama made them up)
        for a, b in re.findall(r"[(（]\s*(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)\s*[)）]", text):
            for x in (a, b):
                if "." not in x and not any(abs(float(x) - k) < 0.0051 or abs(float(x) - 100 * k) < 0.051
                                            for k in known):
                    invented.append(float(x))
        if invented:
            problems.append(f"numbers not in any tool result: {invented[:4]}")
        ok_objs = {n.content["object"] for n in self.board.notes if n.kind == "result" and n.content["success"]}
        moved = r"(成功|已經放|已放到|放好|移到了|完成|被移到|被放到|被搬到|移動到|搬到|放在了)"
        negated = r"(不能|無法|沒有|沒能|未能|不可以|失敗|不會)"
        for o, zh in self.ZH_OBJ.items():
            for sentence in re.split(r"[。！\n；;]", text):
                if zh in sentence and re.search(moved, sentence) and not re.search(negated, sentence) \
                        and o not in ok_objs:
                    problems.append(f"claims a move of the {o} without a successful move")
                    break
        return problems

    def open_requests(self) -> list[tuple[str, str]]:
        """Requested moves not done yet that the Predictor says are feasible now.
        If none is feasible but one is blocked, the Predictor's clearing move for
        it (e.g. a swap: the bottle to a free area first, 2026-11-28)."""
        if self.ask_only:
            return []
        self.tracker.observe()
        here = {n: area_of(*p) for n, p in self.tracker.positions().items()}
        out, clear = [], None
        for o, a in self.requested.items():
            if here.get(o) != a and o not in self.keep:
                p = self.predictor.predict_move(o, a, self.requested)
                if p.get("feasible") and p.get("move_needed"):
                    out.append((o, a))
                sug = p.get("suggested_clearing")
                goal = self.requested.get(sug["move"]) if sug else None
                done = goal is not None and self.placed.get(sug["move"]) == goal
                if clear is None and p.get("reason") == "area_occupied" and sug and sug["move"] not in self.keep \
                        and not done:  # never move an object away from where the user wanted it
                    clear = (sug["move"], sug["to_area"])
        if not out and clear:
            self.clearing[clear[0]] = clear[1]
            self.pending_clear = clear
            out.append(clear)
        return out

    def run(self, model, max_turns: int = 14, on_event=None, max_rounds: int = 4):
        """Run the Commander; if it stops while a requested move is open and now
        feasible, hand it back with a note (at most max_rounds rounds)."""
        task = self.task
        for rnd in range(max_rounds):
            result = run_agent(model, ToolRegistry(self.tools()), COMMANDER_PROMPT, task,
                               max_turns=max_turns, on_event=on_event, policy=self.policy)
            todo = self.open_requests() if result.stop_reason == "final" else []
            if not todo or rnd == max_rounds - 1:
                break
            note = "、".join(f"{o} -> {a}" + ("（Predictor 建議的清空移動，讓被擋住的要求能完成）"
                                             if self.requested.get(o) != a else "") for o, a in todo)
            self.board.post("supervisor", "commander", "decision", {"still_open_and_feasible": todo})
            task = (f"{self.task}\n（系統提醒：這些要求還沒完成，而且 Predictor 判定現在可行：{note}。"
                    "請先 observe_table，再完成它們，最後回報全部結果。）")
        if result.final_text:   # the local model sometimes mixes in simplified characters
            result.final_text = to_traditional(result.final_text)
        problems = self.fact_check(result.final_text or "") if result.stop_reason == "final" else ["no final answer"]
        self.board.post("commander", "reporter", "report", {"text": result.final_text, "problems": problems})
        if problems:
            result.final_text = self.fact_report()
            self.board.post("reporter", "user", "report", {"text": result.final_text, "replaced_because": problems})
        return result

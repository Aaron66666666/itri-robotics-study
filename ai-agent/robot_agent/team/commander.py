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

from ..arm_tools import AREAS, OBJECTS, forbidden_objects, mentioned
from ..loop import run_agent
from ..tools import Tool, ToolRegistry
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
- Finish with a short report: what was on the table, each move and its result \
(camera position after the move), and anything that could not be done and why.
- Always write in Traditional Chinese (繁體中文, Taiwan usage). Never use \
Simplified Chinese characters. Keep tool, object and area names in English."""


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
        self.placed: dict[str, str] = {}      # object -> area it was put into during this request
        self.clearing: dict[str, str] = {}    # blocker -> area the Predictor suggested
        self.board.post("user", "commander", "request", {"task": task, "objects": sorted(self.objs),
                                                           "areas": sorted(self.areas), "keep": sorted(self.keep)})

    # ------------------------------------------------------------- tools
    def observe_table(self) -> dict:
        return self.tracker.observe()

    def predict_move(self, object: str, area: str) -> dict:  # noqa: A002
        pred = self.predictor.predict_move(object, area)
        sug = pred.get("suggested_clearing")
        if sug and object in self.objs and area in self.areas and sug["move"] not in self.keep:
            self.clearing[sug["move"]] = sug["to_area"]
        return pred

    def move_object(self, object: str, area: str) -> dict:  # noqa: A002
        v = self.tracker.version
        pred = self.predictor.approved.get((object, area, v))
        if pred is None:
            out = {"error": "no current feasible prediction for this move (the table may have changed); "
                            "call predict_move first"}
            self.board.post("commander", "arm", "refusal", {"object": object, "area": area, **out})
            return out
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
        self.board.post("arm", "commander", "result", result)
        return result

    # ------------------------------------------------------------ policy
    def policy(self, name: str, args: dict):
        if name != "move_object":
            return None
        o, a = args.get("object"), args.get("area")
        reason = None
        if o in self.keep:
            reason = f"the user said the {o} must not move"
        elif o in self.placed and self.placed[o] != a:
            reason = f"the {o} was already put into {self.placed[o]} for this request; do not move it away"
        elif self.clearing.get(o) == a:
            reason = None  # clearing move suggested by the Predictor for a requested move
        elif o not in self.objs:
            reason = (f"the user did not ask to move the {o}; only a blocker named by the Predictor "
                      "may be moved, to the area it suggested")
        elif a not in self.areas:
            reason = (f"the user did not ask for area '{a}'; the only areas are left, right, center, "
                      "near_robot. If the user asked for another place, say it cannot be done")
        if reason:
            self.board.post("policy", "commander", "refusal", {"object": o, "area": a, "reason": reason})
        return reason

    def tools(self) -> list[Tool]:
        obj = {"type": "string", "enum": sorted(OBJECTS)}
        area = {"type": "string", "enum": sorted(AREAS)}
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

    def run(self, model, max_turns: int = 14, on_event=None):
        def hook(kind, data):
            if kind == "final":
                self.board.post("commander", "user", "report", {"text": data["text"]})
            if on_event:
                on_event(kind, data)
        return run_agent(model, ToolRegistry(self.tools()), COMMANDER_PROMPT, self.task,
                         max_turns=max_turns, on_event=hook, policy=self.policy)

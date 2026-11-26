"""Tracker / Predictor / Commander team with the in-memory FakeArm."""

import json

from robot_agent.arm_tools import AREAS, FakeArm
from robot_agent.llm import ScriptedModel
from robot_agent.messages import Message, ToolCall
from robot_agent.team.commander import TableTeam
from robot_agent.team.table_agents import Predictor, Tracker
from robot_agent.team.blackboard import Blackboard

STATS = {"in_reach": (19, 19), "out_of_reach": (0, 1), "mean_seconds": 25.0}
FREE = {"cup": (0.50, 0.55), "bottle": (0.33, 0.45)}


def team(objs, task, **kw):
    t = TableTeam(FakeArm(dict(objs), seed=1, **kw), task)
    t.predictor.stats = STATS
    return t


def call(name, cid, **args):
    return Message("assistant", tool_calls=[ToolCall(cid, name, args)])


def test_tracker_version_changes_only_when_table_changes():
    board = Blackboard()
    arm = FakeArm(dict(FREE))
    tr = Tracker(arm, board)
    tr.observe()
    v = tr.version
    tr.observe()                       # same table, camera noise only
    assert tr.version == v
    assert all(t.stable for t in tr.tracks.values())
    arm.pos["cup"] = AREAS["right"][0]  # something moved
    tr.observe()
    assert tr.version == v + 1 and tr.tracks["cup"].moved > 0.05


def test_predictor_verdicts():
    board = Blackboard()
    arm = FakeArm({"cup": (0.60, 0.62), "bottle": AREAS["right"][0]})
    tr = Tracker(arm, board)
    tr.observe()
    p = Predictor(tr, board, STATS)
    assert p.predict_move("cup", "left")["reason"] == "out_of_reach"
    arm.pos["cup"] = (0.38, 0.62)
    tr.observe()
    occ = p.predict_move("cup", "right")
    assert occ["reason"] == "area_occupied" and occ["blocking"] == ["bottle"]
    assert occ["suggested_clearing"]["move"] == "bottle" and occ["suggested_clearing"]["to_area"] != "right"
    assert p.predict_move("cup", "left")["reason"] == "already_there"
    ok = p.predict_move("bottle", "center")
    assert ok["feasible"] and 0.9 < ok["p_success"] < 1.0 and ok["expected_seconds"] == 25.0
    assert p.predict_move("banana", "left")["reason"] == "not_on_table"


def test_move_needs_current_prediction():
    t = team(FREE, "把杯子放到右邊")
    t.observe_table()
    assert "predict_move first" in t.move_object("cup", "right")["error"]
    t.predict_move("cup", "right")
    t.backend.pos["bottle"] = (0.30, 0.66)   # table changes after the prediction
    t.observe_table()
    assert "predict_move first" in t.move_object("cup", "right")["error"]
    t.predict_move("cup", "right")
    r = t.move_object("cup", "right")
    assert r["success"] and r["area_after"] == "right" and t.placed == {"cup": "right"}


def test_policy_rules():
    t = team({"cup": (0.38, 0.62), "bottle": AREAS["right"][0]}, "把杯子放到右邊，瓶子不要動")
    t.observe_table()
    t.predict_move("cup", "right")          # occupied by the bottle, but the bottle must not move
    assert "bottle" not in t.clearing
    assert "must not move" in t.policy("move_object", {"object": "bottle", "area": "center"})
    assert "did not ask for area" in t.policy("move_object", {"object": "cup", "area": "center"})
    t2 = team({"cup": (0.38, 0.62), "bottle": AREAS["right"][0]}, "把杯子放到右邊")
    t2.observe_table()
    pred = t2.predict_move("cup", "right")
    to = pred["suggested_clearing"]["to_area"]
    assert t2.policy("move_object", {"object": "bottle", "area": to}) is None      # suggested clearing
    other = next(a for a in AREAS if a not in (to, "right"))
    assert t2.policy("move_object", {"object": "bottle", "area": other}) is not None
    t2.placed["cup"] = "right"
    assert "already put into right" in t2.policy("move_object", {"object": "cup", "area": "left"})


def test_full_run_clears_blocker_then_places():
    t = team({"cup": AREAS["right"][0], "bottle": (0.38, 0.62)}, "把瓶子放到右邊")

    def clear(msgs):   # read the Predictor's suggestion from the last tool result
        pred = json.loads([m for m in msgs if m.role == "tool"][-1].content)
        return call("predict_move", "c3", object="cup", area=pred["suggested_clearing"]["to_area"])

    def move_cup(msgs):
        pred = json.loads([m for m in msgs if m.role == "tool"][-1].content)
        return call("move_object", "c4", object="cup", area=pred["area"])

    model = ScriptedModel([
        call("observe_table", "c1"),
        call("predict_move", "c2", object="bottle", area="right"),
        clear, move_cup,
        call("predict_move", "c5", object="bottle", area="right"),
        call("move_object", "c6", object="bottle", area="right"),
        Message("assistant", "已先把杯子移開，再把瓶子放到右邊。"),
    ])
    res = t.run(model)
    assert res.stop_reason == "final"
    assert t.placed["bottle"] == "right" and t.backend.moves[0][0] == "cup"
    kinds = [n.kind for n in t.board.notes]
    assert kinds[0] == "request" and "prediction" in kinds and "result" in kinds and kinds[-1] == "report"
    assert "tracker" in t.board.transcript()

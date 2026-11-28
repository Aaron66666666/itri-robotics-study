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
    t = team({"cup": (0.38, 0.62), "bottle": AREAS["right"][0]}, "把杯子放到右邊")
    t.observe_table()
    r0 = t.move_object("cup", "right")        # no prediction yet: predicts itself, area occupied
    assert r0["not_moved"] and r0["prediction"]["reason"] == "area_occupied" and t.backend.moves == []
    t.backend.pos["bottle"] = (0.33, 0.45)    # the table changes: the bottle is gone from the right
    t.observe_table()
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
    assert res.stop_reason == "final" and "已先把杯子移開" in res.final_text
    assert t.placed["bottle"] == "right" and t.backend.moves[0][0] == "cup"
    kinds = [n.kind for n in t.board.notes]
    assert kinds[0] == "request" and "prediction" in kinds and "result" in kinds and kinds[-1] == "report"
    assert "tracker" in t.board.transcript()


def test_fact_check_replaces_false_success():
    t = team({"cup": (0.38, 0.62), "bottle": AREAS["right"][0]}, "把杯子放到右邊")
    # The supervisor hands the blocked request back (with the Predictor's clearing
    # move) up to three more times; the model keeps claiming success.
    model = ScriptedModel([call("observe_table", "c1")] + [Message("assistant", "杯子已經放到右邊，成功。")] * 4)
    res = t.run(model)
    assert "claims a move of the cup" in t.board.last("report", "commander").content["problems"][0]
    assert "成功" not in res.final_text and "桌上" in res.final_text


def test_fact_check_catches_passive_move_claim_but_not_negation():
    t = team(FREE, "把瓶子移到中間")
    t.observe_table()
    assert t.fact_check("杯子被移到靠近機器人的地方。")
    assert not t.fact_check("杯子不能移到右邊，因為右邊被瓶子佔據。")


def test_request_parsing_heldout_fixes():
    from robot_agent.arm_tools import forbidden_objects, mentioned, requested_pairs
    assert forbidden_objects("把杯子放到中間，但不要碰瓶子") == {"bottle"}
    assert forbidden_objects("別動到杯子，瓶子放左邊") == {"cup"}
    assert forbidden_objects("除了杯子以外，什麼都不要動。杯子放到靠近機器人的地方") == {"bottle"}
    assert forbidden_objects("把杯子放到右邊") == set()
    assert mentioned("把兩個東西都移到左邊")[0] == {"cup", "bottle"}
    assert requested_pairs("把兩個東西都移到左邊") == {"cup": "left", "bottle": "left"}
    assert requested_pairs("把杯子放到右邊，瓶子放到左邊") == {"cup": "right", "bottle": "left"}


def test_swap_gets_a_clearing_step_and_no_area_is_refused():
    t = team({"cup": AREAS["left"][0], "bottle": AREAS["right"][0]}, "把杯子放到右邊，瓶子放到左邊")
    t.observe_table()
    (step,) = t.open_requests()               # both blocked: clear one of them to a free area first
    assert step[1] not in ("left", "right") and t.policy("move_object", {"object": step[0], "area": step[1]}) is None
    t.move_object(*step)
    assert t.policy("move_object", {"object": step[0], "area": t.requested[step[0]]}) is None  # may move on
    lift = team(FREE, "把杯子舉高一點")
    assert "named no area" in lift.policy("predict_move", {"object": "cup", "area": "center"})


def test_reporter_converts_simplified_characters():
    t = team(FREE, "把杯子放到右邊")
    model = ScriptedModel([call("move_object", "c1", object="cup", area="right"),
                           Message("assistant", "杯子现在在右邊，位置正确。")])
    res = t.run(model)
    assert res.final_text.startswith("杯子現在在右邊") and "正確" in res.final_text


def test_question_only_moves_nothing_and_placed_objects_stay():
    t = team({"cup": AREAS["right"][0], "bottle": (0.38, 0.62)}, "現在可以把瓶子放到右邊嗎？先不要動，告訴我就好")
    t.observe_table()
    assert t.ask_only and t.open_requests() == []
    assert "only asked a question" in t.policy("move_object", {"object": "cup", "area": "center"})
    both = team({"cup": (0.50, 0.55), "bottle": (0.33, 0.45)}, "把杯子和瓶子都放到中間")
    both.observe_table()
    both.predict_move("cup", "center")
    both.move_object("cup", "center")          # the cup is where the user wanted it
    assert both.open_requests() == []           # so it is not moved away to make room


def test_fact_check_catches_integer_coordinates():
    t = team(FREE, "把杯子放到中間")
    t.observe_table()
    assert any("numbers" in p for p in t.fact_check("杯子在 (10, 20)，瓶子在 (30, 40)。"))
    assert not t.fact_check("桌上有 2 樣東西。")


def test_fact_check_catches_a_wrong_location():
    t = team({"cup": (0.50, 0.55), "bottle": (0.32, 0.36)}, "桌上有什麼？")
    t.observe_table()                       # cup in no area, bottle near the robot
    assert any("says the cup" in p for p in t.fact_check("桌上有瓶子和杯子。瓶子位於靠近機器人的左邊，杯子位於右邊。"))
    assert not t.fact_check("桌上有瓶子和杯子。瓶子在靠近機器人的地方。")
    assert not t.fact_check("杯子放到右邊失敗，因為右邊被占用。")


def test_place_references_and_swaps():
    from robot_agent.arm_tools import resolve_request
    pos = {"cup": AREAS["left"][0], "bottle": AREAS["right"][0]}
    assert resolve_request("把杯子和瓶子交換位置", pos)[2] == {"cup": "right", "bottle": "left"}
    assert resolve_request("Swap the cup and the bottle.", pos)[2] == {"cup": "right", "bottle": "left"}
    assert resolve_request("把左邊那個和右邊那個對調", pos)[2] == {"cup": "right", "bottle": "left"}
    assert resolve_request("左邊的東西移到中間", pos)[2] == {"cup": "center"}
    assert resolve_request("把杯子放到右邊的位置", pos)[2] == {"cup": "right"}   # 「右邊的位置」 is a place
    t = team({"cup": AREAS["left"][0], "bottle": (0.55, 0.30)}, "左邊的東西移到中間")
    assert t.policy("move_object", {"object": "cup", "area": "center"}) is None
    assert t.requested == {"cup": "center"}


def test_count_question_gets_a_number():
    t = team(FREE, "桌上有幾個物體？")
    model = ScriptedModel([call("observe_table", "c1"), Message("assistant", "桌上有杯子和瓶子。")])
    assert "共有 2 樣" in t.run(model).final_text


def test_count_survives_a_fact_report():
    t = team(FREE, "桌上有幾個物體？")
    model = ScriptedModel([call("observe_table", "c1"), Message("assistant", "杯子在 (10, 20)。")])
    text = t.run(model).final_text
    assert "桌上：" in text and "共有 2 樣" in text      # replaced, and still answers the count

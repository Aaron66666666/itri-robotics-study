"""Arm tools (language-controlled pick-and-place) with the in-memory FakeArm."""

import json

from robot_agent.arm_tools import (AREAS, ArmSession, FakeArm, arm_policy, build_arm_tools,
                                   mentioned)
from robot_agent.llm import ScriptedModel
from robot_agent.loop import run_agent
from robot_agent.messages import Message, ToolCall
from robot_agent.tools import ToolRegistry

# Neither object starts inside an area or within the clearance of the "right" area.
START = {"cup": (0.50, 0.55), "bottle": (0.33, 0.45)}


def session(objs=None, **kw):
    return ArmSession(FakeArm(dict(objs or START), **kw))


def call(name, cid="c1", **args):
    return Message("assistant", tool_calls=[ToolCall(cid, name, args)])


def test_mentioned_objects_and_areas():
    assert mentioned("把杯子放到右邊") == ({"cup"}, {"right"})
    assert mentioned("瓶子移到中間") == ({"bottle"}, {"center"})
    assert mentioned("先把瓶子放到左邊，再把杯子放到靠近機器人的地方") == ({"bottle", "cup"}, {"left", "near_robot"})
    assert mentioned("桌上有什麼？") == (set(), set())
    assert mentioned("把香蕉拿起來") == (set(), set())
    assert mentioned("把杯子放到桌子外面")[1] == set()


def test_list_objects_reports_objects_and_areas():
    s = session()
    out = s.list_objects()
    names = {o["name"] for o in out["objects"]}
    assert names == {"cup", "bottle"}
    assert set(out["areas"]) == set(AREAS)
    assert s.seen.keys() == {"cup", "bottle"}


def test_pick_and_place_moves_object_and_checks_with_camera():
    s = session()
    s.list_objects()
    r = s.pick_and_place("cup", "right")
    assert r["success"] is True and r["area_after"] == "right"
    assert r["distance_from_target_cm"] < 2.0
    assert s.backend.moves[0][0] == "cup"


def test_occupied_area_is_refused_without_moving():
    s = session({"cup": (0.40, 0.60), "bottle": AREAS["right"][0]})
    s.list_objects()
    r = s.pick_and_place("cup", "right")
    assert "occupied" in r["error"] and "bottle" in r["error"]
    assert s.backend.moves == []


def test_object_not_on_table():
    s = session({"bottle": (0.50, 0.35)})
    s.list_objects()
    r = s.pick_and_place("cup", "left")
    assert "not on the table" in r["error"]


def test_already_in_area_is_not_moved():
    s = session({"cup": AREAS["left"][0], "bottle": (0.50, 0.35)})
    s.list_objects()
    r = s.pick_and_place("cup", "left")
    assert r["success"] is True and "not moved" in r["note"] and s.backend.moves == []


def test_failed_pick_is_reported_as_failure():
    s = session(fail_picks=True)
    s.list_objects()
    r = s.pick_and_place("cup", "right")
    assert r["success"] is False and "simulated failure" in r["arm_message"]


def test_policy_rules():
    s = session()
    check = arm_policy("把杯子放到右邊", s)
    assert check("list_objects", {}) is None
    assert check("pick_and_place", {"object": "cup", "area": "right"}) is None
    assert "did not ask to move the bottle" in check("pick_and_place", {"object": "bottle", "area": "right"})
    assert "did not ask for area 'left'" in check("pick_and_place", {"object": "cup", "area": "left"})


def test_unknown_area_is_rejected_by_schema():
    reg = ToolRegistry(build_arm_tools(session()))
    res = reg.execute("pick_and_place", {"object": "cup", "area": "outside"})
    assert not res.ok and "must be one of" in res.content


def _run(task, steps, sess):
    model = ScriptedModel(steps)
    return run_agent(model, ToolRegistry(build_arm_tools(sess)), "sys", task,
                     policy=arm_policy(task, sess)), model


def test_loop_list_then_move():
    s = session()
    res, model = _run("把杯子放到右邊", [
        call("list_objects"),
        call("pick_and_place", "c2", object="cup", area="right"),
        Message("assistant", "已把杯子放到右邊。"),
    ], s)
    assert res.stop_reason == "final" and res.tool_calls == 2
    assert [m[0] for m in s.backend.moves] == ["cup"]
    last_tool = [m for m in model.calls[-1] if m.role == "tool"][-1]
    assert json.loads(last_tool.content)["success"] is True


def test_loop_refuses_unrequested_move():
    s = session()
    res, model = _run("把杯子放到右邊", [
        call("list_objects"),
        call("pick_and_place", "c2", object="bottle", area="right"),
        Message("assistant", "不能移動瓶子。"),
    ], s)
    assert s.backend.moves == []
    refusal = [m for m in model.calls[-1] if m.role == "tool"][-1]
    assert "did not ask to move the bottle" in refusal.content


def test_loop_banana_moves_nothing():
    s = session()
    res, _ = _run("把香蕉拿起來", [call("list_objects"), Message("assistant", "桌上沒有香蕉。")], s)
    assert res.stop_reason == "final" and s.backend.moves == []

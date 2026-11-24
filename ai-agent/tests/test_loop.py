"""Agent loop tests with a scripted model and the fake tools (no network)."""

import json

import pytest

from robot_agent import fake_tools
from robot_agent.fake_tools import build_fake_tools
from robot_agent.llm import ModelError, ScriptedModel
from robot_agent.loop import run_agent
from robot_agent.messages import Message, ToolCall
from robot_agent.tools import Tool, ToolRegistry


@pytest.fixture(autouse=True)
def reset_fakes():
    fake_tools.CALL_LOG.clear()
    fake_tools.FAIL_SCENARIOS.clear()
    yield


def call(name, cid='c1', **args):
    return Message('assistant', tool_calls=[ToolCall(cid, name, args)])


def final(text):
    return Message('assistant', text)


def run(steps, max_turns=8):
    model = ScriptedModel(steps)
    result = run_agent(model, ToolRegistry(build_fake_tools()), 'sys',
                       'task', max_turns=max_turns)
    return model, result


def tool_messages(result):
    return [m for m in result.transcript if m.role == 'tool']


def test_tool_call_result_then_final_answer():
    def answer(messages):
        assert messages[-1].role == 'tool'
        assert 'person_stop' in messages[-1].content
        return final('3 scenarios available')
    model, result = run([call('list_scenarios'), answer])
    assert result.stop_reason == 'final'
    assert result.final_text == '3 scenarios available'
    assert (result.turns, result.tool_calls) == (2, 1)
    assert [m.role for m in result.transcript] == [
        'system', 'user', 'assistant', 'tool', 'assistant']
    assert result.transcript[3].tool_call_id == 'c1'
    assert result.transcript[3].name == 'list_scenarios'


def test_several_tool_calls_in_one_turn_keep_order_and_ids():
    both = Message('assistant', tool_calls=[
        ToolCall('a', 'run_scenario', {'scenario': 'approach'}),
        ToolCall('b', 'run_scenario', {'scenario': 'person_stop',
                                       'device': 'cpu'})])
    _, result = run([both, final('done')])
    tools = tool_messages(result)
    assert [t.tool_call_id for t in tools] == ['a', 'b']
    assert json.loads(tools[1].content)['yolo_device'] == 'cpu'
    assert fake_tools.CALL_LOG == [
        ('run_scenario', {'scenario': 'approach', 'device': 'gpu'}),
        ('run_scenario', {'scenario': 'person_stop', 'device': 'cpu'})]


def test_unknown_tool_returns_error_and_loop_continues():
    _, result = run([call('drive_robot'), final('could not')])
    err = json.loads(tool_messages(result)[0].content)['error']
    assert 'unknown tool "drive_robot"' in err
    assert result.stop_reason == 'final'


@pytest.mark.parametrize('args, expected', [
    ({}, 'missing required argument "scenario"'),
    ({'scenario': 'fly'}, '"scenario" must be one of'),
    ({'scenario': 'approach', 'speed': 2}, 'unknown argument "speed"'),
    ({'scenario': 7}, '"scenario" must be string'),
])
def test_invalid_arguments_are_rejected_before_running(args, expected):
    _, result = run([call('run_scenario', **args), final('x')])
    assert expected in json.loads(tool_messages(result)[0].content)['error']
    assert fake_tools.CALL_LOG == []  # tool never executed


def test_tool_exception_becomes_error_result():
    _, result = run([call('get_run_summary', run_name='nope'), final('x')])
    content = tool_messages(result)[0].content
    assert 'FileNotFoundError' in content


def test_failed_scenario_is_reported_not_raised():
    fake_tools.FAIL_SCENARIOS.add('person_stop')
    _, result = run([call('run_scenario', scenario='person_stop'),
                     final('person_stop FAIL')])
    summary = json.loads(tool_messages(result)[0].content)
    assert summary['verdict'] == 'FAIL'
    assert summary['checks']['stopped_for_person'] is False


def test_max_turns_stops_a_model_that_never_answers():
    steps = [call('list_scenarios', cid=f'c{i}') for i in range(10)]
    _, result = run(steps, max_turns=3)
    assert result.stop_reason == 'max_turns'
    assert result.turns == 3


def test_repeated_identical_call_is_refused_after_limit():
    steps = [call('get_gpu_status', cid=f'c{i}') for i in range(3)]
    _, result = run(steps + [final('ok')])
    contents = [t.content for t in tool_messages(result)]
    assert 'same call already made' in contents[2]
    assert len(fake_tools.CALL_LOG) == 2


def test_model_error_stops_cleanly():
    def broken(messages):
        raise ModelError('connection refused')
    _, result = run([broken])
    assert result.stop_reason == 'model_error'
    assert 'connection refused' in result.final_text


def test_long_tool_output_is_truncated():
    registry = ToolRegistry([Tool('big', 'd', {'type': 'object',
                                               'properties': {}},
                                  lambda: 'x' * 5000)],
                            max_result_chars=100)
    result = registry.execute('big', {})
    assert result.ok and len(result.content) < 200
    assert 'truncated, 5000 chars total' in result.content


def test_fake_saved_run_requires_exact_name_like_real_tool():
    _, result = run([call('get_run_summary', run_name='person_stop'),
                     final('x')])
    assert 'call list_saved_runs first' in tool_messages(result)[0].content


def test_policy_blocks_scenarios_the_user_did_not_ask_for():
    from robot_agent.acceptance_tools import scenario_policy
    steps = [call('run_scenario', cid='a', scenario='approach'),
             call('run_scenario', cid='b', scenario='person_stop'),
             final('done')]
    model = ScriptedModel(steps)
    result = run_agent(model, ToolRegistry(build_fake_tools()), 'sys',
                       '執行 person_stop', policy=scenario_policy(
                           '執行 person_stop'))
    tools = tool_messages(result)
    assert 'did not ask to run "approach"' in json.loads(
        tools[0].content)['error']
    assert json.loads(tools[1].content)['verdict'] == 'PASS'
    assert fake_tools.CALL_LOG == [
        ('run_scenario', {'scenario': 'person_stop', 'device': 'gpu'})]


@pytest.mark.parametrize('task, expected', [
    ('執行 fly_to_moon 情境。', set()),
    ('用 GPU 執行 person_stop', {'person_stop'}),
    ('把全部情境都跑一次', {'approach', 'target_loss', 'person_stop'}),
    ('Run every scenario', {'approach', 'target_loss', 'person_stop'}),
])
def test_requested_scenarios(task, expected):
    from robot_agent.acceptance_tools import requested_scenarios
    assert requested_scenarios(task) == expected

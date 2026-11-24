"""Multi-agent pipeline tests: one scripted model per role, fake tools."""

import pytest

from robot_agent import fake_tools
from robot_agent.acceptance_tools import scenario_policy
from robot_agent.fake_tools import build_fake_tools
from robot_agent.llm import ScriptedModel
from robot_agent.messages import Message, ToolCall
from robot_agent.multi_agent import (MAX_STEPS, check_plan, run_multi_agent,
                                     unsupported_numbers)
from robot_agent.tools import ToolRegistry


@pytest.fixture(autouse=True)
def reset_fakes():
    fake_tools.CALL_LOG.clear()
    fake_tools.FAIL_SCENARIOS.clear()
    yield


def call(name, cid='c1', **args):
    return Message('assistant', tool_calls=[ToolCall(cid, name, args)])


def text(t):
    return Message('assistant', t)


def approve():
    return {'parts': [{'part': 'request', 'answered': True}]}


def run(request, plan, executor_steps, reports, reviews, max_revisions=2):
    models = {
        'planner': ScriptedModel([plan, {'steps': [], 'done': True}]),
        'executor': ScriptedModel(executor_steps),
        'reporter': ScriptedModel([text(r) for r in reports]),
        'reviewer': ScriptedModel(reviews),
    }
    result = run_multi_agent(request, ToolRegistry(build_fake_tools()),
                             policy=scenario_policy(request),
                             max_revisions=max_revisions, **models)
    return result, models


PERSON_PLAN = {'steps': [{'tool': 'run_scenario',
                          'arguments': {'scenario': 'person_stop',
                                        'device': 'gpu'},
                          'goal': 'run person_stop on GPU'}]}


def test_happy_path_plan_execute_report_approve():
    result, models = run(
        '用 GPU 執行 person_stop，回報停車反應時間。', PERSON_PLAN,
        [call('run_scenario', scenario='person_stop', device='gpu'),
         text('done')],
        ['person_stop：PASS，停車反應時間 94 ms。'], [approve()])
    assert result.approved and result.stop_reason == 'done'
    assert [e['tool'] for e in result.evidence] == ['run_scenario']
    assert result.evidence[0]['result']['verdict'] == 'PASS'
    assert len(result.reviews) == 1
    # the reporter saw the evidence, not the tools
    reporter_prompt = models['reporter'].calls[0][-1].content
    assert '"verdict": "PASS"' in reporter_prompt


def test_invented_number_is_caught_by_code_and_revised():
    result, models = run(
        '用 GPU 執行 person_stop，回報停車反應時間。', PERSON_PLAN,
        [call('run_scenario', scenario='person_stop', device='gpu'),
         text('done')],
        ['person_stop：PASS，停車反應時間 120 ms。',      # invented
         'person_stop：PASS，停車反應時間 94 ms。'],
        [approve(), approve()])  # model reviewer misses it; code does not
    assert result.approved
    first, second = result.reviews
    assert not first['approved'] and first['model_approved']
    assert first['code_problems'] == [
        'Remove or correct the number 120: it does not appear in the '
        'evidence.']
    assert second['approved']
    revision_prompt = models['reporter'].calls[1][-1].content
    assert 'Remove or correct the number 120' in revision_prompt
    assert '120 ms' in revision_prompt  # previous report shown


def test_model_reviewer_problems_also_trigger_revision():
    result, _ = run(
        '執行 approach 並說明結果', {'steps': [
            {'tool': 'run_scenario', 'arguments': {'scenario': 'approach'},
             'goal': 'run approach'}]},
        [call('run_scenario', scenario='approach'), text('done')],
        ['approach 已執行。', 'approach：PASS，停在 0.53 m。'],
        [{'parts': [{'part': '說明結果', 'answered': False}]}, approve()])
    assert result.approved and len(result.reviews) == 2
    assert result.reviews[0]['model_problems'] == ['Not answered: 說明結果']


def test_gives_up_after_max_revisions():
    result, _ = run(
        '用 GPU 執行 person_stop', PERSON_PLAN,
        [call('run_scenario', scenario='person_stop', device='gpu'),
         text('done')],
        ['停車 999 ms'] * 3, [approve()] * 3, max_revisions=2)
    assert not result.approved and len(result.reviews) == 3
    assert result.report == '停車 999 ms'


def test_executor_repairs_a_wrong_run_name_from_the_error():
    plan = {'steps': [{'tool': 'get_run_summary',
                       'arguments': {'run_name': 'person_stop'},
                       'goal': 'summarize the saved person_stop run'}]}
    result, _ = run(
        '摘要已保存的 person_stop 執行紀錄', plan,
        [call('get_run_summary', run_name='person_stop'),
         call('list_saved_runs', cid='c2'),
         call('get_run_summary', cid='c3', run_name='D1_person'),
         text('done')],
        ['D1_person：PASS，停車反應時間 94 ms。'], [approve()])
    assert [(e['tool'], e['ok']) for e in result.evidence] == [
        ('get_run_summary', False), ('list_saved_runs', True),
        ('get_run_summary', True)]
    assert result.approved


def test_unknown_scenario_gives_empty_plan_and_no_execution():
    plan = {'steps': [], 'note': 'fly_to_moon 不存在'}
    result, models = run('執行 fly_to_moon 情境', plan, [],
                         ['fly_to_moon 情境不存在，可用：approach、'
                          'target_loss、person_stop。'], [approve()])
    assert result.approved and result.evidence == []
    assert fake_tools.CALL_LOG == []
    assert 'fly_to_moon 不存在' in models['reporter'].calls[0][-1].content


def test_check_plan_drops_unknown_unrequested_and_duplicate_steps():
    registry = ToolRegistry(build_fake_tools())
    raw = {'steps': [
        {'tool': 'drive_robot', 'arguments': {}, 'goal': 'x'},
        {'tool': 'run_scenario', 'arguments': {'scenario': 'approach'},
         'goal': 'not requested'},
        {'tool': 'run_scenario', 'arguments': {'scenario': 'person_stop'},
         'goal': 'requested'},
        {'tool': 'run_scenario', 'arguments': {'scenario': 'person_stop'},
         'goal': 'duplicate'},
        {'tool': 'get_run_summary', 'arguments': {}, 'goal': 'bad args'},
    ]}
    steps, changes = check_plan(raw, registry,
                                scenario_policy('執行 person_stop'))
    assert [s['tool'] for s in steps] == ['run_scenario', 'get_run_summary']
    assert any('unknown tool "drive_robot"' in c for c in changes)
    assert any('did not ask to run "approach"' in c for c in changes)
    assert any('repeated step' in c for c in changes)
    assert any('executor will repair' in c for c in changes)


def test_check_plan_caps_the_number_of_steps():
    registry = ToolRegistry(build_fake_tools())
    raw = {'steps': [{'tool': 'get_run_summary',
                      'arguments': {'run_name': f'r{i}'}, 'goal': ''}
                     for i in range(MAX_STEPS + 3)]}
    steps, changes = check_plan(raw, registry, None)
    assert len(steps) == MAX_STEPS and 'plan cut' in changes[-1]


@pytest.mark.parametrize('report, missing', [
    ('停車反應時間 94 ms，最終位置 0.53 m', []),       # 0.525 rounds to 0.53
    ('停車反應時間 94毫秒', []),                       # CJK right after number
    ('D1_person 在 RTX 4070 上，步驟 3', []),          # ids, card name, small int
    ('停車反應時間 95 ms', ['95']),
    ('推論 27.5 ms，位移 0.4 m', ['27.5', '0.4']),
])
def test_unsupported_numbers(report, missing):
    evidence = [{'tool': 'run_scenario', 'arguments': {}, 'ok': True,
                 'result': {'facts': {'person_to_stop_ms': 94},
                            'final_x_m': 0.525,
                            'nvidia_smi': 'NVIDIA GeForce RTX 4070, 621.24'}}]
    assert unsupported_numbers(report, evidence, '') == missing


EVIDENCE_TWO_RUNS = [
    {'tool': 'get_run_summary', 'arguments': {}, 'ok': True,
     'result': {'run': 'D1_person', 'scenario': 'person_stop',
                'verdict': 'PASS',
                'checks': {'stopped_for_person': True,
                           'stop_within_500_ms': True}}},
    {'tool': 'run_scenario', 'arguments': {}, 'ok': True,
     'result': {'run': 'run_approach', 'scenario': 'approach',
                'verdict': 'FAIL',
                'checks': {'reached_target_and_stopped': False}}},
]


@pytest.mark.parametrize('report, expected', [
    ('D1_person：PASS\nstopped_for_person：通過', 0),
    ('approach：FAIL，reached_target_and_stopped 未通過', 0),
    ('stopped_for_person: true', 0),
    ('approach：PASS', 1),                       # verdict contradicted
    ('reached_target_and_stopped：通過', 1),      # check contradicted
    ('D1_person 失敗', 1),
    ('停車反應時間 94 ms', 0),                     # no PASS/FAIL claim
])
def test_contradicted_claims(report, expected):
    from robot_agent.multi_agent import contradicted_claims
    assert len(contradicted_claims(report, EVIDENCE_TWO_RUNS)) == expected


def test_wrong_verdict_is_caught_even_if_model_reviewer_approves():
    fake_tools.FAIL_SCENARIOS.add('approach')
    result, _ = run(
        '執行 approach 並說明結果', {'steps': [
            {'tool': 'run_scenario', 'arguments': {'scenario': 'approach'},
             'goal': 'run approach'}]},
        [call('run_scenario', scenario='approach'), text('done')],
        ['approach：PASS', 'approach：FAIL，reached_target_and_stopped 未通過'],
        [approve(), approve()])
    assert result.approved
    assert 'verdict in the evidence is FAIL' in \
        result.reviews[0]['code_problems'][0]


def test_replanning_uses_the_listed_run_name():
    first = {'steps': [{'tool': 'list_saved_runs', 'arguments': {},
                        'goal': 'find the exact run name'}], 'done': False}

    def second(messages):
        assert 'D1_person' in messages[-1].content   # planner sees evidence
        return {'steps': [{'tool': 'get_run_summary',
                           'arguments': {'run_name': 'D1_person'},
                           'goal': 'summarize it'}], 'done': True}
    models = {
        'planner': ScriptedModel([first, second]),
        'executor': ScriptedModel([call('list_saved_runs'), text('ok'),
                                   call('get_run_summary', cid='c2',
                                        run_name='D1_person'), text('ok')]),
        'reporter': ScriptedModel([text('D1_person：PASS，94 ms')]),
        'reviewer': ScriptedModel([approve()]),
    }
    result = run_multi_agent('摘要已保存的 person_stop 執行紀錄',
                             ToolRegistry(build_fake_tools()), **models)
    assert [s['tool'] for s in result.plan] == ['list_saved_runs',
                                                'get_run_summary']
    assert result.approved


def test_replanning_never_repeats_an_executed_step():
    again = {'steps': [{'tool': 'list_saved_runs', 'arguments': {},
                        'goal': 'again'}]}
    models = {
        'planner': ScriptedModel([again, again]),
        'executor': ScriptedModel([call('list_saved_runs'), text('ok')]),
        'reporter': ScriptedModel([text('有 3 筆紀錄')]),
        'reviewer': ScriptedModel([approve()]),
    }
    result = run_multi_agent('列出已保存的紀錄',
                             ToolRegistry(build_fake_tools()), **models)
    assert len(result.plan) == 1
    assert any('repeated step' in c for c in result.plan_changes)


def test_pass_claim_without_any_test_result_is_rejected():
    from robot_agent.multi_agent import contradicted_claims
    assert contradicted_claims('PLANNER: PASS\n所有檢查都通過', [])
    assert contradicted_claims('答案是：能用（PASS）', [])
    assert contradicted_claims('沒有執行測試，無法得出 PASS 或 FAIL 結果', []) == []
    gpu = [{'tool': 'get_gpu_status', 'arguments': {}, 'ok': True,
            'result': {'yolo_venv_torch_and_cuda': '2.14.1+cu130 True'}}]
    assert contradicted_claims('PyTorch CUDA：True', gpu) == []


def test_fabricated_result_for_empty_plan_is_caught():
    result, models = run(
        '執行 fly_to_moon 情境', {'steps': [], 'note': '不存在'}, [],
        ['fly_to_moon：PASS，所有檢查都通過', 'fly_to_moon 情境不存在，沒有執行。'],
        [approve(), approve()])
    assert result.approved and len(result.reviews) == 2
    assert 'must not contain the words PASS' in \
        result.reviews[0]['code_problems'][0]
    assert 'no tool was run' in models['reporter'].calls[0][-1].content

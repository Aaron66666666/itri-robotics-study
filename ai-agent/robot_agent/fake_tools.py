"""Fake versions of the acceptance tools: same names and schemas, canned
results, no Gazebo. Used to get the agent loop right before running real
simulations. FAIL_SCENARIOS lets a test make one scenario fail on purpose.
"""

from .acceptance_tools import SCENARIOS, list_scenarios, tool_specs
from .tools import Tool

FAIL_SCENARIOS: set[str] = set()
# Saved-run names look like the real evidence runs (not "fake_*"), so the
# model has to map a request such as "person_stop" to the right run name.
SAVED_RUNS = {'A1_approach': 'approach', 'B1_loss': 'target_loss',
              'D1_person': 'person_stop'}
CALL_LOG: list[tuple[str, dict]] = []


def _summary(scenario: str, device: str, run_name: str = '') -> dict:
    ok = scenario not in FAIL_SCENARIOS
    checks = {'camera_node_running': True,
              'reached_target_and_stopped': ok}
    facts = {}
    if scenario == 'person_stop':
        checks.update(stopped_for_person=ok, resumed_after_person_left=True)
        facts = {'person_to_stop_ms': 94 if ok else None}
    return {'run': run_name or f'run_{scenario}', 'scenario': scenario,
            'verdict': 'PASS' if ok else 'FAIL', 'checks': checks,
            'facts': facts, 'final_x_m': 0.53 if ok else 0.09,
            'yolo_device': 'cuda:0' if device == 'gpu' else 'cpu',
            'fake': True}


def _record(name, **args):
    CALL_LOG.append((name, args))


def fake_list_scenarios():
    _record('list_scenarios')
    return list_scenarios()


def fake_run_scenario(scenario, device='gpu'):
    _record('run_scenario', scenario=scenario, device=device)
    return _summary(scenario, device)


def fake_list_saved_runs():
    _record('list_saved_runs')
    return {'runs': sorted(SAVED_RUNS), 'count': len(SAVED_RUNS)}


def fake_get_run_summary(run_name):
    _record('get_run_summary', run_name=run_name)
    # Strict like the real tool: only exact names from list_saved_runs.
    if run_name not in SAVED_RUNS:
        raise FileNotFoundError(f'no saved run named {run_name}; '
                                'call list_saved_runs first')
    return _summary(SAVED_RUNS[run_name], 'gpu', run_name)


def fake_get_gpu_status():
    _record('get_gpu_status')
    return {'nvidia_smi': 'NVIDIA GeForce RTX 4070 Laptop GPU, 621.24 (fake)',
            'yolo_venv_torch_and_cuda': '2.14.1+cu130 True'}


def build_fake_tools() -> list[Tool]:
    funcs = {'list_scenarios': fake_list_scenarios,
             'run_scenario': fake_run_scenario,
             'list_saved_runs': fake_list_saved_runs,
             'get_run_summary': fake_get_run_summary,
             'get_gpu_status': fake_get_gpu_status}
    return [Tool(name, desc, params, funcs[name])
            for name, desc, params in tool_specs()]

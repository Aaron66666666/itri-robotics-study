"""Real tools: run and summarize the Gazebo/YOLO acceptance scenarios.

All parsing and pass/fail checks happen here in plain Python. The model only
decides which tools to call and reads short JSON summaries (never raw logs).

Paths:
  ROBOT_WS  workspace with tools/acceptance and worlds (default ~/robot_ws)
  OUT       where run.sh writes runs (default /tmp/robot_acceptance)
Saved evidence runs in ROBOT_WS/docs/evidence/* are summarized as well.
"""

import csv
import os
import re
import statistics
import subprocess
import time
from pathlib import Path

from .tools import Tool

ROBOT_WS = Path(os.environ.get('ROBOT_WS', Path.home() / 'robot_ws'))
OUT_DIR = Path(os.environ.get('OUT', '/tmp/robot_acceptance'))
YOLO_PYTHON = Path.home() / 'yolo_project' / '.venv' / 'bin' / 'python'

COMMON_ARGS = [
    'target_class:=cup', 'search_speed:=0.05', 'approach_speed:=0.05',
    'alignment_speed:=0.15', 'target_action:=stop',
    'stop_bbox_dimension:=width', 'stop_bbox_ratio:=0.14',
]
SCENARIOS = {
    'approach': {
        'description': 'Vehicle detects the cup, approaches at 0.05 m/s and '
                       'stops near it.',
        'world': 'worlds/diff_drive_camera_cup.sdf', 'hook': None,
        'seconds': 60, 'extra_args': [],
    },
    'target_loss': {
        'description': 'Cup is removed briefly (stop and wait) and then for '
                       '12 s (bounded search, then stop).',
        'world': 'worlds/diff_drive_camera_cup.sdf', 'hook': 'hook_loss.sh',
        'seconds': 55, 'extra_args': ['search_duration:=3.0'],
    },
    'person_stop': {
        'description': 'A person walks into view during the approach for '
                       '6 s; the vehicle must stop, then resume.',
        'world': 'worlds/diff_drive_camera_cup_person.sdf',
        'hook': 'hook_person.sh', 'seconds': 55, 'extra_args': [],
    },
}
NAME_RE = re.compile(r'^[A-Za-z0-9_]+$')
STATE_RE = re.compile(r'\[(\d+\.\d+)\] \[autonomy_controller\]: '
                      r'Autonomy state: (\S+)')


# ----------------------------------------------------------- parsing
def _run_dirs() -> list[Path]:
    dirs = [OUT_DIR]
    evidence = ROBOT_WS / 'docs' / 'evidence'
    if evidence.is_dir():
        dirs += sorted(p for p in evidence.iterdir() if p.is_dir())
    return dirs


def _find_run(run_name: str) -> Path | None:
    for directory in _run_dirs():
        if (directory / f'{run_name}.launch.log').is_file():
            return directory
    return None


def _guess_scenario(run_name: str, launch_log: str) -> str:
    if 'person' in run_name or 'cup_person' in launch_log:
        return 'person_stop'
    if 'loss' in run_name:
        return 'target_loss'
    return 'approach'


def summarize_run(run_name: str, directory: Path,
                  scenario: str | None = None) -> dict:
    """Parse one run's files into a short summary with pass/fail checks."""
    base = directory / run_name
    log = (base.with_name(f'{run_name}.launch.log')).read_text(
        errors='replace')
    scenario = scenario or _guess_scenario(run_name, log)
    states = [(float(t), s) for t, s in STATE_RE.findall(log)]
    seq = [s for _, s in states]

    elapsed = [float(v) * 1000 for v in re.findall(r'elapsed=([0-9.]+)s',
                                                   log)][1:]
    device = re.search(r'runtime_device=(\S+?),', log)
    camera_crashed = 'Program error' in log

    final_x = None
    pose_file = base.with_name(f'{run_name}.gzpose.txt')
    if pose_file.is_file():
        match = re.search(r'x:\s*(-?[0-9.e-]+)', pose_file.read_text())
        final_x = round(float(match.group(1)), 3) if match else None

    odom, det_classes = [], {}
    csv_file = base.with_name(f'{run_name}.csv')
    if csv_file.is_file():
        with csv_file.open() as handle:
            for row in csv.DictReader(handle):
                if row['kind'] == 'odom':
                    odom.append((float(row['t']), float(row['a'])))
                elif row['kind'] == 'det' and row['a'] != 'none':
                    for item in row['a'].split(';'):
                        cls, conf = item.split(':')[:2]
                        best = det_classes.get(cls, 0.0)
                        det_classes[cls] = max(best, float(conf))

    events = []
    hook_file = base.with_name(f'{run_name}.hook.log')
    if hook_file.is_file():
        for line in hook_file.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                events.append((float(parts[0]), parts[1], parts[2]))

    checks: dict[str, bool] = {
        'camera_node_running': not camera_crashed and bool(elapsed),
        'reached_target_and_stopped': 'target_action_complete' in seq,
    }
    facts: dict[str, object] = {}
    if scenario == 'approach':
        checks['vehicle_moved_toward_cup'] = (final_x or 0) > 0.3
    elif scenario == 'target_loss':
        for state in ('target_lost_wait', 'search_forward',
                      'search_timeout'):
            checks[f'saw_{state}'] = state in seq
    elif scenario == 'person_stop':
        person_in = next((t for t, who, pos in events
                          if who == 'person' and not pos.startswith('x=-')),
                         None)
        person_out = next((t for t, who, pos in events
                           if who == 'person' and pos.startswith('x=-')),
                          None)
        stop_t = next((t for t, s in states
                       if s == 'person_detected'
                       and person_in and t >= person_in), None)
        resume_t = next((t for t, s in states
                         if s == 'approach_target'
                         and person_out and t >= person_out), None)
        checks['stopped_for_person'] = stop_t is not None
        checks['resumed_after_person_left'] = resume_t is not None
        if stop_t:
            facts['person_to_stop_ms'] = round((stop_t - person_in) * 1000)
            checks['stop_within_500_ms'] = facts['person_to_stop_ms'] <= 500
        if resume_t:
            facts['person_left_to_resume_ms'] = round(
                (resume_t - person_out) * 1000)
        epoch_odom = [o for o in odom if o[0] > 1e9]
        if stop_t and person_out and epoch_odom:
            window = [x for t, x in epoch_odom
                      if stop_t + 0.3 <= t <= person_out]
            if window:
                moved = max(window) - min(window)
                facts['moved_while_person_visible_m'] = round(moved, 4)
                checks['stayed_stopped_while_person_visible'] = moved < 0.01

    return {
        'run': run_name,
        'scenario': scenario,
        'verdict': 'PASS' if all(checks.values()) else 'FAIL',
        'checks': checks,
        'facts': facts,
        'state_sequence': [s for i, s in enumerate(seq)
                           if i == 0 or seq[i - 1] != s],
        'final_x_m': final_x,
        'yolo_device': device.group(1) if device else None,
        'inference_ms_median': (round(statistics.median(elapsed))
                                if elapsed else None),
        'max_confidence_by_class': {k: round(v, 3)
                                    for k, v in det_classes.items()},
    }


# ------------------------------------------------------------- tools
def list_scenarios() -> dict:
    return {name: {'description': spec['description'],
                   'approx_runtime_s': spec['seconds'] + 25}
            for name, spec in SCENARIOS.items()}


def list_saved_runs() -> dict:
    runs = {}
    for directory in _run_dirs():
        for log in sorted(directory.glob('*.launch.log')):
            name = log.name[:-len('.launch.log')]
            runs.setdefault(name, str(directory))
    return {'runs': sorted(runs), 'count': len(runs)}


def get_run_summary(run_name: str) -> dict:
    if not NAME_RE.match(run_name):
        raise ValueError('run_name may contain only letters, digits and _')
    directory = _find_run(run_name)
    if directory is None:
        raise FileNotFoundError(f'no saved run named {run_name}; '
                                'call list_saved_runs first')
    return summarize_run(run_name, directory)


def run_scenario(scenario: str, device: str = 'gpu') -> dict:
    spec = SCENARIOS[scenario]
    run_name = f'agent_{scenario}_{time.strftime("%Y%m%d_%H%M%S")}'
    script = ROBOT_WS / 'tools' / 'acceptance' / 'run.sh'
    env = dict(os.environ, WORLD=spec['world'], OUT=str(OUT_DIR),
               ROBOT_WS=str(ROBOT_WS))
    if spec['hook']:
        env['HOOK'] = str(ROBOT_WS / 'tools' / 'acceptance' / spec['hook'])
    args = [str(script), run_name, str(spec['seconds'])] + COMMON_ARGS + \
        spec['extra_args'] + [f"device:={'0' if device == 'gpu' else 'cpu'}"]
    completed = subprocess.run(args, env=env, capture_output=True, text=True,
                               timeout=spec['seconds'] + 120)
    if not (OUT_DIR / f'{run_name}.launch.log').is_file():
        raise RuntimeError(f'run.sh produced no log (exit '
                           f'{completed.returncode}): '
                           f'{completed.stderr[-300:]}')
    return summarize_run(run_name, OUT_DIR, scenario)


def get_gpu_status() -> dict:
    status: dict[str, object] = {}
    smi = subprocess.run(
        ['/usr/lib/wsl/lib/nvidia-smi', '--query-gpu=name,driver_version,'
         'memory.used,memory.total', '--format=csv,noheader'],
        capture_output=True, text=True, timeout=20)
    status['nvidia_smi'] = smi.stdout.strip() or smi.stderr.strip()[:200]
    if YOLO_PYTHON.is_file():
        torch = subprocess.run(
            [str(YOLO_PYTHON), '-I', '-c',
             'import torch;print(torch.__version__, '
             'torch.cuda.is_available())'],
            capture_output=True, text=True, timeout=120)
        status['yolo_venv_torch_and_cuda'] = (torch.stdout.strip()
                                              or torch.stderr.strip()[-200:])
    return status


SCENARIO_ARG = {'type': 'string', 'enum': sorted(SCENARIOS),
                'description': 'Scenario name from list_scenarios.'}
DEVICE_ARG = {'type': 'string', 'enum': ['gpu', 'cpu'],
              'description': 'Where YOLO runs. Default gpu.'}


def _obj(props: dict, required: list[str]) -> dict:
    return {'type': 'object', 'properties': props, 'required': required,
            'additionalProperties': False}


def tool_specs() -> list[tuple[str, str, dict]]:
    """(name, description, parameters) shared by the real and fake tools."""
    return [
        ('list_scenarios', 'List the Gazebo acceptance scenarios that can be '
         'run, with what each one checks.', _obj({}, [])),
        ('run_scenario', 'Run one acceptance scenario in headless Gazebo '
         '(takes about 1.5 minutes) and return a pass/fail summary.',
         _obj({'scenario': SCENARIO_ARG, 'device': DEVICE_ARG},
              ['scenario'])),
        ('list_saved_runs', 'List names of previously saved runs that can '
         'be summarized.', _obj({}, [])),
        ('get_run_summary', 'Return the pass/fail summary of a saved run.',
         _obj({'run_name': {'type': 'string',
                            'description': 'Name from list_saved_runs.'}},
              ['run_name'])),
        ('get_gpu_status', 'Report the GPU, driver and whether PyTorch in '
         'the YOLO environment can use CUDA.', _obj({}, [])),
    ]


def build_real_tools() -> list[Tool]:
    funcs = {'list_scenarios': list_scenarios, 'run_scenario': run_scenario,
             'list_saved_runs': list_saved_runs,
             'get_run_summary': get_run_summary,
             'get_gpu_status': get_gpu_status}
    return [Tool(name, desc, params, funcs[name])
            for name, desc, params in tool_specs()]

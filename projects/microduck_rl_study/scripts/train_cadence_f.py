"""Experiment F: let lateral walking use a higher cadence.

Gait analysis of C (2026-11-28, docs/gait/C_gait.json): sideways the policy
steps at 2.2-2.4 Hz while forward it steps at ~3 Hz, and the servos are far
from their speed / torque limits. The stock air_time reward pays every control
step a foot has been in the air for 0.125-0.300 s, so a long swing (close to
0.3 s) earns more than a short one: an incentive for a slow cadence that the
forward tracking terms overcome but the weaker lateral tracking does not.

F = experiment C (train_tracking_v3.py settings: pure-axis bucket, fine linear
term, track_yaw_fine) with ONE change: for lateral-dominant commands
(|vy| > |vx| and |vy| > 0.1 m/s) the air_time window ends at LATERAL_AIR_MAX
(default 0.20 s) instead of 0.30 s. Everything else is untouched.

Run from the microduck_rl checkout, resuming from C:
    ~/rl/tools-venv/bin/uv run --locked python <this file> \\
        Mjlab-Velocity-Flat-MicroDuck-TrackV3F --env.scene.num-envs 4096 \\
        --agent.logger tensorboard --agent.resume True --agent.load-run <C run> \\
        --agent.load-checkpoint model_11995.pt --agent.max-iterations 2000 \\
        --agent.run-name track_v3_F
"""

import importlib.util
import os
import sys
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("train_tracking_v3", HERE / "train_tracking_v3.py")
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)  # registers TrackV3 and patches the command resample (C settings)

from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task  # noqa: E402

LATERAL_AIR_MAX = float(os.environ.get("LATERAL_AIR_MAX", "0.20"))
NEW_TASK = v3.BASE_TASK + "-TrackV3F"


def feet_air_time_cadence(env, sensor_name: str, threshold_min: float, threshold_max: float,
                          lateral_max: float, command_name: str, command_threshold: float):
    """mjlab's feet_air_time, with a shorter window for lateral-dominant commands."""
    air = env.scene[sensor_name].data.current_air_time
    cmd = env.command_manager.get_command(command_name)
    lateral = (cmd[:, 1].abs() > cmd[:, 0].abs()) & (cmd[:, 1].abs() > 0.1)
    tmax = torch.where(lateral, torch.full_like(cmd[:, 1], lateral_max),
                       torch.full_like(cmd[:, 1], threshold_max))
    in_range = (air > threshold_min) & (air < tmax[:, None])
    reward = torch.sum(in_range.float(), dim=1)
    total = torch.norm(cmd[:, :2], dim=1) + torch.abs(cmd[:, 2])
    return reward * (total > command_threshold).float()


def adjust_f(cfg):
    cfg = v3.adjust(cfg)
    term = cfg.rewards["air_time"]
    params = dict(term.params)
    params["lateral_max"] = LATERAL_AIR_MAX
    term.func = feet_air_time_cadence
    term.params = params
    return cfg


register_mjlab_task(
    task_id=NEW_TASK,
    env_cfg=adjust_f(load_env_cfg(v3.BASE_TASK)),
    play_env_cfg=adjust_f(load_env_cfg(v3.BASE_TASK, play=True)),
    rl_cfg=load_rl_cfg(v3.BASE_TASK),
    runner_cls=load_runner_cls(v3.BASE_TASK),
)
print(f"[cadence_f] registered {NEW_TASK}: lateral air_time window ends at {LATERAL_AIR_MAX} s "
      "(others unchanged)", flush=True)

if __name__ == "__main__":
    from mjlab.scripts.train import main

    sys.exit(main())

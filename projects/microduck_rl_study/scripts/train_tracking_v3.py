"""Experiment C: fix lateral / backward tracking by rebalancing the commands.

Findings (probe_cmd_grid.py on experiment A, 2026-11-26):
  - forward 50-57% of the command, backward ~45%, turning in place ~100%,
    lateral only 12-31% and asymmetric, and a dead zone for |cmd| <= 0.1;
  - the training command mix is forward-heavy: mjlab's default
    rel_forward_envs = 0.2 makes 20% of resamples forward-only (vx >= 0.3),
    and pure lateral commands never occur (lateral only appears mixed with
    random vx and wz, |vy| ~0.15 on average).

This wrapper registers Mjlab-Velocity-Flat-MicroDuck-TrackV3 = experiment A
(linear std^2 0.05, stock angular term, track_yaw_fine) plus:
  - FORWARD_BUCKET (default 0.0): rel_forward_envs (upstream 0.2)
  - AXIS_BUCKET (default 0.25): share of resamples replaced by a pure-axis
    command, LATERAL_SHARE (default 0.7) of them pure lateral
    |vy| in [0.1, 0.3], the rest pure backward vx in [-0.4, -0.1]
  - LIN_FINE_WEIGHT (default 1.0) / LIN_FINE_STD (default 0.15): an added
    xy-velocity Gaussian with a sharper std, same idea as track_yaw_fine,
    to price small errors (and the dead zone).

Run from the microduck_rl checkout, resuming from experiment A:
    ~/rl/tools-venv/bin/uv run --locked python <this file> \
        Mjlab-Velocity-Flat-MicroDuck-TrackV3 --env.scene.num-envs 4096 \
        --agent.logger tensorboard --agent.resume True --agent.load-run <A run> \
        --agent.load-checkpoint model_9996.pt --agent.max-iterations 2000 \
        --agent.run-name track_v3_C
"""

import math
import os
import sys

import torch

import mjlab.tasks  # noqa: F401  (runs the plugin loader, registers the upstream tasks)
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task
from mjlab_microduck.tasks import mdp as microduck_mdp

BASE_TASK = "Mjlab-Velocity-Flat-MicroDuck"
NEW_TASK = "Mjlab-Velocity-Flat-MicroDuck-TrackV3"
LIN_STD2 = 0.05
YAW_FINE_WEIGHT, YAW_FINE_STD = 2.0, 0.35
FORWARD_BUCKET = float(os.environ.get("FORWARD_BUCKET", "0.0"))
AXIS_BUCKET = float(os.environ.get("AXIS_BUCKET", "0.25"))
LATERAL_SHARE = float(os.environ.get("LATERAL_SHARE", "0.7"))
LIN_FINE_WEIGHT = float(os.environ.get("LIN_FINE_WEIGHT", "1.0"))
LIN_FINE_STD = float(os.environ.get("LIN_FINE_STD", "0.15"))


def track_lin_vel_fine(env, std: float, command_name: str):
    """xy-velocity Gaussian with a sharp std, added next to the stock term."""
    asset = env.scene["robot"]
    cmd = env.command_manager.get_command(command_name)
    err = torch.sum(torch.square(cmd[:, :2] - asset.data.root_link_lin_vel_b[:, :2]), dim=1)
    return torch.exp(-err / std**2)


def adjust(cfg):
    r = cfg.rewards
    r["track_linear_velocity"].params["std"] = math.sqrt(LIN_STD2)
    r["track_angular_velocity"].params["std"] = math.sqrt(0.5)
    r["track_yaw_fine"] = RewardTermCfg(func=microduck_mdp.track_yaw_rate_fine, weight=YAW_FINE_WEIGHT,
                                        params={"command_name": "twist", "std": YAW_FINE_STD})
    if LIN_FINE_WEIGHT > 0:
        r["track_lin_vel_fine"] = RewardTermCfg(func=track_lin_vel_fine, weight=LIN_FINE_WEIGHT,
                                                params={"command_name": "twist", "std": LIN_FINE_STD})
    cfg.commands["twist"].rel_forward_envs = FORWARD_BUCKET
    return cfg


# Pure-axis command bucket: patch the resample of the command class the task uses.
_cls = microduck_mdp.VelocityCommandCommandOnly
_orig_resample = _cls._resample_command


def _resample_with_axis_bucket(self, env_ids):
    _orig_resample(self, env_ids)
    if AXIS_BUCKET <= 0 or len(env_ids) == 0:
        return
    dev = self.vel_command_b.device
    pick = torch.rand(len(env_ids), device=dev) < AXIS_BUCKET
    ids = env_ids[pick]
    if len(ids) == 0:
        return
    lateral = torch.rand(len(ids), device=dev) < LATERAL_SHARE
    mag_y = torch.empty(len(ids), device=dev).uniform_(0.1, self.cfg.ranges.lin_vel_y[1])
    sign = torch.where(torch.rand(len(ids), device=dev) < 0.5, -1.0, 1.0)
    mag_x = torch.empty(len(ids), device=dev).uniform_(0.1, -self.cfg.ranges.lin_vel_x[0])
    vx = torch.where(lateral, torch.zeros_like(mag_x), -mag_x)
    vy = torch.where(lateral, sign * mag_y, torch.zeros_like(mag_y))
    self.vel_command_b[ids, 0] = vx
    self.vel_command_b[ids, 1] = vy
    self.vel_command_b[ids, 2] = 0.0


_cls._resample_command = _resample_with_axis_bucket

register_mjlab_task(
    task_id=NEW_TASK,
    env_cfg=adjust(load_env_cfg(BASE_TASK)),
    play_env_cfg=adjust(load_env_cfg(BASE_TASK, play=True)),
    rl_cfg=load_rl_cfg(BASE_TASK),
    runner_cls=load_runner_cls(BASE_TASK),
)
print(f"[track_v3] registered {NEW_TASK}: forward bucket={FORWARD_BUCKET}, axis bucket={AXIS_BUCKET} "
      f"(lateral share {LATERAL_SHARE}), lin_fine w={LIN_FINE_WEIGHT} std={LIN_FINE_STD}, "
      f"yaw_fine w={YAW_FINE_WEIGHT}", flush=True)

if __name__ == "__main__":
    from mjlab.scripts.train import main

    sys.exit(main())

"""Second attempt at better velocity tracking, based on upstream's own notes.

What the first attempt (train_tight_track.py) did: linear tracking std^2
0.1 -> 0.05 and angular std^2 0.5 -> 0.25. Forward speed improved, but turning
and straight-line holding got worse.

Upstream (docs/velstand_policy.md and the docstring of mdp.track_yaw_rate_fine)
found the same thing: making the stock angular term sharper makes turning
WORSE, because a sharp Gaussian has almost no gradient at large errors. Their
fix is to keep the stock term and ADD a yaw-only fine term (std 0.35, weight 2).

This wrapper registers Mjlab-Velocity-Flat-MicroDuck-TrackV2:
  - linear tracking std^2 = LIN_STD2 (default 0.05, as in attempt 1)
  - angular tracking back to the upstream std^2 0.5
  - track_yaw_fine added (YAW_FINE_WEIGHT, default 2.0; std 0.35)
  - optional: HIP_ROLL_STD_WALK loosens the pose reward's hip-roll tolerance
    while walking (upstream 0.05 rad). Side-stepping needs hip roll, so this
    tests whether that tolerance is what limits lateral speed. Unset = upstream.

Run from the microduck_rl checkout (same log folder as the other runs):
    LIN_STD2=0.05 YAW_FINE_WEIGHT=2.0 [HIP_ROLL_STD_WALK=0.08] \
    ~/rl/tools-venv/bin/uv run --locked python <this file> \
        Mjlab-Velocity-Flat-MicroDuck-TrackV2 --env.scene.num-envs 4096 \
        --agent.logger tensorboard --agent.resume True --agent.load-run <run> \
        --agent.load-checkpoint model_<N>.pt --agent.max-iterations 2000 \
        --agent.run-name track_v2
"""

import math
import os
import sys

import mjlab.tasks  # noqa: F401  (runs the plugin loader, registers the upstream tasks)
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task
from mjlab_microduck.tasks import mdp as microduck_mdp

BASE_TASK = "Mjlab-Velocity-Flat-MicroDuck"
NEW_TASK = "Mjlab-Velocity-Flat-MicroDuck-TrackV2"
LIN_STD2 = float(os.environ.get("LIN_STD2", "0.05"))  # upstream 0.1
YAW_FINE_WEIGHT = float(os.environ.get("YAW_FINE_WEIGHT", "2.0"))  # 0 disables
YAW_FINE_STD = 0.35  # as upstream velstand
HIP_ROLL_STD_WALK = os.environ.get("HIP_ROLL_STD_WALK")  # upstream 0.05


def adjust(cfg):
    cfg.rewards["track_linear_velocity"].params["std"] = math.sqrt(LIN_STD2)
    cfg.rewards["track_angular_velocity"].params["std"] = math.sqrt(0.5)  # upstream value
    if YAW_FINE_WEIGHT > 0:
        cfg.rewards["track_yaw_fine"] = RewardTermCfg(
            func=microduck_mdp.track_yaw_rate_fine,
            weight=YAW_FINE_WEIGHT,
            params={"command_name": "twist", "std": YAW_FINE_STD},
        )
    if HIP_ROLL_STD_WALK:
        for key in ("std_walking", "std_running"):
            stds = dict(cfg.rewards["pose"].params[key])
            stds[r".*hip_roll.*"] = float(HIP_ROLL_STD_WALK)
            cfg.rewards["pose"].params[key] = stds
    return cfg


register_mjlab_task(
    task_id=NEW_TASK,
    env_cfg=adjust(load_env_cfg(BASE_TASK)),
    play_env_cfg=adjust(load_env_cfg(BASE_TASK, play=True)),
    rl_cfg=load_rl_cfg(BASE_TASK),
    runner_cls=load_runner_cls(BASE_TASK),
)
print(f"[track_v2] registered {NEW_TASK}: lin std^2={LIN_STD2}, ang std^2=0.5, "
      f"yaw_fine w={YAW_FINE_WEIGHT} std={YAW_FINE_STD}, hip_roll walk std={HIP_ROLL_STD_WALK or 'upstream'}",
      flush=True)

if __name__ == "__main__":
    from mjlab.scripts.train import main

    sys.exit(main())

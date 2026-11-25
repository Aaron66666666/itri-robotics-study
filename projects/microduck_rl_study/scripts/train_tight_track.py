"""Train the flat-walk task with a stricter velocity-tracking reward.

The fixed-command evaluation showed the upstream policy walking at only about
55% of the commanded forward speed, and about 20% backward and sideways. The
tracking rewards are exp(-err^2 / std^2) with std^2 = 0.1 (linear) and 0.5
(angular), so walking slowly still earns most of the reward. This wrapper
registers a copy of the upstream task with smaller std^2 values, then runs
mjlab's own `train` entry point, so the upstream code stays untouched.

Run from the microduck_rl checkout (same log folder as the normal runs):
    TIGHT_LIN_STD2=0.05 TIGHT_ANG_STD2=0.25 ~/rl/tools-venv/bin/uv run --locked \
        python <this file> Mjlab-Velocity-Flat-MicroDuck-TightTrack \
        --env.scene.num-envs 4096 --agent.logger tensorboard --agent.resume True \
        --agent.load-run <run> --agent.load-checkpoint model_<N>.pt \
        --agent.max-iterations 2000 --agent.run-name tight_track
"""

import math
import os
import sys

import mjlab.tasks  # noqa: F401  (runs the plugin loader, registers the upstream tasks)
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task

BASE_TASK = "Mjlab-Velocity-Flat-MicroDuck"
NEW_TASK = "Mjlab-Velocity-Flat-MicroDuck-TightTrack"
LIN_STD2 = float(os.environ.get("TIGHT_LIN_STD2", "0.05"))  # upstream: 0.1
ANG_STD2 = float(os.environ.get("TIGHT_ANG_STD2", "0.25"))  # upstream: 0.5


def tighten(cfg):
    cfg.rewards["track_linear_velocity"].params["std"] = math.sqrt(LIN_STD2)
    cfg.rewards["track_angular_velocity"].params["std"] = math.sqrt(ANG_STD2)
    return cfg


register_mjlab_task(
    task_id=NEW_TASK,
    env_cfg=tighten(load_env_cfg(BASE_TASK)),
    play_env_cfg=tighten(load_env_cfg(BASE_TASK, play=True)),
    rl_cfg=load_rl_cfg(BASE_TASK),
    runner_cls=load_runner_cls(BASE_TASK),
)
print(f"[tight_track] registered {NEW_TASK}: lin std^2={LIN_STD2}, ang std^2={ANG_STD2}", flush=True)

if __name__ == "__main__":
    from mjlab.scripts.train import main

    sys.exit(main())

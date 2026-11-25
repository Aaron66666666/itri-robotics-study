"""Command-response probe: run many fixed commands in parallel in ONE environment
(each group of envs gets its own command) and measure the achieved velocity.

Used to (1) see how each axis responds to its command, including commands
beyond the training range, and (2) build a command remap (calibration) table.

Curricula are at their final stage, no pushes, no standing / turn-in-place /
forward-only buckets. Commands are held fixed (resampling disabled and
re-written every step).

Run from the microduck_rl checkout:
    MUJOCO_GL=egl .venv/bin/python probe_cmd_grid.py --checkpoint <run>/model_N.pt \
        --out probe.json [--points sweep|FILE.json] [--per-point 16] [--seconds 16]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mjlab.tasks  # noqa: F401,E402
import mjlab_microduck.tasks  # noqa: F401,E402
from mjlab.envs import ManagerBasedRlEnv  # noqa: E402
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper  # noqa: E402
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls  # noqa: E402

TASK = "Mjlab-Velocity-Flat-MicroDuck"
WARMUP_S = 3.0
FINAL_STAGE_STEP = 10**7


def sweep_points():
    pts = [(0.0, 0.0, 0.0)]
    for vx in (-0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        pts.append((vx, 0.0, 0.0))
    for vy in (-0.5, -0.4, -0.3, -0.2, -0.1, 0.1, 0.2, 0.3, 0.4, 0.5):
        pts.append((0.0, vy, 0.0))
    for wz in (-1.4, -1.0, -0.6, -0.3, 0.3, 0.6, 1.0, 1.4):
        pts.append((0.0, 0.0, wz))
    return pts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--points", default="sweep")
    p.add_argument("--per-point", type=int, default=16)
    p.add_argument("--seconds", type=float, default=16.0)
    p.add_argument("--task", default=TASK)
    a = p.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    pts = sweep_points() if a.points == "sweep" else [tuple(x) for x in json.load(open(a.points))]
    n = len(pts) * a.per_point

    cfg = load_env_cfg(a.task, play=True)
    cfg.scene.num_envs = n
    tw = cfg.commands["twist"]
    tw.resampling_time_range = (1e6, 1e6)
    tw.rel_standing_envs = 0.0
    tw.rel_heading_envs = 0.0
    for attr in ("rel_turn_in_place_envs", "rel_forward_envs", "rel_world_envs", "init_velocity_prob"):
        if hasattr(tw, attr):
            setattr(tw, attr, 0.0)
    cfg.curriculum.pop("standing_envs", None)
    cfg.events.pop("push_robot", None)
    env = ManagerBasedRlEnv(cfg=cfg, device=device)
    wrapped = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(a.task).clip_actions)
    agent_cfg = load_rl_cfg(a.task)
    runner = (load_runner_cls(a.task) or MjlabOnPolicyRunner)(wrapped, asdict(agent_cfg), device=device)
    runner.load(a.checkpoint, load_cfg={"actor": True}, strict=True, map_location=device)
    policy = runner.get_inference_policy(device=device)

    target = torch.tensor([pt for pt in pts for _ in range(a.per_point)], device=device, dtype=torch.float32)
    term = env.command_manager.get_term("twist")
    env.common_step_counter = FINAL_STAGE_STEP
    wrapped.reset()

    def set_cmd():
        term.vel_command_b[:] = target
        term.is_standing_env[:] = False

    set_cmd()
    obs = wrapped.get_observations()
    robot = env.scene["robot"]
    dt = env.step_dt
    steps = int(round(a.seconds / dt))
    alive = torch.zeros(n, device=device)
    falls = torch.zeros(n, device=device)
    vsum = torch.zeros(n, 3, device=device)
    vcnt = torch.zeros(n, device=device)
    with torch.no_grad():
        for _ in range(steps):
            obs, _, dones, _ = wrapped.step(policy(obs))
            set_cmd()
            d = dones.bool()
            falls += env.termination_manager.get_term("fell_over").float()
            alive = torch.where(d, torch.zeros_like(alive), alive + dt)
            ok = (alive >= WARMUP_S) & ~d
            v = torch.cat([robot.data.root_link_lin_vel_b[:, :2], robot.data.root_link_ang_vel_b[:, 2:3]], 1)
            vsum += v * ok[:, None]
            vcnt += ok.float()
    out = []
    for i, pt in enumerate(pts):
        sl = slice(i * a.per_point, (i + 1) * a.per_point)
        m = (vsum[sl].sum(0) / vcnt[sl].sum().clamp(min=1)).tolist()
        out.append({"cmd": list(pt), "achieved": [round(x, 4) for x in m],
                    "falls": int(falls[sl].sum())})
        print(json.dumps(out[-1]), flush=True)
    json.dump({"checkpoint": a.checkpoint, "seconds": a.seconds, "per_point": a.per_point,
               "results": out}, open(a.out, "w"), indent=1)
    env.close()


if __name__ == "__main__":
    main()

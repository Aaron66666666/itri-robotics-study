"""Fixed-command evaluation of microduck walking checkpoints.

Training metrics are noisy (random commands, curricula, pushes), so this runs
every checkpoint under the same fixed velocity commands and reports, per
command: falls, measured velocity in the base frame, and tracking error.

The curricula are moved to their final stage (as at the end of training), the
standing-env and turn-in-place buckets are disabled so every env gets the
fixed command, and pushes can be turned off or kept (play-mode pushes are
every 0.5-1 s, harsher than training's 3-6 s).

Run from the microduck_rl checkout with its venv:
    MUJOCO_GL=egl .venv/bin/python <this file> \
        --checkpoints a/model_3999.pt b/model_7997.pt --num-envs 64 --seconds 20
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

import torch

import mjlab.tasks  # noqa: F401  (populates the task registry)
import mjlab_microduck.tasks  # noqa: F401
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

TASK = "Mjlab-Velocity-Flat-MicroDuck"
WARMUP_S = 2.0  # ignore the first seconds after each (re)spawn
FINAL_STAGE_STEP = 10**7  # far past every curriculum stage


def parse_cmd(text: str) -> tuple[float, float, float]:
    vx, vy, wz = (float(x) for x in text.split(","))
    return vx, vy, wz


def make_env(num_envs: int, cmd: tuple[float, float, float], pushes: bool, device: str):
    cfg = load_env_cfg(TASK, play=True)
    cfg.scene.num_envs = num_envs
    twist = cfg.commands["twist"]
    vx, vy, wz = cmd
    twist.ranges.lin_vel_x = (vx, vx)
    twist.ranges.lin_vel_y = (vy, vy)
    twist.ranges.ang_vel_z = (wz, wz)
    twist.rel_standing_envs = 0.0
    twist.rel_heading_envs = 0.0
    # Every bucket that would replace the fixed command must be off. mjlab's
    # velocity cfg defaults rel_forward_envs to 0.2 (20% of resamples become
    # forward-only, |vx| >= 0.3): before 2026-11-26 this was left on, so ~20% of
    # envs walked forward in every test (that showed up as fake "standing
    # drift" and too-low backward/lateral numbers).
    for attr in ("rel_turn_in_place_envs", "rel_forward_envs", "rel_world_envs", "init_velocity_prob"):
        if hasattr(twist, attr):
            setattr(twist, attr, 0.0)
    # This curriculum would raise rel_standing_envs back to 0.25.
    cfg.curriculum.pop("standing_envs", None)
    if not pushes:
        cfg.events.pop("push_robot", None)
    return ManagerBasedRlEnv(cfg=cfg, device=device)


def load_policy(env, path: str, device: str):
    agent_cfg = load_rl_cfg(TASK)
    runner_cls = load_runner_cls(TASK) or MjlabOnPolicyRunner
    runner = runner_cls(env, asdict(agent_cfg), device=device)
    runner.load(path, load_cfg={"actor": True}, strict=True, map_location=device)
    return runner.get_inference_policy(device=device)


@torch.no_grad()
def evaluate(env, policy, seconds: float) -> dict:
    base = env.unwrapped
    robot = base.scene["robot"]
    dt = base.step_dt
    n = base.num_envs
    steps = int(round(seconds / dt))
    falls = torch.zeros(n, device=base.device)
    alive_t = torch.zeros(n, device=base.device)
    v_sum = torch.zeros(n, 3, device=base.device)
    v_cnt = torch.zeros(n, device=base.device)
    cmd = base.command_manager.get_command("twist")[:, :3].clone()

    start_pos = robot.data.root_link_pos_w[:, :2].clone()
    start_t = None
    never_reset = torch.ones(n, dtype=torch.bool, device=base.device)

    obs = env.get_observations()
    for i in range(steps):
        if start_t is None and (i + 1) * dt >= WARMUP_S:
            start_pos = robot.data.root_link_pos_w[:, :2].clone()
            start_t = i * dt
        obs, _, dones, _ = env.step(policy(obs))
        fell = base.termination_manager.get_term("fell_over").float()
        falls += fell
        if i < steps - 1:  # the 20 s time-out resets every env on the last step
            never_reset &= ~dones.bool()
            end_pos = robot.data.root_link_pos_w[:, :2].clone()
        alive_t = torch.where(dones.bool(), torch.zeros_like(alive_t), alive_t + dt)
        ok = (alive_t >= WARMUP_S) & ~dones.bool()
        vel = torch.cat([robot.data.root_link_lin_vel_b[:, :2], robot.data.root_link_ang_vel_b[:, 2:3]], dim=1)
        v_sum += vel * ok[:, None]
        v_cnt += ok.float()

    # Cross-check: straight-line distance per second (envs that never reset).
    # For a straight command this should be close to the measured speed.
    disp = (end_pos - start_pos).norm(dim=1) / ((steps - 1) * dt - start_t)
    mean_v = (v_sum.sum(0) / v_cnt.sum().clamp(min=1)).tolist()
    per_env_v = v_sum / v_cnt.clamp(min=1)[:, None]
    err = (per_env_v - cmd).abs()
    return {
        "envs": n,
        "seconds": seconds,
        "envs_fell": int((falls > 0).sum()),
        "falls_total": int(falls.sum()),
        "falls_per_min": float(falls.sum() / (n * seconds / 60)),
        "cmd": [round(x, 3) for x in cmd[0].tolist()],
        "measured": [round(x, 3) for x in mean_v],
        "abs_err_vx": round(float(err[:, 0].mean()), 3),
        "abs_err_vy": round(float(err[:, 1].mean()), 3),
        "abs_err_wz": round(float(err[:, 2].mean()), 3),
        "disp_speed": round(float(disp[never_reset].mean()), 3) if never_reset.any() else None,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoints", nargs="+", required=True)
    p.add_argument("--commands", nargs="+", default=["0.2,0,0", "0.4,0,0", "-0.2,0,0", "0,0.2,0", "0,0,0.8", "0,0,0"])
    p.add_argument("--num-envs", type=int, default=64)
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--pushes", choices=["off", "on"], default="off")
    p.add_argument("--json-out")
    a = p.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    results = []
    for text in a.commands:
        cmd = parse_cmd(text)
        env = make_env(a.num_envs, cmd, a.pushes == "on", device)
        base = env
        base.common_step_counter = FINAL_STAGE_STEP
        wrapped = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(TASK).clip_actions)
        for ckpt in a.checkpoints:
            torch.manual_seed(0)
            policy = load_policy(wrapped, ckpt, device)
            # runner.load restores the checkpoint's step counter; override it so
            # every checkpoint is evaluated at the final curriculum stage, which
            # the reset below applies.
            base.common_step_counter = FINAL_STAGE_STEP
            wrapped.reset()
            r = evaluate(wrapped, policy, a.seconds)
            r.update(checkpoint="/".join(ckpt.rstrip("/").split("/")[-2:]), pushes=a.pushes)  # run folder + file
            # Sanity check: -1.0 means the action_rate curriculum is at its final stage.
            r["action_rate_w"] = base.reward_manager.get_term_cfg("action_rate_l2").weight
            results.append(r)
            print(json.dumps(r), flush=True)
        env.close()
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()

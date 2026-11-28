"""Gait analysis: how does a checkpoint walk sideways compared with forward?

Experiment E showed that more lateral commands do not make lateral walking
faster. This measures, per fixed command, what the legs actually do:
  - range of every joint actually used (5-95 percentile) vs its limits,
  - step frequency (foot height oscillation) and step length per axis,
  - foot spacing (left-right distance between the feet, base frame),
  - share of actions at the clip limit (is the policy asking for more?).

Run from the microduck_rl checkout with its venv:
    MUJOCO_GL=egl .venv/bin/python <this file> --checkpoint .../model_11995.pt --json-out gait.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eval_fixed_cmd", HERE / "eval_fixed_cmd.py")
efc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(efc)
from mjlab.rl import RslRlVecEnvWrapper  # noqa: E402
from mjlab.tasks.registry import load_rl_cfg  # noqa: E402


def quat_rotate_inv(q, v):
    """Rotate world vectors v (n, k, 3) into the frames of quaternions q (n, 4, wxyz)."""
    w, x, y, z = q[:, 0:1, None], q[:, 1:2, None], q[:, 2:3, None], q[:, 3:4, None]
    qv = torch.cat([x, y, z], dim=2).expand_as(v)
    t = 2.0 * torch.cross(qv, v, dim=2)
    return v - w * t + torch.cross(qv, t, dim=2)


@torch.no_grad()
def record(env, policy, seconds: float, warmup: float = 2.0):
    base = env.unwrapped
    robot = base.scene["robot"]
    dt = base.step_dt
    names = list(robot.joint_names)
    bodies = list(robot.body_names)
    feet = [i for i, b in enumerate(bodies) if "foot" in b.lower() or b.startswith("ankle")]
    clip = load_rl_cfg(efc.TASK).clip_actions
    q_log, feet_log, vel_log, act_log, alive = [], [], [], [], []
    obs = env.get_observations()
    for i in range(int(round((warmup + seconds) / dt))):
        act = policy(obs)
        obs, _, dones, _ = env.step(act)
        if i * dt < warmup:
            continue
        alive.append(~dones.bool())
        q_log.append(robot.data.joint_pos.clone())
        pos_w = robot.data.body_link_pos_w[:, feet, :] - robot.data.root_link_pos_w[:, None, :]
        feet_log.append(quat_rotate_inv(robot.data.root_link_quat_w, pos_w))
        vel_log.append(robot.data.root_link_lin_vel_b[:, :2].clone())
        act_log.append(act.clone())
    q = torch.stack(q_log)            # (T, n, joints)
    fp = torch.stack(feet_log)        # (T, n, feet, 3) base frame
    v = torch.stack(vel_log)          # (T, n, 2)
    a = torch.stack(act_log)
    ok = torch.stack(alive).all(0)    # envs that never fell / reset
    q, fp, v, a = q[:, ok], fp[:, ok], v[:, ok], a[:, ok]
    out = {"envs_used": int(ok.sum()), "joints": {}, "feet": [bodies[i] for i in feet]}
    lim = getattr(robot.data, "joint_pos_limits", None)
    for j, nme in enumerate(names):
        p01, lo, hi, p99 = torch.quantile(q[:, :, j].flatten().float(),
                                          torch.tensor([0.01, 0.05, 0.95, 0.99], device=q.device)).tolist()
        d = {"p01": round(p01, 3), "p05": round(lo, 3), "p95": round(hi, 3), "p99": round(p99, 3),
             "range": round(hi - lo, 3)}
        if lim is not None:
            d["limit"] = [round(float(lim[0, j, 0]), 3), round(float(lim[0, j, 1]), 3)]
        out["joints"][nme] = d
    # step frequency from the foot height (z) crossing its mean, averaged over envs and feet
    z = fp[..., 2] - fp[..., 2].mean(0, keepdim=True)
    crossings = ((z[1:] > 0) & (z[:-1] <= 0)).float().sum(0)   # (n, feet) up-crossings
    freq = float(crossings.mean() / (z.shape[0] * dt))
    speed = v.mean((0, 1)).tolist()
    out["step_frequency_hz"] = round(freq, 2)
    out["speed_b"] = [round(s, 3) for s in speed]
    out["step_length_m"] = [round(s / freq, 3) if freq > 0 else None for s in speed]
    if fp.shape[2] >= 2:
        out["foot_spacing_y_m"] = round(float((fp[:, :, 0, 1] - fp[:, :, 1, 1]).abs().mean()), 3)
        out["foot_spacing_y_range_m"] = round(float((fp[:, :, 0, 1] - fp[:, :, 1, 1]).abs().std()), 3)
    if clip:
        out["actions_at_clip"] = round(float((a.abs() >= 0.99 * clip).float().mean()), 3)
    out["action_abs_mean"] = round(float(a.abs().mean()), 3)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--commands", nargs="+", default=["0.3,0,0", "-0.3,0,0", "0,0.3,0", "0,-0.3,0", "0,0,0"])
    p.add_argument("--num-envs", type=int, default=16)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--json-out")
    a = p.parse_args()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    results = []
    for text in a.commands:
        cmd = efc.parse_cmd(text)
        env = efc.make_env(a.num_envs, cmd, False, device)
        env.common_step_counter = efc.FINAL_STAGE_STEP
        wrapped = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(efc.TASK).clip_actions)
        torch.manual_seed(0)
        policy = efc.load_policy(wrapped, a.checkpoint, device)
        env.common_step_counter = efc.FINAL_STAGE_STEP
        wrapped.reset()
        r = record(wrapped, policy, a.seconds)
        r["cmd"] = list(cmd)
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "joints"}), flush=True)
        env.close()
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()

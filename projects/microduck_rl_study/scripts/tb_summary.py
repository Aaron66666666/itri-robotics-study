"""Print key training scalars from an rsl_rl TensorBoard run directory.

Usage (inside the microduck_rl venv):
    python tb_summary.py <run_dir> [step ...]
"""
import sys

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

KEYS = ("error_vel_xy", "error_vel_yaw", "fell_over", "time_out")


def main() -> None:
    run_dir = sys.argv[1]
    ea = EventAccumulator(run_dir, size_guidance={"scalars": 0})
    ea.Reload()
    tags = ea.Tags()["scalars"]
    wanted = ["Train/mean_reward", "Train/mean_episode_length"]
    wanted += [t for t in tags if any(k in t for k in KEYS)]
    first = {t: ea.Scalars(t) for t in wanted}
    all_steps = sorted({e.step for t in wanted for e in first[t]})
    steps = [int(s) for s in sys.argv[2:]] or all_steps[:: max(1, len(all_steps) // 5)] + all_steps[-1:]
    for t in wanted:
        v = {e.step: e.value for e in first[t]}
        cells = " ".join(f"{s}:{v[s]:.2f}" for s in steps if s in v)
        print(t.split("/")[-1][:24].ljust(24), cells)


if __name__ == "__main__":
    main()

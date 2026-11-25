"""Export every scalar of an rsl_rl TensorBoard run to one CSV (step, tag, value).

Usage (inside the microduck_rl venv):
    python tb_to_csv.py <run_dir> <out.csv>
"""
import csv
import sys

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ea = EventAccumulator(sys.argv[1], size_guidance={"scalars": 0})
ea.Reload()
with open(sys.argv[2], "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["step", "tag", "value"])
    for tag in ea.Tags()["scalars"]:
        for e in ea.Scalars(tag):
            w.writerow([e.step, tag, f"{e.value:.6g}"])

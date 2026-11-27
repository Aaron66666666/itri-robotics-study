#!/usr/bin/env python3
"""Summarise S1-S5 scenario metrics (analyze.py output) per label.

  compare.py OUT.json LABEL=GLOB [LABEL=GLOB ...]
  e.g. compare.py cmp.json 'team_v5=runs/scenarios_v5/rep*/S?_team.metrics.json'

Per scenario and label: mean time to reach the cup over the runs that reached
it (and how many did), mean time stopped, and the minimum clearance to the
person (all, and while the vehicle moves). Clearance <= 0 is a collision.
"""
import glob
import json
import re
import statistics
import sys


def summary(files):
    ms = [json.load(open(f)) for f in files]
    reached = [m['reached_cup_s'] for m in ms if m['reached_cup_s'] is not None]
    moving = [m['min_clearance_moving_m'] for m in ms if m['min_clearance_moving_m'] is not None]
    clear = [m['min_clearance_m'] for m in ms if m['min_clearance_m'] is not None]
    return {'runs': len(ms), 'reached': len(reached),
            'reached_cup_s': round(statistics.mean(reached), 1) if reached else None,
            'stopped_s': round(statistics.mean(m['stopped_s'] for m in ms), 1),
            'min_clearance_m': round(min(clear), 2) if clear else None,
            'min_clearance_moving_m': round(min(moving), 2) if moving else None,
            'collision': any(c <= 0 for c in clear)}


def main():
    out, specs = sys.argv[1], [a.split('=', 1) for a in sys.argv[2:]]
    table = {}
    for label, pattern in specs:
        for f in sorted(glob.glob(pattern)):
            sc = re.search(r'(S\d)_', f.rsplit('/', 1)[-1]).group(1)
            table.setdefault(sc, {}).setdefault(label, []).append(f)
    result = {sc: {label: summary(fs) for label, fs in sorted(by.items())}
              for sc, by in sorted(table.items())}
    for sc, by in result.items():
        for label, s in by.items():
            print(sc, label, json.dumps(s, ensure_ascii=False))
    json.dump(result, open(out, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()

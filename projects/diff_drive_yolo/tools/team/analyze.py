#!/usr/bin/env python3
"""Metrics of one scenario run: safety (clearance to the person), efficiency
(time to reach the cup, time stopped), and the team's decisions."""
import csv
import json
import math
import re
import sys

PERSON_R = 0.25          # person footprint radius
BOX = (-1.15, 0.85, 0.5)  # vehicle footprint in its frame: x from, x to, half width


def clearance(row):
    dx, dy = row['px'] - row['vx'], row['py'] - row['vy']
    c, s = math.cos(row['vyaw']), math.sin(row['vyaw'])
    rx, ry = dx * c + dy * s, -dx * s + dy * c
    ex = max(0.0, rx - BOX[1], BOX[0] - rx)
    ey = max(0.0, abs(ry) - BOX[2])
    return math.hypot(ex, ey) - PERSON_R


def main(prefix):
    rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(prefix + '.poses.csv'))
            if None not in r.values() and '' not in r.values()]  # the last line may be cut off
    log = open(prefix + '.launch.log', errors='ignore').read()
    stamps = [(float(t), s) for t, s in re.findall(r'\[(\d+\.\d+)\] \[autonomy_controller\]: Autonomy state: (\S+)', log)]
    t_start = stamps[0][0] if stamps else rows[0]['t']
    done = next((t for t, s in stamps if s == 'target_action_complete'), None)
    # only the part of the run while the person is near (x > -2): the parked person is far away
    near = [r for r in rows if r['px'] > -2.0]
    min_clear = min((clearance(r) for r in near), default=None)
    # Clearance while the vehicle itself is moving: a person walking up to a
    # vehicle that has already stopped is not the vehicle closing the gap.
    moving = [b for a, b in zip(rows, rows[1:]) if b['px'] > -2.0
              and math.hypot(b['vx'] - a['vx'], b['vy'] - a['vy']) / max(1e-3, b['t'] - a['t']) > 0.01]
    min_clear_moving = min((clearance(r) for r in moving), default=None)
    stopped = 0.0
    for a, b in zip(rows, rows[1:]):
        if done and a['t'] > done:
            break
        v = math.hypot(b['vx'] - a['vx'], b['vy'] - a['vy']) / max(1e-3, b['t'] - a['t'])
        if v < 0.01 and a['t'] > t_start + 3.0:
            stopped += b['t'] - a['t']
    decisions = re.findall(r'Team decision: (\w+) \(([^)]*)\)', log)
    out = {'reached_cup_s': round(done - t_start, 1) if done else None,
           'stopped_s': round(stopped, 1),
           'min_clearance_m': round(min_clear, 3) if min_clear is not None else None,
           'min_clearance_moving_m': round(min_clear_moving, 3) if min_clear_moving is not None else None,
           'final_x': round(rows[-1]['vx'], 3),
           'person_stops': len(re.findall(r'Autonomy state: person_detected', log)),
           'team_decisions': [f'{m}: {r[:70]}' for m, r in decisions][:30]}
    print(json.dumps(out, ensure_ascii=False))
    json.dump(out, open(prefix + '.metrics.json', 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main(sys.argv[1])

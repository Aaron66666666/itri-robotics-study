#!/usr/bin/env python3
"""Seeded random person walk for the vehicle scenarios.

Prints 'DELAY SPEED PATH' for walk_person.py. Four kinds (seed % 4): cross in
front, come towards the vehicle and step into its path, pass alongside,
overtake from behind and cross. World frame: the vehicle starts at (0, 2)
facing +x and stops near x = 0.5 (front bumper about 1.4); the cup's table
covers x 2.45-3.15, y 1.55-2.45. Paths keep out of the vehicle body and the
table, and end at least 1.8 m to the side (or behind), so no run is blocked
forever by a person standing next to the vehicle.

  random_walk.py SEED            e.g. walk_person.py $(random_walk.py 3)
"""
import random
import sys


def walk(seed):
    r = random.Random(seed)
    side = r.choice((1, -1))                      # +1: starts on the left (y > 2)

    def lateral(lo, hi, s=1):
        return round(2 + s * side * r.uniform(lo, hi), 2)

    xc = round(r.choice((r.uniform(1.9, 2.3), r.uniform(3.4, 4.2))), 2)
    kind = seed % 4
    if kind == 0:      # cross in front of the vehicle
        path = [(xc, lateral(1.8, 2.4)), (xc, lateral(1.8, 2.4, -1))]
    elif kind == 1:    # come towards the vehicle beside its path, step in, then leave
        x1 = round(r.uniform(1.9, 2.25), 2)
        y = lateral(0.9, 1.1)
        path = [(round(r.uniform(4.6, 5.5), 2), y), (round(x1 + 0.2, 2), y), (x1, lateral(0.0, 0.3)),
                (x1, lateral(0.0, 0.3)), (x1, lateral(1.8, 2.4, r.choice((1, -1))))]
    elif kind == 2:    # pass alongside, in either direction
        y = lateral(1.1, 1.8)
        ends = [(5.0, y), (-3.0, y)]
        path = ends if r.random() < 0.5 else ends[::-1]
    else:              # overtake from behind along the side, then cross in front
        y = lateral(1.4, 1.8)
        path = [(-2.5, y), (xc, y), (xc, lateral(1.8, 2.4, -1))]
    delay = round(r.uniform(2.0, 12.0), 1)
    speed = round(r.uniform(0.3, 0.8), 2)
    return delay, speed, ';'.join(f'{x},{y}' for x, y in path)


if __name__ == '__main__':
    print(*walk(int(sys.argv[1])))

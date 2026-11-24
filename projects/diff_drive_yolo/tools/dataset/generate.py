#!/usr/bin/env python3
"""Generate a labeled YOLO dataset from worlds/yolo_datagen.sdf.

Start the world first (headless):
  gz sim -s -r --headless-rendering worlds/yolo_datagen.sdf
then:
  python3 generate.py --out DATASET --split train --count 1800 --seed 1

Writes DATASET/images/<split>/*.png, DATASET/labels/<split>/*.txt (YOLO:
class cx cy w h, normalized; class = COCO id) and DATASET/meta/*.jsonl
(scene description of every image). Use --start for chunked generation
(build_dataset.sh restarts Gazebo for every chunk of 200 images).
"""

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path

import cv2
from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.light_pb2 import Light
from gz.msgs10.pose_v_pb2 import Pose_V

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gzcapture import BoxCameraCapture  # noqa: E402

POOL = json.loads((Path(__file__).resolve().parent / 'pool.json')
                  .read_text())
WORLD = 'datagen'
W, H = 640, 480
MIN_BOX_PX = 6
ROBOT_CAM_HEIGHT = 0.575  # vehicle camera height in the robot worlds


def _request_worker(conn) -> None:
    """Separate process for service calls: a gz-transport request blocks
    and times out while the same process also receives image callbacks."""
    from gz.transport13 import Node
    types = {'Pose_V': Pose_V, 'Light': Light}
    node = Node()
    while True:
        job = conn.recv()
        if job is None:
            return
        service, type_name, payload, timeout = job
        req = types[type_name]()
        req.ParseFromString(payload)
        ok, rep = node.request(service, req, types[type_name], Boolean,
                               timeout)
        conn.send(bool(ok and rep.data))


class Requester:
    def __init__(self):
        ctx = mp.get_context('spawn')
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_request_worker, args=(child,),
                                daemon=True)
        self.proc.start()

    def call(self, service, msg, timeout=3000) -> bool:
        self.conn.send((service, type(msg).__name__,
                        msg.SerializeToString(), timeout))
        return self.conn.recv()


def quat(yaw=0.0, pitch=0.0):
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    return cy * cp, -sy * sp, cp * 0 + sp * cy, sy * cp  # w, x, y, z


def add_pose(req, name, x, y, z, yaw=0.0, pitch=0.0):
    pose = req.pose.add()
    pose.name = name
    pose.position.x, pose.position.y, pose.position.z = x, y, z
    w, qx, qy, qz = quat(yaw, pitch)
    pose.orientation.w, pose.orientation.x = w, qx
    pose.orientation.y, pose.orientation.z = qy, qz


def sample_scene(rng: random.Random) -> dict:
    cx, cy = rng.uniform(-3, 3), rng.uniform(-3, 3)
    placed, used = {}, set()

    def free_spot(radius, min_gap):
        for _ in range(50):
            ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(0, radius)
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            if all(math.hypot(x - px, y - py) >= min_gap
                   for px, py, _ in placed.values()):
                return x, y
        return None

    def pick(kind):
        options = [n for n in POOL[kind] if n not in used]
        if kind in ('bottle', 'cup') and f'{kind}_world' in options \
                and rng.random() < 0.3:
            return f'{kind}_world'   # favour the exact robot-world objects
        return rng.choice(options) if options else None

    scene = {'center': [cx, cy], 'objects': {}}
    if rng.random() < 0.35:   # a table with one target on it
        table = rng.choice(sorted(POOL['table']))
        height = POOL['table'][table]['height']
        placed[table] = (cx, cy, 0.0)
        used.add(table)
        kind = 'cup' if rng.random() < 0.6 else 'bottle'
        name = pick(kind)
        if name:
            used.add(name)
            scene['objects'][name] = [cx, cy, height, rng.uniform(-3.14, 3.14)]
    n_targets = rng.choices([0, 1, 2, 3], [0.08, 0.42, 0.32, 0.18])[0]
    for _ in range(n_targets):
        name = pick('bottle' if rng.random() < 0.5 else 'cup')
        spot = free_spot(1.0, 0.45) if name else None
        if spot:
            used.add(name)
            placed[name] = (*spot, 0.0)
            scene['objects'][name] = [*spot, 0.0, rng.uniform(-3.14, 3.14)]
    if rng.random() < 0.45:
        name, spot = pick('person'), free_spot(1.6, 0.6)
        if name and spot:
            used.add(name)
            placed[name] = (*spot, 0.0)
            scene['objects'][name] = [*spot, 0.0, rng.uniform(-3.14, 3.14)]
    for _ in range(rng.randint(0, 3)):
        name, spot = pick('distractor'), free_spot(1.6, 0.4)
        if name and spot:
            used.add(name)
            placed[name] = (*spot, 0.0)
            scene['objects'][name] = [*spot, 0.0, rng.uniform(-3.14, 3.14)]
    for name in placed:
        if name in POOL['table']:
            scene['objects'][name] = [*placed[name][:2], 0.0,
                                      rng.uniform(-3.14, 3.14)]

    robot_view = rng.random() < 0.25
    dist = rng.uniform(0.7, 4.5)
    azimuth = rng.uniform(0, 2 * math.pi)
    cam_x, cam_y = cx + dist * math.cos(azimuth), cy + dist * math.sin(azimuth)
    if robot_view:
        cam_z, pitch = ROBOT_CAM_HEIGHT, 0.0
    else:
        cam_z = rng.uniform(0.25, 1.3)
        pitch = math.atan2(cam_z - rng.uniform(0.1, 0.5), dist) + \
            rng.uniform(-0.08, 0.08)
    yaw = math.atan2(cy - cam_y, cx - cam_x) + rng.uniform(-0.25, 0.25)
    scene['camera'] = [cam_x, cam_y, cam_z, yaw, pitch]
    scene['robot_view'] = robot_view

    if rng.random() < 0.6:
        scene['objects'][rng.choice(POOL['mat'])] = [cx, cy, 0.0,
                                                     rng.uniform(0, 3.14)]
    if rng.random() < 0.35:   # backdrop behind the cluster, facing the camera
        back = math.atan2(cy - cam_y, cx - cam_x)
        gap = rng.uniform(1.5, 3.0)
        scene['objects'][rng.choice(POOL['wall'])] = [
            cx + gap * math.cos(back), cy + gap * math.sin(back), 0.0, back]
    return scene


def all_models() -> list[str]:
    names = []
    for key, value in POOL.items():
        names += list(value) if isinstance(value, dict) else value
    return names


def apply_scene(requester, scene: dict) -> None:
    req = Pose_V()
    for i, name in enumerate(all_models()):
        if name in scene['objects']:
            x, y, z, yaw = scene['objects'][name]
            add_pose(req, name, x, y, z, yaw)
        else:   # park far away and underground
            add_pose(req, name, -500 - 3 * i, 0, -50)
    x, y, z, yaw, pitch = scene['camera']
    add_pose(req, 'cam', x, y, z, yaw, pitch)
    if not requester.call(f'/world/{WORLD}/set_pose_vector', req):
        raise RuntimeError('set_pose_vector failed')


def set_light(requester, rng: random.Random) -> dict:
    azimuth, elevation = rng.uniform(0, 2 * math.pi), rng.uniform(0.35, 1.4)
    level = rng.uniform(0.55, 1.15)
    light = Light()
    light.name, light.type = 'sun', Light.DIRECTIONAL
    light.cast_shadows = True
    light.diffuse.r = light.diffuse.g = light.diffuse.b = level
    light.diffuse.a = 1.0
    light.specular.r = light.specular.g = light.specular.b = 0.3
    light.specular.a = 1.0
    light.direction.x = -math.cos(elevation) * math.cos(azimuth)
    light.direction.y = -math.cos(elevation) * math.sin(azimuth)
    light.direction.z = -math.sin(elevation)
    ok = requester.call(f'/world/{WORLD}/light_config', light)
    # fill light: off half of the time, otherwise random direction/level
    fill = Light()
    fill.name, fill.type, fill.cast_shadows = 'fill', Light.DIRECTIONAL, False
    fill_level = rng.uniform(0.4, 0.9) if rng.random() < 0.5 else 0.0
    fill_azimuth = rng.uniform(0, 2 * math.pi)
    fill.diffuse.r = fill.diffuse.g = fill.diffuse.b = fill_level
    fill.diffuse.a = 1.0
    fill.direction.x = -0.7 * math.cos(fill_azimuth)
    fill.direction.y = -0.7 * math.sin(fill_azimuth)
    fill.direction.z = -0.7
    ok_fill = requester.call(f'/world/{WORLD}/light_config', fill)
    return {'azimuth': azimuth, 'elevation': elevation, 'level': level,
            'fill_level': fill_level, 'fill_azimuth': fill_azimuth,
            'applied': ok and ok_fill}


def to_yolo(boxes) -> list[str]:
    lines = []
    for label, x1, y1, x2, y2 in boxes:
        x1, x2 = max(0.0, x1), min(float(W), x2)
        y1, y2 = max(0.0, y1), min(float(H), y2)
        if x2 - x1 < MIN_BOX_PX or y2 - y1 < MIN_BOX_PX or label < 1:
            continue
        lines.append(f'{label - 1} {(x1 + x2) / 2 / W:.6f} '
                     f'{(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} '
                     f'{(y2 - y1) / H:.6f}')
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--split', required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--start', type=int, default=0,
                        help='first image index (chunked generation)')
    args = parser.parse_args()
    out = Path(args.out)
    for sub in (f'images/{args.split}', f'labels/{args.split}', 'meta'):
        (out / sub).mkdir(parents=True, exist_ok=True)
    # one deterministic stream per chunk, so a retried chunk is identical
    rng = random.Random(f'{args.seed}-{args.start}')
    requester = Requester()   # start before any gz node exists here
    cap = BoxCameraCapture()
    cap.get(after=-1, timeout=30)   # wait until the sensor is running
    light = set_light(requester, rng)
    started = time.time()
    meta_path = out / 'meta' / f'{args.split}_{args.start:05d}.jsonl'
    with meta_path.open('w') as meta:
        for index in range(args.start, args.start + args.count):
            if (index - args.start) % 6 == 0:
                light = set_light(requester, rng)
            scene = sample_scene(rng)
            before = cap.latest_stamp()
            apply_scene(requester, scene)
            # two frames after the command so the new poses are rendered
            stamp, image, boxes = cap.get(after=before + 0.11, timeout=10)
            name = f'{args.split}_{args.seed}_{index:05d}'
            cv2.imwrite(str(out / 'images' / args.split / f'{name}.png'),
                        image)
            lines = to_yolo(boxes)
            (out / 'labels' / args.split / f'{name}.txt').write_text(
                '\n'.join(lines) + ('\n' if lines else ''))
            meta.write(json.dumps({'image': name, 'stamp': stamp,
                                   'light': light, **scene,
                                   'labels': lines}) + '\n')
            done = index - args.start + 1
            if done % 100 == 0:
                rate = done / (time.time() - started)
                print(f'{args.split}: {index + 1} ({rate:.1f} img/s)',
                      flush=True)
    print(f'done {args.split}: {args.count} images in '
          f'{time.time() - started:.0f} s', flush=True)
    requester.conn.send(None)
    os._exit(0)   # avoid a gz-transport teardown crash at interpreter exit


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Write worlds/yolo_datagen.sdf: a pool of labeled objects for synthetic
YOLO data. generate.py moves pool members into view (or parks them far away)
for every image.

Gazebo label = COCO class id + 1 (label 0 is background for the sensor):
  person 1, bottle 40, cup 42.  Unlabeled models are never boxed.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / 'worlds' / 'yolo_datagen.sdf'
POOL_FILE = Path(__file__).resolve().parent / 'pool.json'
LABEL = {'person': 1, 'bottle': 40, 'cup': 42}
PERSON_URIS = [
    'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Casual female',
    'https://fuel.gazebosim.org/1.0/OpenRobotics/models/MaleVisitorOnPhone',
]


def mat(rgb, alpha=1.0):
    r, g, b = rgb
    color = f'{r} {g} {b} {alpha}'
    return (f'<material><ambient>{color}</ambient><diffuse>{color}</diffuse>'
            f'<specular>0.3 0.3 0.3 1</specular></material>'
            + (f'<transparency>{1 - alpha}</transparency>' if alpha < 1
               else ''))


def cyl(name, z, r, length, rgb, alpha=1.0):
    return (f'<visual name="{name}"><pose>0 0 {z:.4f} 0 0 0</pose>'
            f'<geometry><cylinder><radius>{r:.4f}</radius>'
            f'<length>{length:.4f}</length></cylinder></geometry>'
            f'{mat(rgb, alpha)}</visual>')


def box(name, xyz, size, rgb):
    x, y, z = xyz
    sx, sy, sz = size
    return (f'<visual name="{name}"><pose>{x} {y} {z} 0 0 0</pose>'
            f'<geometry><box><size>{sx} {sy} {sz}</size></box></geometry>'
            f'{mat(rgb)}</visual>')


def labeled(name, label, body):
    return (f'<model name="{name}"><static>true</static>'
            f'<pose>0 0 -50 0 0 0</pose><link name="link">{body}</link>'
            f'<plugin filename="gz-sim-label-system" '
            f'name="gz::sim::systems::Label"><label>{label}</label></plugin>'
            f'</model>')


def bottle(s, body, label_rgb, cap, alpha=1.0, base=None):
    """Same shape as the world's bottle, scaled by s. base = height of the
    bottom above the model origin (world bottle floats: base 0.125)."""
    z0 = (0.275 * s) if base is None else base + 0.275 * s
    return (cyl('body', z0, 0.15 * s, 0.55 * s, body, alpha)
            + cyl('neck', z0 + 0.325 * s, 0.075 * s, 0.16 * s, body, alpha)
            + cyl('cap', z0 + 0.435 * s, 0.08 * s, 0.06 * s, cap)
            + cyl('label', z0 + 0.02 * s, 0.151 * s, 0.18 * s, label_rgb))


def mug(s, rgb):
    return (cyl('body', 0.15 * s, 0.13 * s, 0.30 * s, rgb)
            + cyl('coffee', 0.295 * s, 0.115 * s, 0.012 * s,
                  (0.25, 0.12, 0.04))
            + box('handle_top', (0, 0.17 * s, 0.24 * s),
                  (0.035 * s, 0.09 * s, 0.035 * s), rgb)
            + box('handle_side', (0, 0.205 * s, 0.15 * s),
                  (0.035 * s, 0.035 * s, 0.17 * s), rgb)
            + box('handle_bottom', (0, 0.17 * s, 0.06 * s),
                  (0.035 * s, 0.09 * s, 0.035 * s), rgb))


def plain(name, body):
    return (f'<model name="{name}"><static>true</static>'
            f'<pose>0 0 -50 0 0 0</pose><link name="link">{body}</link>'
            '</model>')


GREEN, BROWN, BLUE = (0.08, 0.65, 0.12), (0.4, 0.2, 0.05), (0.1, 0.3, 0.75)
CREAM, WHITE, RED = (0.95, 0.9, 0.7), (0.95, 0.95, 0.95), (0.8, 0.1, 0.1)

BOTTLES = {  # name: (scale, body, label, cap, alpha, base)
    'bottle_world': (1.0, GREEN, CREAM, (0.95, 0.15, 0.05), 1.0, 0.125),
    'bottle_1': (0.5, GREEN, CREAM, RED, 1.0, None),
    'bottle_2': (0.35, BROWN, WHITE, (0.9, 0.75, 0.2), 1.0, None),
    'bottle_3': (0.6, BLUE, WHITE, WHITE, 1.0, None),
    'bottle_4': (0.4, (0.75, 0.85, 0.9), RED, WHITE, 0.55, None),
    'bottle_5': (1.0, (0.1, 0.18, 0.1), CREAM, (0.1, 0.1, 0.1), 1.0, None),
    'bottle_6': (0.3, GREEN, WHITE, RED, 1.0, None),
    'bottle_7': (0.8, BROWN, CREAM, (0.9, 0.75, 0.2), 1.0, None),
}
CUPS = {  # name: (scale, color)
    'cup_world': (1.0, (0.92, 0.92, 0.92)),
    'cup_1': (0.6, (0.8, 0.1, 0.1)), 'cup_2': (0.5, (0.15, 0.3, 0.8)),
    'cup_3': (0.4, (0.9, 0.75, 0.1)), 'cup_4': (0.8, (0.12, 0.12, 0.12)),
    'cup_5': (0.35, (0.2, 0.6, 0.3)), 'cup_6': (0.45, (0.92, 0.92, 0.92)),
}
TABLES = {  # name: (top height, top size xy, color)
    'table_1': (0.15, (0.7, 0.9), (0.55, 0.35, 0.18)),
    'table_2': (0.45, (0.8, 0.6), (0.6, 0.6, 0.62)),
    'table_3': (0.30, (0.5, 0.5), (0.9, 0.9, 0.88)),
}
DISTRACTORS = {
    'box_1': box('b', (0, 0, 0.15), (0.3, 0.3, 0.3), (0.2, 0.4, 0.8)),
    'box_2': box('b', (0, 0, 0.1), (0.5, 0.2, 0.2), (0.8, 0.5, 0.1)),
    'box_3': box('b', (0, 0, 0.25), (0.2, 0.2, 0.5), (0.5, 0.5, 0.5)),
    'ball_1': ('<visual name="s"><pose>0 0 0.15 0 0 0</pose><geometry>'
               '<sphere><radius>0.15</radius></sphere></geometry>'
               + mat((0.9, 0.2, 0.2)) + '</visual>'),
    'ball_2': ('<visual name="s"><pose>0 0 0.1 0 0 0</pose><geometry>'
               '<sphere><radius>0.1</radius></sphere></geometry>'
               + mat((0.95, 0.95, 0.3)) + '</visual>'),
    'disc_1': cyl('d', 0.03, 0.25, 0.06, (0.3, 0.3, 0.35)),
    'disc_2': cyl('d', 0.02, 0.15, 0.04, (0.7, 0.2, 0.6)),
}
MATS = {'mat_1': (0.85, 0.8, 0.7), 'mat_2': (0.3, 0.3, 0.32),
        'mat_3': (0.5, 0.33, 0.2), 'mat_4': (0.6, 0.75, 0.85),
        # near-white floors: the robot worlds look like this under two lights
        'mat_5': (0.97, 0.97, 0.97), 'mat_6': (0.9, 0.9, 0.92)}
WALLS = {'wall_1': (0.95, 0.95, 0.92), 'wall_2': (0.6, 0.75, 0.6),
         'wall_3': (0.2, 0.25, 0.45)}


def main():
    parts, pool = [], {'bottle': [], 'cup': [], 'person': [], 'table': {},
                       'distractor': [], 'mat': [], 'wall': []}
    for name, (s, body, lab, cap, alpha, base) in BOTTLES.items():
        parts.append(labeled(name, LABEL['bottle'],
                             bottle(s, body, lab, cap, alpha, base)))
        pool['bottle'].append(name)
    for name, (s, rgb) in CUPS.items():
        parts.append(labeled(name, LABEL['cup'], mug(s, rgb)))
        pool['cup'].append(name)
    for i, uri in enumerate(PERSON_URIS, 1):
        parts.append(
            f'<include><name>person_{i}</name><uri>{uri}</uri>'
            f'<pose>0 0 -50 0 0 0</pose><plugin filename='
            f'"gz-sim-label-system" name="gz::sim::systems::Label">'
            f'<label>{LABEL["person"]}</label></plugin></include>')
        pool['person'].append(f'person_{i}')
    for name, (h, (sx, sy), rgb) in TABLES.items():
        parts.append(plain(name, box('top', (0, 0, h - 0.02),
                                     (sx, sy, 0.04), rgb)
                           + box('base', (0, 0, (h - 0.04) / 2),
                                 (sx * 0.6, sy * 0.6, h - 0.04),
                                 tuple(c * 0.8 for c in rgb))))
        pool['table'][name] = {'height': h, 'size': [sx, sy]}
    for name, body in DISTRACTORS.items():
        parts.append(plain(name, body))
        pool['distractor'].append(name)
    for name, rgb in MATS.items():
        parts.append(plain(name, box('m', (0, 0, 0.005), (6, 6, 0.01), rgb)))
        pool['mat'].append(name)
    for name, rgb in WALLS.items():
        parts.append(plain(name, box('w', (0, 0, 1.5), (0.1, 10, 3), rgb)))
        pool['wall'].append(name)

    world = f'''<?xml version="1.0"?>
<!-- Generated by tools/dataset/make_world.py: synthetic YOLO data world. -->
<sdf version="1.8">
<world name="datagen">
  <physics name="1ms" type="ignored"><real_time_factor>1.0</real_time_factor></physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
  <scene><ambient>0.4 0.4 0.4 1</ambient><background>0.8 0.85 0.9 1</background></scene>
  <light type="directional" name="sun"><cast_shadows>true</cast_shadows><pose>0 0 10 0 0 0</pose>
    <diffuse>1 1 1 1</diffuse><specular>0.3 0.3 0.3 1</specular><direction>0.5 0.1 -0.9</direction></light>
  <!-- second light, randomized (or switched off) by generate.py; the robot
       worlds use a front fill light like this -->
  <light type="directional" name="fill"><cast_shadows>false</cast_shadows><pose>0 0 5 0 0 0</pose>
    <diffuse>0 0 0 1</diffuse><specular>0.1 0.1 0.1 1</specular><direction>0.7 0.15 -0.7</direction></light>
  <model name="ground"><static>true</static><link name="link"><visual name="v"><geometry><plane><normal>0 0 1</normal><size>200 200</size></plane></geometry>
    {mat((0.7, 0.7, 0.7))}</visual></link></model>
  {chr(10).join("  " + p for p in parts)}
  <model name="cam"><static>true</static><pose>0 0 0.6 0 0 0</pose><link name="link">
    <sensor name="bbox" type="boundingbox_camera"><update_rate>20</update_rate><always_on>1</always_on><topic>/datagen/boxes</topic>
      <camera><box_type>2d</box_type><horizontal_fov>1.047</horizontal_fov><image><width>640</width><height>480</height></image>
      <clip><near>0.1</near><far>60</far></clip></camera></sensor>
    <!-- Ordinary camera at the same pose: the boundingbox camera's own image
         (/datagen/boxes_image) has the boxes drawn on it, so training images
         come from this sensor and only the boxes from the one above. -->
    <sensor name="rgb" type="camera"><update_rate>20</update_rate><always_on>1</always_on><topic>/datagen/rgb</topic>
      <camera><horizontal_fov>1.047</horizontal_fov><image><width>640</width><height>480</height><format>R8G8B8</format></image>
      <clip><near>0.1</near><far>60</far></clip></camera></sensor></link></model>
</world>
</sdf>
'''
    WORLD.write_text(world)
    POOL_FILE.write_text(json.dumps(pool, indent=1))
    print(f'wrote {WORLD} and {POOL_FILE}')


if __name__ == '__main__':
    main()

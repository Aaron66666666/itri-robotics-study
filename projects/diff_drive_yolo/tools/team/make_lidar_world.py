#!/usr/bin/env python3
"""Write worlds/diff_drive_camera_cup_person_lidar.sdf: the person world plus a
360-degree 2D lidar on vehicle_blue (scan plane 0.9 m above the ground, above
the chassis, the cup on its table and the parked vehicle; people are taller).
Everything else is unchanged, so baseline / team / team_lidar runs compare in
the same world.

--clutter also writes ..._lidar_clutter.sdf: the same plus two pillars beside
the path (one next to the vehicle, one ahead on the right) and a wall behind,
all taller than the scan plane, i.e. static things a lidar sees in a real room.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SRC = WS / 'worlds' / 'diff_drive_camera_cup_person.sdf'
DST = WS / 'worlds' / 'diff_drive_camera_cup_person_lidar.sdf'
LIDAR = """
<!-- 360-degree 2D lidar (added by tools/team/make_lidar_world.py): chassis
     centre, 0.4 m above it = 0.9 m above the ground. -->
        <sensor name="lidar_360" type="gpu_lidar">
          <pose>0 0 0.4 0 0 0</pose>
          <always_on>true</always_on>
          <update_rate>10</update_rate>
          <visualize>false</visualize>
          <topic>/vehicle_blue/scan</topic>
          <lidar>
            <scan>
              <horizontal>
                <samples>720</samples>
                <resolution>1</resolution>
                <min_angle>-3.14159</min_angle>
                <max_angle>3.14159</max_angle>
              </horizontal>
              <vertical>
                <samples>1</samples>
                <resolution>1</resolution>
                <min_angle>0</min_angle>
                <max_angle>0</max_angle>
              </vertical>
            </scan>
            <range>
              <min>0.3</min>
              <max>10.0</max>
              <resolution>0.01</resolution>
            </range>
          </lidar>
        </sensor>
"""


CLUTTER = """
    <!-- Static obstacles taller than the scan plane (make_lidar_world.py --clutter). -->
    <model name="pillar_left"><static>true</static><pose>0.3 2.95 0.6 0 0 0</pose>
      <link name="l"><collision name="c"><geometry><cylinder><radius>0.15</radius><length>1.2</length></cylinder></geometry></collision>
        <visual name="v"><geometry><cylinder><radius>0.15</radius><length>1.2</length></cylinder></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.6 0.6 0.6 1</diffuse></material></visual></link></model>
    <model name="pillar_right"><static>true</static><pose>1.2 0.8 0.6 0 0 0</pose>
      <link name="l"><collision name="c"><geometry><cylinder><radius>0.15</radius><length>1.2</length></cylinder></geometry></collision>
        <visual name="v"><geometry><cylinder><radius>0.15</radius><length>1.2</length></cylinder></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.6 0.6 0.6 1</diffuse></material></visual></link></model>
    <model name="wall_back"><static>true</static><pose>-4.5 2.0 0.75 0 0 0</pose>
      <link name="l"><collision name="c"><geometry><box><size>0.1 4.0 1.5</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>0.1 4.0 1.5</size></box></geometry>
          <material><ambient>0.7 0.7 0.65 1</ambient><diffuse>0.8 0.8 0.75 1</diffuse></material></visual></link></model>
"""


def main():
    s = SRC.read_text()
    anchor = '<sensor name="front_camera" type="camera">'
    i = s.index(anchor)
    j = s.index('</sensor>', i) + len('</sensor>')
    assert s.count(anchor) == 1
    out = s[:j] + '\n' + LIDAR + s[j:]
    DST.write_text(out)
    print(f'wrote {DST}')
    if '--clutter' in sys.argv:
        dst = DST.with_name(DST.stem + '_clutter.sdf')
        dst.write_text(out.replace('  </world>', CLUTTER + '  </world>'))
        print(f'wrote {dst}')


if __name__ == '__main__':
    main()

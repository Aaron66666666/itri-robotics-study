#!/usr/bin/env python3
"""Write worlds/diff_drive_camera_cup_person_lidar.sdf: the person world plus a
360-degree 2D lidar on vehicle_blue (scan plane 0.9 m above the ground, above
the chassis, the cup on its table and the parked vehicle; people are taller).
Everything else is unchanged, so baseline / team / team_lidar runs compare in
the same world.
"""
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


def main():
    s = SRC.read_text()
    anchor = '<sensor name="front_camera" type="camera">'
    i = s.index(anchor)
    j = s.index('</sensor>', i) + len('</sensor>')
    assert s.count(anchor) == 1
    DST.write_text(s[:j] + '\n' + LIDAR + s[j:])
    print(f'wrote {DST}')


if __name__ == '__main__':
    main()

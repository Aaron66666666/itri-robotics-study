#!/usr/bin/env python3
"""Record the static lidar map (cells hit in most scans) with nobody around.

  record_static_map.py OUT.json [SECONDS]
Needs Gazebo with the lidar world and bridges for /vehicle_blue/scan and the
odometry (record_static_map.sh starts them). Cells (0.1 m) in the odometry
frame, i.e. relative to the vehicle's start pose, like the team's tracks.
"""
import json
import math
import sys
import time

from nav_msgs.msg import Odometry
import rclpy
from rclpy.qos import qos_profile_sensor_data
from robot_control.team_logic import lidar_to_odom, MAP_RES
from sensor_msgs.msg import LaserScan


def main():
    out, seconds = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    rclpy.init()
    node = rclpy.create_node('record_static_map')
    st = {'pose': None, 'scans': 0, 'hits': {}}

    def on_odom(m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        st['pose'] = (p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))

    def on_scan(m):
        if st['pose'] is None:
            return
        pts = [(r * math.cos(m.angle_min + i * m.angle_increment), r * math.sin(m.angle_min + i * m.angle_increment))
               for i, r in enumerate(m.ranges) if math.isfinite(r) and m.range_min < r < m.range_max * 0.99]
        cells = {(math.floor(x / MAP_RES), math.floor(y / MAP_RES)) for x, y in lidar_to_odom(pts, st['pose'])}
        for c in cells:
            st['hits'][c] = st['hits'].get(c, 0) + 1
        st['scans'] += 1

    node.create_subscription(Odometry, '/model/vehicle_blue/odometry', on_odom, qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/vehicle_blue/scan', on_scan, qos_profile_sensor_data)
    t_end = time.time() + seconds
    while time.time() < t_end or st['scans'] == 0:
        rclpy.spin_once(node, timeout_sec=0.1)
        if time.time() > t_end + 20:
            sys.exit('no scans received')
    cells = sorted(c for c, n in st['hits'].items() if n >= 0.5 * st['scans'])
    json.dump({'resolution': MAP_RES, 'frame': 'odometry (vehicle start pose = origin)',
               'scans': st['scans'], 'cells': cells}, open(out, 'w'))
    print(f"{st['scans']} scans, {len(cells)} static cells -> {out}")


if __name__ == '__main__':
    main()

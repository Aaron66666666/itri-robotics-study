#!/bin/bash
# Print Gazebo pose of pick_cube (x y z)
source /opt/ros/jazzy/setup.bash
timeout 5 gz topic -e -t /world/ur5e_pick_place/pose/info -n 1 | python3 -c "
import sys,re
t=sys.stdin.read(); i=t.find('name: \"pick_cube\"'); s=t[i:i+400]
v=lambda k: float((re.search(k+r': (-?[0-9.e-]+)', s.split('orientation')[0]) or [0,0])[1])
print(f'cube x={v(\"x\"):.4f} y={v(\"y\"):.4f} z={v(\"z\"):.4f}')"

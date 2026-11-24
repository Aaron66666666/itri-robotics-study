#!/bin/bash
# moveperson.sh X Y [YAW] : move the test person (Gazebo set_pose); park with: moveperson.sh -3 2
source /opt/ros/jazzy/setup.bash
Y=${3:-0}; QZ=$(python3 -c "import math;print(math.sin($Y/2))"); QW=$(python3 -c "import math;print(math.cos($Y/2))")
gz service -s /world/diff_drive/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 1000 \
  --req "name: 'test_person', position: {x: $1, y: $2, z: 0}, orientation: {z: $QZ, w: $QW}" > /dev/null
echo "$(date +%s.%N) person x=$1 y=$2 yaw=$Y"

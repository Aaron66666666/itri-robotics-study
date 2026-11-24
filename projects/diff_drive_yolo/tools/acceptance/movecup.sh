#!/bin/bash
# movecup.sh Y : move the cup model to (2.8, Y, 0.15); Y=2 is in view.
source /opt/ros/jazzy/setup.bash
gz service -s /world/diff_drive/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 1000 \
  --req "name: 'yolo_test_cup', position: {x: 2.8, y: $1, z: 0.15}" > /dev/null
echo "$(date +%s.%N) cup y=$1"

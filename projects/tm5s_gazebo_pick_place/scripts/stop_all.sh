#!/bin/bash
# Stop everything started by start_moveit.sh / the vision tools.
PAT="[g]z sim|[m]ove_group|[r]viz2|[r]obot_state_publisher|[p]arameter_bridge|[i]mage_bridge|[s]pawner|[p]ick_place_demo|[r]ecord_flange.py"
pkill -INT -f "[r]os2 launch tm5s_gripper_demo"; sleep 3
pkill -f "$PAT"; sleep 2; pkill -9 -f "$PAT"; sleep 1
pgrep -f "$PAT" > /dev/null && echo "still running" || echo "stopped"

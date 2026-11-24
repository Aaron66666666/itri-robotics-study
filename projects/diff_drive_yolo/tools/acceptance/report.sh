#!/bin/bash
# report.sh NAME : summarize a run
S=${OUT:-/tmp/robot_acceptance}; N=$1; cd $S
echo "--- cmd"; cat $N.cmd
echo "--- states"; grep -E "Autonomy state|ERROR|Saved|died" $N.launch.log | sed -E 's/^\[[a-z_]+-[0-9]+\] //' | cut -c1-130
echo "--- params"; grep -E "confidence|stop_bbox|speed|target|timeout" $N.params.yaml
echo "--- gazebo world pose (end)"; grep -A4 position $N.gzpose.txt | head -5
echo "--- odom (t,x,y,yaw,vx)"; grep odom $N.csv | awk -F, -v k=${EVERY:-4} 'NR%k==1{print $1,$3,$4,$5,$6}' | head -${ROWS:-25}
echo "--- detections"; grep ',det,' $N.csv | awk -F, -v k=${DEVERY:-10} 'NR%k==1{print $1,$3}' | head -${ROWS:-25}
echo "--- nonzero cmd count / total"; grep ',cmd,' $N.csv | awk -F, '{t++; if ($3!=0||$4!=0) n++} END{print n+0, t+0}'

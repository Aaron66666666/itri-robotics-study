#!/bin/bash
D=$(cd "$(dirname "$0")" && pwd)
sleep 14; $D/movecup.sh 40; sleep 0.35; $D/movecup.sh 2     # brief loss during approach
sleep 3;  $D/movecup.sh 40; sleep 12; $D/movecup.sh 2       # long loss -> search -> timeout

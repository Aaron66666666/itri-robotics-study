#!/bin/bash
# During approach: person steps into view for 6 s, then leaves.
D=$(cd "$(dirname "$0")" && pwd)
sleep 9; $D/moveperson.sh 3.6 2.6 3.1416
sleep 6; $D/moveperson.sh -3 2

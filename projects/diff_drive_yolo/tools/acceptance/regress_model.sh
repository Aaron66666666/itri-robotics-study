#!/bin/bash
# Re-run the v3 regression scenarios (F1-F4) with another YOLO model.
# Usage: regress_model.sh MODEL.pt OUT_DIR
A=$(cd "$(dirname "$0")" && pwd); M=${1:?model}; export OUT=${2:?out}
mkdir -p "$OUT"
COMMON="device:=0 search_speed:=0.05 approach_speed:=0.05 alignment_speed:=0.15 target_action:=stop model_path:=$M"
CUP="target_class:=cup stop_bbox_dimension:=width stop_bbox_ratio:=0.185"
WORLD=worlds/diff_drive_camera_cup.sdf bash "$A/run.sh" F1_cup 60 $COMMON $CUP
HOOK=$A/hook_loss.sh WORLD=worlds/diff_drive_camera_cup.sdf bash "$A/run.sh" F2_loss 55 $COMMON $CUP search_duration:=3.0
HOOK=$A/hook_person.sh WORLD=worlds/diff_drive_camera_cup_person.sdf bash "$A/run.sh" F3_person 55 $COMMON $CUP
WORLD=worlds/diff_drive_camera_bottle.sdf bash "$A/run.sh" F4_bottle 70 $COMMON target_class:=bottle stop_bbox_dimension:=width stop_bbox_ratio:=0.22
for n in F1_cup F2_loss F3_person F4_bottle; do
  echo "== $n"; grep -a "Autonomy state" "$OUT/$n.launch.log" | sed 's/.*Autonomy state: //' | uniq | tr '\n' ' '; echo
  grep -A3 position "$OUT/$n.gzpose.txt" | grep -E " x:" | head -1
done

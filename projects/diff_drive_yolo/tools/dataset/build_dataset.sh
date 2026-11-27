#!/bin/bash
# Build the synthetic dataset: starts headless Gazebo with the data world and
# generates train/val/test with different seeds. Usage: build_dataset.sh OUT_DIR
# Images come from an ordinary camera (clean, v5). To rebuild the v1-v3 data,
# whose images have the boundingbox camera's drawn boxes on them:
#   IMAGE_TOPIC=/datagen/boxes_image build_dataset.sh OUT_DIR
set -e
# 'set -e' also stops the build if a chunk fails three times.
S=$(cd "$(dirname "$0")" && pwd); WS=$(cd "$S/../.." && pwd); OUT=${1:?OUT_DIR}
source /opt/ros/jazzy/setup.bash
mkdir -p "$OUT"
python3 "$S/make_world.py"
CHUNK=200
stop_gz() {  # never fatal under set -e
  kill "$GZ" 2>/dev/null || true
  pkill -f "[g]z sim" 2>/dev/null || true
  sleep 4
}
run_chunk() {  # split start count seed
  for attempt in 1 2 3; do
    timeout 600 gz sim -s -r --headless-rendering "$WS/worlds/yolo_datagen.sdf" > "$OUT/gz_$1_$2.log" 2>&1 &
    GZ=$!; sleep 15
    if timeout 400 python3 "$S/generate.py" --out "$OUT" --split "$1" --start "$2" --count "$3" --seed "$4" \
        --image-topic "${IMAGE_TOPIC:-/datagen/rgb}"; then
      stop_gz; return 0
    fi
    echo "chunk $1/$2 failed (attempt $attempt), restarting Gazebo"
    stop_gz
  done
  return 1
}
for spec in "train 2000 1" "val 400 2" "test 400 3"; do
  set -- $spec
  rm -rf "$OUT/images/$1" "$OUT/labels/$1"
  rm -f "$OUT"/meta/"$1"_*.jsonl "$OUT"/meta/"$1".jsonl
  for ((start = 0; start < $2; start += CHUNK)); do
    run_chunk "$1" "$start" "$CHUNK" "$3"
  done
done
NAMES=$(~/yolo_project/.venv/bin/python -I -c "
from ultralytics import YOLO; import os, json
m = YOLO(os.path.expanduser('~/yolo_project/yolo26n.pt'))
print(json.dumps([m.names[i] for i in range(len(m.names))]))")
cat > "$OUT/data.yaml" <<YAML
# Synthetic Gazebo dataset (person, bottle, cup) with COCO class ids, so a
# model trained on it stays a drop-in replacement for yolo26n.pt.
path: $OUT
train: images/train
val: images/val
test: images/test
names: $NAMES
YAML
echo "dataset ready: $OUT"

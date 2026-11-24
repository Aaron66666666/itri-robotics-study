#!/usr/bin/env python3
"""Write the v3 training config: synthetic data + COCO128 replay.

  make_replay_yaml.py DATASET_DIR [COCO128_DIR] [REPEAT]
DATASET_DIR is a build_dataset.sh output (has data.yaml); COCO128_DIR
defaults to ~/datasets/coco128 (Ultralytics downloads it on first use of
'coco128.yaml'); REPEAT (default 3) lists the COCO images several times so
about 16% of every epoch is real images. Writes DATASET_DIR/data_v3_replay.yaml.
"""
import re
import sys
from pathlib import Path

dataset = Path(sys.argv[1]).resolve()
coco = Path(sys.argv[2] if len(sys.argv) > 2 else
            Path.home() / 'datasets' / 'coco128').resolve()
repeat = int(sys.argv[3]) if len(sys.argv) > 3 else 3
if not (coco / 'images' / 'train2017').is_dir():
    sys.exit(f'COCO128 not found in {coco}; download it first, e.g. '
             "python -c \"from ultralytics.data.utils import "
             "check_det_dataset as c; c('coco128.yaml')\"")
names = re.search(r'^names: .*$', (dataset / 'data.yaml').read_text(),
                  re.M).group(0)
coco_lines = ''.join(f'  - {coco}/images/train2017\n' for _ in range(repeat))
out = dataset / 'data_v3_replay.yaml'
out.write_text(f'''# Synthetic Gazebo data + COCO128 replay x{repeat} (keeps the person class).
path: {dataset}
train:
  - {dataset}/images/train
{coco_lines}val: {dataset}/images/val
test: {dataset}/images/test
{names}
''')
print(f'wrote {out}')

"""Make a frame strip (one row of N frames per video) from play videos.

Usage:
    python make_strip.py out.png video1.mp4 [video2.mp4 ...] [--frames 6]
"""
import argparse

import imageio.v3 as iio
import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("videos", nargs="+")
    p.add_argument("--frames", type=int, default=6)
    p.add_argument("--skip", type=int, default=20, help="first frame index to use")
    p.add_argument("--crop", type=int, nargs=4, metavar=("Y0", "Y1", "X0", "X1"),
                   help="crop each frame (full resolution) instead of halving it")
    a = p.parse_args()
    rows = []
    for path in a.videos:
        f = iio.imread(path)
        idx = np.linspace(a.skip, len(f) - 1, a.frames).astype(int)
        if a.crop:
            y0, y1, x0, x1 = a.crop
            frames = [f[i][y0:y1, x0:x1] for i in idx]
        else:
            frames = [f[i][::2, ::2] for i in idx]
        rows.append(np.hstack(frames))
    iio.imwrite(a.out, np.vstack(rows))


if __name__ == "__main__":
    main()

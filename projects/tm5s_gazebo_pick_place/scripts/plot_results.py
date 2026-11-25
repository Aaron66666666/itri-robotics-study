"""Plot a TM5S pick-and-place run: top view of the table with the flange path,
place targets and measured cube positions, plus flange height and gripper
opening over time.

Usage: python3 plot_results.py <run_dir>   (reads results.csv, flange_path.csv)
"""
import csv
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

run = sys.argv[1]
path = list(csv.DictReader(open(os.path.join(run, 'flange_path.csv'))))
rows = list(csv.reader(open(os.path.join(run, 'results.csv'))))[1:]
t = [float(r['wall_t']) for r in path]
x = [float(r['x']) for r in path]
y = [float(r['y']) for r in path]
z = [float(r['z']) for r in path]
q = [float(r['finger_q']) for r in path]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={'width_ratios': [1, 1.25]})

# Top view (world frame). Table top: centre (0.65, 0.75), 1.0 x 1.2 m.
ax1.add_patch(Rectangle((0.15, 0.15), 1.0, 1.2, color='#c8a27a', alpha=0.35, label='table top'))
ax1.add_patch(Rectangle((-0.11, -0.11), 0.22, 0.22, color='#555', alpha=0.6, label='robot pedestal'))
sc = ax1.scatter(x, y, c=t, cmap='viridis', s=4, label='flange path (colour = time)')
for r in rows:
    n, tx, ty, mx, my, ex, ey = r[0], float(r[3]), float(r[4]), float(r[5]), float(r[6]), r[7], r[8]
    ax1.plot(tx, ty, 'o', ms=13, mfc='none', mec='#d62728', mew=2)
    ax1.plot(mx, my, 'x', ms=9, color='#d62728', mew=2)
    ax1.annotate(f'move {n}\nerr x {ex} mm, y {ey} mm', (tx, ty), textcoords='offset points',
                 xytext=(14, -6), fontsize=8.5)
ax1.plot([], [], 'o', ms=10, mfc='none', mec='#d62728', mew=2, label='place target')
ax1.plot([], [], 'x', ms=8, color='#d62728', mew=2, label='measured cube (Gazebo)')
ax1.set_xlim(-0.2, 1.15)
ax1.set_ylim(-0.2, 0.95)
ax1.set_aspect('equal')
ax1.set_xlabel('world x [m]')
ax1.set_ylabel('world y [m]')
ax1.set_title('Top view: flange path and cube placement')
ax1.legend(loc='lower right', fontsize=8)
fig.colorbar(sc, ax=ax1, label='time [s]', shrink=0.8)

# Height and gripper over time.
ax2.plot(t, z, color='#1f77b4', label='flange height z [m]')
ax2.axhline(0.70, color='#8c564b', ls='--', lw=1, label='table top (0.70 m)')
ax2.set_xlabel('time [s]')
ax2.set_ylabel('flange z [m]')
ax2.set_title('Flange height and gripper (3 pick-and-place moves)')
ax3 = ax2.twinx()
ax3.fill_between(t, 0, [v * 1000 for v in q], color='#ff7f0e', alpha=0.25, step='post',
                 label='finger closing [mm]')
ax3.set_ylabel('finger closing [mm]')
ax3.set_ylim(0, 120)
h1, l1 = ax2.get_legend_handles_labels()
h2, l2 = ax3.get_legend_handles_labels()
ax2.legend(h1 + h2, l1 + l2, loc='upper right', fontsize=8)

fig.suptitle('Techman TM5S + parallel gripper, Gazebo Harmonic + MoveIt 2 (ROS 2 Jazzy)', fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(run, 'plot_results.png'), dpi=130)

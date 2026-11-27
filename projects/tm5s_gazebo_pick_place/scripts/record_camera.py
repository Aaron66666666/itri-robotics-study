#!/usr/bin/env python3
"""Record a ROS image topic to an mp4, with a caption box read from a text file.

  record_camera.py OUT.mp4 [--topic /demo_camera/image] [--caption FILE] [--fps 10]

Used by demo_language_gui.sh with the demo world's recording camera; the
caption file is written by ai-agent/demo_team.py (current step and command).
Stops on Ctrl-C / SIGINT / SIGTERM and closes the file properly. Chinese text
needs a CJK font: the Windows fonts in /mnt/c/Windows/Fonts are used from WSL.
"""
import argparse
import signal
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image as PILImage, ImageDraw, ImageFont
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

FONTS = ['/mnt/c/Windows/Fonts/msjh.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']


def load_font(size):
    for f in FONTS:
        if Path(f).is_file():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('out')
    p.add_argument('--topic', default='/demo_camera/image')
    p.add_argument('--caption')
    p.add_argument('--fps', type=float, default=10.0)
    a = p.parse_args()
    rclpy.init()
    node = rclpy.create_node('record_camera')
    font = load_font(30)
    state = {'writer': None, 'frames': 0, 'caption': '', 'checked': 0.0, 'stop': False}

    def on_image(m):
        frame = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width, -1)[:, :, :3]
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if m.encoding.lower().startswith('rgb') else frame.copy()
        if state['writer'] is None:
            state['writer'] = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*'mp4v'), a.fps,
                                              (m.width, m.height))
        now = time.monotonic()
        if a.caption and now - state['checked'] > 0.3:
            try:
                state['caption'] = Path(a.caption).read_text().strip()
            except OSError:
                pass
            state['checked'] = now
        if state['caption']:
            img = PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img, 'RGBA')
            lines = state['caption'].splitlines()
            h = 18 + 42 * len(lines)
            draw.rectangle([0, 0, m.width, h], fill=(0, 0, 0, 160))
            for i, line in enumerate(lines):
                draw.text((20, 10 + 42 * i), line, font=font, fill=(255, 255, 255, 255))
            frame = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        state['writer'].write(frame)
        state['frames'] += 1

    node.create_subscription(Image, a.topic, on_image, qos_profile_sensor_data)

    def stop(*_):
        state['stop'] = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while not state['stop']:
        rclpy.spin_once(node, timeout_sec=0.2)
    if state['writer'] is not None:
        state['writer'].release()
    print(f"{state['frames']} frames -> {a.out}", flush=True)
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()

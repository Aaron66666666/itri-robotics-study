"""Capture paired (image, 2D boxes) from a Gazebo boundingbox_camera.

The sensor publishes boxes on TOPIC and the RGB image on TOPIC + '_image'
with the same header stamp; get() waits for a pair newer than a given sim
time so a capture never mixes a new pose with an old frame.
"""

import threading
import time

import numpy as np
from gz.msgs10.annotated_axis_aligned_2d_box_v_pb2 import \
    AnnotatedAxisAligned2DBox_V
from gz.msgs10.image_pb2 import Image
from gz.transport13 import Node


def _stamp(msg) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nsec * 1e-9


class BoxCameraCapture:
    def __init__(self, topic: str = '/datagen/boxes'):
        self.node = Node()
        self.lock = threading.Lock()
        self.images: dict[float, np.ndarray] = {}
        self.boxes: dict[float, list] = {}
        if not self.node.subscribe(Image, topic + '_image', self._on_image):
            raise RuntimeError(f'cannot subscribe {topic}_image')
        if not self.node.subscribe(AnnotatedAxisAligned2DBox_V, topic,
                                   self._on_boxes):
            raise RuntimeError(f'cannot subscribe {topic}')

    def _on_image(self, msg: Image) -> None:
        frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(
            msg.height, msg.width, 3)[:, :, ::-1].copy()  # RGB -> BGR
        with self.lock:
            self.images[_stamp(msg)] = frame
            self._trim(self.images)

    def _on_boxes(self, msg: AnnotatedAxisAligned2DBox_V) -> None:
        boxes = [(int(b.label), b.box.min_corner.x, b.box.min_corner.y,
                  b.box.max_corner.x, b.box.max_corner.y)
                 for b in msg.annotated_box]
        with self.lock:
            self.boxes[_stamp(msg)] = boxes
            self._trim(self.boxes)

    @staticmethod
    def _trim(store: dict) -> None:
        for key in sorted(store)[:-20]:
            del store[key]

    def latest_stamp(self) -> float:
        with self.lock:
            return max(self.images, default=-1.0)

    def get(self, after: float, timeout: float = 5.0):
        """Return (stamp, BGR image, boxes) for the first pair newer than
        `after` (sim seconds)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                common = sorted(t for t in self.images
                                if t in self.boxes and t > after)
                if common:
                    t = common[0]
                    return t, self.images[t], self.boxes[t]
            time.sleep(0.02)
        raise TimeoutError('no image/boxes pair received')

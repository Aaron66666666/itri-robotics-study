"""ROS 2 nodes of the vehicle team (logic in team_logic.py)."""
# team_tracker    /yolo/detections + odometry -> /team/tracks
# team_predictor  /team/tracks + odometry     -> /team/prediction (10 Hz)
# team_commander  /autonomy/cmd_vel_raw + /team/prediction -> vehicle cmd_vel (20 Hz)

import json
import math
import time

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String

from .team_logic import assess, CommanderLogic, PersonTracker

ODOM = '/model/vehicle_blue/odometry'


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class _OdomMixin:
    def _init_odom(self):
        self.pose = (0.0, 0.0, 0.0)
        self.speed = 0.0
        self.create_subscription(Odometry, ODOM, self._on_odom, qos_profile_sensor_data)

    def _on_odom(self, m):
        p = m.pose.pose
        self.pose = (p.position.x, p.position.y, yaw_of(p.orientation))
        self.speed = m.twist.twist.linear.x


class TrackerNode(Node, _OdomMixin):
    def __init__(self):
        super().__init__('team_tracker')
        self._init_odom()
        self.tracker = PersonTracker()
        self.pub = self.create_publisher(String, '/team/tracks', 10)
        self.create_subscription(String, '/yolo/detections', self._on_det, 10)

    def _on_det(self, msg):
        try:
            dets = json.loads(msg.data).get('detections', [])
        except (ValueError, AttributeError):
            return
        t = time.monotonic()
        tracks = self.tracker.update(dets, t, self.pose)
        out = {'t': t, 'tracks': []}
        for tr in tracks:
            x, y, vx, vy = tr.kf.state_at(t)
            out['tracks'].append({'id': tr.tid, 'x': round(x, 3), 'y': round(y, 3),
                                  'vx': round(vx, 3), 'vy': round(vy, 3), 'n': tr.n})
        self.pub.publish(String(data=json.dumps(out)))


class _TrackView:
    """A published track, extrapolated like a Kalman state (for assess())."""

    class _KF:
        def __init__(self, d, t0):
            self.d, self.t0 = d, t0

        def state_at(self, t):
            dt = t - self.t0
            d = self.d
            return d['x'] + d['vx'] * dt, d['y'] + d['vy'] * dt, d['vx'], d['vy']

    def __init__(self, d, t0):
        self.tid, self.n, self.kf = d['id'], d['n'], self._KF(d, t0)


class PredictorNode(Node, _OdomMixin):
    def __init__(self):
        super().__init__('team_predictor')
        self._init_odom()
        self.tracks_msg = None
        self.tracks_time = None
        self.pub = self.create_publisher(String, '/team/prediction', 10)
        self.create_subscription(String, '/team/tracks', self._on_tracks, 10)
        self.create_timer(0.1, self._tick)

    def _on_tracks(self, msg):
        self.tracks_msg = json.loads(msg.data)
        self.tracks_time = time.monotonic()

    def _tick(self):
        now = time.monotonic()
        if self.tracks_time is None or now - self.tracks_time > 1.0:
            pred = {'risk': 'STOP', 'ttc': None, 'track': None,
                    'reason': 'tracker silent (no camera detections for 1 s)'}
        else:
            views = [_TrackView(d, self.tracks_msg['t']) for d in self.tracks_msg['tracks']]
            pred = assess(views, now, self.pose, max(0.0, self.speed))
        pred['n_tracks'] = len(self.tracks_msg['tracks']) if self.tracks_msg else 0
        self.pub.publish(String(data=json.dumps(pred)))


class CommanderNode(Node):
    def __init__(self):
        super().__init__('team_commander')
        self.declare_parameter('cmd_vel_topic', '/model/vehicle_blue/cmd_vel')
        self.logic = CommanderLogic()
        self.raw, self.raw_time = Twist(), None
        self.pred, self.pred_time = None, 0.0
        self.pub = self.create_publisher(Twist, self.get_parameter('cmd_vel_topic').value, 10)
        self.decision_pub = self.create_publisher(String, '/team/decision', 10)
        self.create_subscription(Twist, '/autonomy/cmd_vel_raw', self._on_raw, 10)
        self.create_subscription(String, '/team/prediction', self._on_pred, 10)
        self.create_timer(0.05, self._tick)
        self.get_logger().info(
            'Team commander: base controller /autonomy/cmd_vel_raw -> vehicle cmd_vel')

    def _on_raw(self, m):
        self.raw, self.raw_time = m, time.monotonic()

    def _on_pred(self, m):
        self.pred, self.pred_time = json.loads(m.data), time.monotonic()

    def _tick(self):
        now = time.monotonic()
        lin, ang = (self.raw.linear.x, self.raw.angular.z) if (
            self.raw_time and now - self.raw_time < 0.5) else (0.0, 0.0)
        out_lin, out_ang, changed = self.logic.decide(lin, ang, self.pred, self.pred_time, now)
        cmd = Twist()
        cmd.linear.x, cmd.angular.z = out_lin, out_ang
        self.pub.publish(cmd)
        if changed:
            self.get_logger().info(f'Team decision: {self.logic.mode} ({self.logic.reason})')
            self.decision_pub.publish(String(data=json.dumps(
                {'mode': self.logic.mode, 'reason': self.logic.reason,
                 'ttc': (self.pred or {}).get('ttc'), 'track': (self.pred or {}).get('track')})))


def _spin(node_cls):
    rclpy.init()
    node = node_cls()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if isinstance(node, CommanderNode):
            node.pub.publish(Twist())  # leave the vehicle stopped
        node.destroy_node()
        rclpy.try_shutdown()


def tracker_main():
    _spin(TrackerNode)


def predictor_main():
    _spin(PredictorNode)


def commander_main():
    _spin(CommanderNode)

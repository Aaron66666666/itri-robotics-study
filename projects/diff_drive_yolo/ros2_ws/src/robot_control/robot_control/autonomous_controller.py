"""Rule-based autonomous behavior driven by YOLO detection JSON."""

import json
import time

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class AutonomyLogic:
    """Bounded search, visual approach, and target action logic."""

    def __init__(self, target_class='bottle', target_action='turn_left',
                 confidence_threshold=0.5, action_duration=1.5,
                 linear_speed=0.2, angular_speed=0.6, stale_timeout=1.0,
                 search_speed=0.1, search_duration=5.0,
                 approach_speed=0.1, stop_bbox_ratio=0.55,
                 alignment_speed=0.25, alignment_deadband=0.08,
                 target_loss_timeout=0.5, stop_bbox_dimension='height'):
        self.target_class = target_class.lower()
        self.target_action = target_action
        self.confidence_threshold = confidence_threshold
        self.action_duration = action_duration
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.stale_timeout = stale_timeout
        self.search_speed = search_speed
        self.search_duration = search_duration
        self.approach_speed = approach_speed
        self.stop_bbox_ratio = stop_bbox_ratio
        self.alignment_speed = alignment_speed
        self.alignment_deadband = alignment_deadband
        self.target_loss_timeout = target_loss_timeout
        if stop_bbox_dimension not in ('height', 'width'):
            raise ValueError("stop_bbox_dimension must be 'height' or 'width'")
        self.stop_bbox_dimension = stop_bbox_dimension
        self.last_message_time = None
        self.last_target_time = None
        self.search_started = None
        self.action_started = None
        self.target_latched = False
        self.last_command = ('stop', 0.0, 0.0)

    def update(self, payload, now=None):
        """Process detections and choose a safe search/approach/action command."""
        now = time.monotonic() if now is None else now
        self.last_message_time = now
        try:
            message = json.loads(payload)
            detections = message.get('detections', [])
            if not isinstance(detections, list):
                raise ValueError('detections must be a list')
        except (AttributeError, ValueError, TypeError, json.JSONDecodeError):
            self._reset_motion()
            return self.last_command

        try:
            valid = [
                detection for detection in detections
                if isinstance(detection, dict)
                and float(detection.get('confidence', 0.0))
                >= self.confidence_threshold
            ]
        except (TypeError, ValueError):
            self._reset_motion()
            return self.last_command

        person_visible = any(
            str(detection.get('class_name', '')).lower() == 'person'
            for detection in valid
        )
        targets = [
            detection for detection in valid
            if str(detection.get('class_name', '')).lower() == self.target_class
        ]

        if person_visible:
            self.action_started = None
            self.search_started = None
            # Keep an existing latch (action already started/completed) so the
            # action is not repeated, but never create one here: the robot
            # must resume approaching once the person has left.
            self.target_latched = self.target_latched and bool(targets)
            return self._set_command('person_detected', 0.0, 0.0)

        if not targets:
            if (self.last_target_time is not None
                    and now - self.last_target_time < self.target_loss_timeout):
                # Stop immediately on a missed frame; tolerate a brief gap
                # before resuming the bounded search behavior. Keep the
                # latch so a flickering target does not re-trigger the
                # target action after it has completed.
                self.action_started = None
                self.search_started = None
                return self._set_command('target_lost_wait', 0.0, 0.0)
            self.last_target_time = None
            self.action_started = None
            self.target_latched = False
            if self.search_started is None:
                self.search_started = now
            if now - self.search_started < self.search_duration:
                return self._set_command(
                    'search_forward', self.search_speed, 0.0)
            return self._set_command('search_timeout', 0.0, 0.0)

        self.search_started = None
        self.last_target_time = now
        target = max(targets, key=lambda item: float(item['confidence']))
        geometry = self._target_geometry(message, target)
        if geometry is None:
            return self._set_command('target_bbox_missing', 0.0, 0.0)
        horizontal_error, height_ratio, width_ratio = geometry
        size_ratio = (width_ratio if self.stop_bbox_dimension == 'width'
                      else height_ratio)

        if self.target_latched:
            if self.action_started is None:
                return self._set_command(
                    'target_action_complete', 0.0, 0.0)
            if now - self.action_started >= self.action_duration:
                self.action_started = None
                return self._set_command(
                    'target_action_complete', 0.0, 0.0)
            return self._action_command()

        if abs(horizontal_error) > self.alignment_deadband:
            turn = -self.alignment_speed if horizontal_error > 0 else self.alignment_speed
            return self._set_command('align_to_target', 0.0, turn)

        if size_ratio < self.stop_bbox_ratio:
            return self._set_command(
                'approach_target', self.approach_speed, 0.0)

        self.target_latched = True
        self.action_started = now
        return self._action_command()

    @staticmethod
    def _target_geometry(message, detection):
        """Return center error, bbox height ratio and bbox width ratio."""
        bbox = detection.get('bbox_xyxy')
        image_size = message.get('image_size', {})
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
            image_width = float(image_size['width'])
            image_height = float(image_size['height'])
            if image_width <= 0 or image_height <= 0:
                return None
        except (TypeError, ValueError, KeyError):
            return None
        center_x = (x1 + x2) / 2.0
        horizontal_error = center_x / image_width - 0.5
        height_ratio = max(0.0, y2 - y1) / image_height
        width_ratio = max(0.0, x2 - x1) / image_width
        return horizontal_error, height_ratio, width_ratio

    def command(self, now=None):
        """Return the current command; stop safely when detections go stale."""
        now = time.monotonic() if now is None else now
        if (self.last_message_time is None
                or now - self.last_message_time > self.stale_timeout):
            self._reset_motion()
            return 'stale_detections', 0.0, 0.0
        if self.action_started is not None:
            if now - self.action_started >= self.action_duration:
                self.action_started = None
                self.last_command = ('target_action_complete', 0.0, 0.0)
            else:
                return self._action_command()
        return self.last_command

    def _set_command(self, reason, linear, angular):
        self.last_command = (reason, linear, angular)
        return self.last_command

    def _reset_motion(self):
        self.search_started = None
        self.last_target_time = None
        self.action_started = None
        self.target_latched = False
        self.last_command = ('stop', 0.0, 0.0)

    def _action_command(self):
        actions = {
            'turn_left': (0.0, self.angular_speed),
            'turn_right': (0.0, -self.angular_speed),
            'move_forward': (self.linear_speed, 0.0),
            'stop': (0.0, 0.0),
        }
        linear, angular = actions.get(self.target_action, (0.0, 0.0))
        return self._set_command(
            f'target_action:{self.target_action}', linear, angular)


class AutonomousController(Node):
    """Consume /yolo/detections and publish safe velocity commands."""

    def __init__(self):
        super().__init__('autonomy_controller')
        self.declare_parameter('detections_topic', '/yolo/detections')
        self.declare_parameter('cmd_vel_topic', '/model/vehicle_blue/cmd_vel')
        self.declare_parameter('target_class', 'bottle')
        self.declare_parameter('target_action', 'turn_left')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('action_duration', 1.5)
        self.declare_parameter('linear_speed', 0.2)
        self.declare_parameter('angular_speed', 0.6)
        self.declare_parameter('stale_timeout', 1.0)
        self.declare_parameter('search_speed', 0.1)
        self.declare_parameter('search_duration', 5.0)
        self.declare_parameter('approach_speed', 0.1)
        self.declare_parameter('stop_bbox_ratio', 0.55)
        self.declare_parameter('alignment_speed', 0.25)
        self.declare_parameter('alignment_deadband', 0.08)
        self.declare_parameter('target_loss_timeout', 0.5)
        # 'width' suits targets whose bottom is cropped when close.
        self.declare_parameter('stop_bbox_dimension', 'height')

        def get(name):
            return self.get_parameter(name).value
        self.logic = AutonomyLogic(
            target_class=get('target_class'), target_action=get('target_action'),
            confidence_threshold=float(get('confidence_threshold')),
            action_duration=float(get('action_duration')),
            linear_speed=float(get('linear_speed')),
            angular_speed=float(get('angular_speed')),
            stale_timeout=float(get('stale_timeout')),
            search_speed=float(get('search_speed')),
            search_duration=float(get('search_duration')),
            approach_speed=float(get('approach_speed')),
            stop_bbox_ratio=float(get('stop_bbox_ratio')),
            alignment_speed=float(get('alignment_speed')),
            alignment_deadband=float(get('alignment_deadband')),
            target_loss_timeout=float(get('target_loss_timeout')),
            stop_bbox_dimension=str(get('stop_bbox_dimension')),
        )
        self.publisher = self.create_publisher(Twist, get('cmd_vel_topic'), 10)
        self.subscription = self.create_subscription(
            String, get('detections_topic'), self.detections_callback, 10)
        self.timer = self.create_timer(0.1, self.publish_command)
        self.last_reason = None
        self.get_logger().info(
            f"Listening {get('detections_topic')}; publishing {get('cmd_vel_topic')}; "
            f"person stops; searching/approaching {get('target_class')} before "
            f"{get('target_action')}"
        )

    def detections_callback(self, message):
        reason, _, _ = self.logic.update(message.data)
        if reason != self.last_reason:
            self.get_logger().info(f'Autonomy state: {reason}')
            self.last_reason = reason

    def publish_command(self):
        reason, linear, angular = self.logic.command()
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        self.publisher.publish(message)
        if reason != self.last_reason:
            self.get_logger().info(f'Autonomy state: {reason}')
            self.last_reason = reason


def main(args=None):
    rclpy.init(args=args)
    node = AutonomousController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.publisher.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

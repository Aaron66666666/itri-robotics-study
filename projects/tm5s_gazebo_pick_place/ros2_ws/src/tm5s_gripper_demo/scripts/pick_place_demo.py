#!/usr/bin/env python3
"""Techman TM5S + parallel gripper pick-and-place through MoveIt 2 (no moveit_py).

Same flow as the UR5e project (projects/ur5e_gazebo_pick_place); only the arm
group, joint names, end link and ready pose differ.

Stages (each includes the previous ones):
  scene  - add work table + cube as MoveIt collision objects (matches the
           Gazebo world pick_place_world.sdf)
  joints - joint-space goal for the arm (tmr_arm)
  ee     - end-effector (flange) pose goal above the cube + gripper open/close
  pick   - full pick-and-place: approach, grasp, attach, lift, move, place,
           release, detach, retreat

Usage:
  ros2 run tm5s_gripper_demo pick_place_demo.py --stage pick
"""

import argparse
import sys
import time

from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import Pose, PoseStamped, Quaternion
from moveit_msgs.action import ExecuteTrajectory, MoveGroup
from moveit_msgs.msg import (AttachedCollisionObject, CollisionObject,
                             Constraints, JointConstraint,
                             MotionPlanRequest, OrientationConstraint,
                             PlanningOptions, PlanningScene,
                             PositionConstraint, RobotState)
from moveit_msgs.srv import (ApplyPlanningScene, GetCartesianPath,
                             GetPositionIK)
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from trajectory_msgs.msg import JointTrajectoryPoint

ARM_GROUP = 'tmr_arm'
EE_LINK = 'flange'
FRAME = 'world'
ARM_JOINTS = ['joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6']
FINGER_JOINTS = ['left_finger_joint', 'right_finger_joint']
FINGER_LINKS = ['left_finger', 'right_finger', 'gripper_base', 'gripper_adapter']

# Scene geometry copied from pick_place_world.sdf (world frame).
TABLE_TOP_CENTER = (0.65, 0.75, 0.35 + 0.32)    # top box centre
TABLE_TOP_SIZE = (1.0, 1.2, 0.06)
TABLE_TOP_Z = TABLE_TOP_CENTER[2] + TABLE_TOP_SIZE[2] / 2   # 0.70
TABLE_LEG_SIZE = (0.06, 0.06, 0.28)
TABLE_LEG_OFFSETS = [(-0.42, -0.52), (0.42, -0.52), (-0.42, 0.52),
                     (0.42, 0.52)]
CUBE_SIZE = 0.06
PEDESTAL_SIZE = (0.22, 0.22, 0.69)   # robot_pedestal, top 1 cm below base

# Gripper geometry (urdf/tm5s_gripper.urdf.xacro): finger centre is
# 0.075 + 0.045 + 0.045 = 0.165 m along flange +z; finger tip at 0.21 m.
FINGER_TIP_OFFSET = 0.21
GRIPPER_BODY_BOTTOM = 0.125   # gripper_base spans 0.075-0.125 m along flange +z
GRASP_TOOL_Z_ABOVE_CUBE_BOTTOM = FINGER_TIP_OFFSET + 0.012  # tips 12 mm above table
APPROACH_HEIGHT = 0.12
# Finger joint (left; right is mirrored: -q) at which the fingers touch a 6 cm
# cube: finger centre 0.07 - q, inner face 0.07 - q - 0.009 = 0.03.
OPEN_Q = 0.0
GRASP_Q = 0.036          # 5 mm total squeeze beyond contact (q=0.031)

# flange +z pointing down (roll = pi).
DOWN = Quaternion(x=1.0, y=0.0, z=0.0, w=0.0)


def cylinder(name, radius, height, xyz):
    obj = box(name, (0.0, 0.0, 0.0), xyz)
    obj.primitives = [SolidPrimitive(type=SolidPrimitive.CYLINDER,
                                     dimensions=[height, radius])]
    return obj


def box(name, size, xyz, operation=CollisionObject.ADD):
    obj = CollisionObject()
    obj.header.frame_id = FRAME
    obj.id = name
    prim = SolidPrimitive(type=SolidPrimitive.BOX, dimensions=list(size))
    pose = Pose()
    pose.position.x, pose.position.y, pose.position.z = xyz
    pose.orientation.w = 1.0
    obj.primitives = [prim]
    obj.primitive_poses = [pose]
    obj.operation = operation
    return obj


class PickPlace(Node):

    def __init__(self, args):
        super().__init__('pick_place_demo')
        self.args = args
        # Finger joint q where a finger touches an object: inner face at
        # 0.07 - q - 0.009 = radius (half-width) -> squeeze 5 mm past contact.
        if args.grasp_q is not None:
            self.grasp_q = args.grasp_q
        elif args.object_shape == 'box':
            self.grasp_q = GRASP_Q
        else:
            self.grasp_q = min(0.04, 0.061 - args.object_radius + 0.005)
        self.joint_state = None
        self.create_subscription(JointState, '/joint_states',
                                 self._on_joints, 10)
        self.scene_cli = self.create_client(ApplyPlanningScene,
                                            '/apply_planning_scene')
        self.ik_cli = self.create_client(GetPositionIK, '/compute_ik')
        self.cart_cli = self.create_client(GetCartesianPath,
                                           '/compute_cartesian_path')
        self.move_ac = ActionClient(self, MoveGroup, '/move_action')
        self.exec_ac = ActionClient(self, ExecuteTrajectory,
                                    '/execute_trajectory')
        self.grip_ac = ActionClient(
            self, FollowJointTrajectory,
            '/parallel_gripper_controller/follow_joint_trajectory')

    # ------------------------------------------------------------ helpers
    def _on_joints(self, msg):
        self.joint_state = msg

    def log(self, text):
        self.get_logger().info(text)

    def wait(self, future, timeout=60.0):
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if not future.done():
            raise RuntimeError('timed out waiting for MoveIt/controller')
        return future.result()

    def wait_ready(self):
        for cli in (self.scene_cli, self.ik_cli, self.cart_cli):
            if not cli.wait_for_service(timeout_sec=30.0):
                raise RuntimeError(f'service {cli.srv_name} unavailable')
        for ac in (self.move_ac, self.exec_ac, self.grip_ac):
            if not ac.wait_for_server(timeout_sec=30.0):
                raise RuntimeError('action server unavailable')
        end = time.time() + 30.0
        while self.joint_state is None:
            rclpy.spin_once(self, timeout_sec=0.1)
            if time.time() > end:
                raise RuntimeError('no /joint_states for 30 s (is joint_state_broadcaster active?)')

    def joints(self, names):
        rclpy.spin_once(self, timeout_sec=0.05)
        js = dict(zip(self.joint_state.name, self.joint_state.position))
        return [js[n] for n in names]

    def apply_scene(self, scene):
        scene.is_diff = True
        scene.robot_state.is_diff = True
        req = ApplyPlanningScene.Request(scene=scene)
        if not self.wait(self.scene_cli.call_async(req)).success:
            raise RuntimeError('apply_planning_scene failed')

    # -------------------------------------------------------------- scene
    def add_scene(self):
        objs = [box('table_top', TABLE_TOP_SIZE, TABLE_TOP_CENTER)]
        tx, ty = TABLE_TOP_CENTER[0], TABLE_TOP_CENTER[1]
        for i, (dx, dy) in enumerate(TABLE_LEG_OFFSETS):
            objs.append(box(f'table_leg_{i}', TABLE_LEG_SIZE,
                            (tx + dx, ty + dy, 0.35 + 0.14)))
        objs.append(box('robot_pedestal', PEDESTAL_SIZE,
                        (0.0, 0.0, PEDESTAL_SIZE[2] / 2)))
        a = self.args
        if a.object_shape == 'box':
            obj_xyz = (a.cube_x, a.cube_y, TABLE_TOP_Z + CUBE_SIZE / 2)
            objs.append(box(a.object_id, (CUBE_SIZE,) * 3, obj_xyz))
        else:
            obj_xyz = (a.cube_x, a.cube_y, TABLE_TOP_Z + a.object_height / 2)
            objs.append(cylinder(a.object_id, a.object_radius, a.object_height, obj_xyz))
        for spec in a.obstacle or []:
            name, ox, oy, orad, oh = spec.split(',')
            objs.append(cylinder(name, float(orad), float(oh),
                                 (float(ox), float(oy), TABLE_TOP_Z + float(oh) / 2)))
        cube_xyz = obj_xyz
        scene = PlanningScene()
        scene.world.collision_objects = objs
        # Clear every object that may still be attached from an earlier run:
        # a run that failed while holding the cup left it attached, and the
        # next run (picking the bottle) then failed with START_STATE_IN_COLLISION
        # (2026-11-28).
        ids = {self.args.object_id, 'pick_cube', 'cup', 'bottle'}
        ids |= {spec.split(',')[0] for spec in self.args.obstacle or []}
        detached = []
        for oid in sorted(ids):
            d = AttachedCollisionObject(link_name=EE_LINK)
            d.object.id = oid
            d.object.operation = CollisionObject.REMOVE
            detached.append(d)
        self.apply_scene(PlanningScene(
            robot_state=RobotState(attached_collision_objects=detached,
                                   is_diff=True)))
        self.apply_scene(scene)
        self.log(f'Collision scene: pedestal, table top z={TABLE_TOP_Z:.3f}, '
                 '4 legs, '
                 f'{self.args.object_id} ({self.args.object_shape}) at '
                 f'({cube_xyz[0]:.3f}, {cube_xyz[1]:.3f}, {cube_xyz[2]:.3f})'
                 + (f', obstacles {self.args.obstacle}' if self.args.obstacle else ''))

    # ---------------------------------------------------------- motions
    def move_joints(self, target, label):
        goal = MoveGroup.Goal()
        req = MotionPlanRequest()
        req.group_name = ARM_GROUP
        req.num_planning_attempts = 5
        req.allowed_planning_time = 10.0
        req.max_velocity_scaling_factor = self.args.speed
        req.max_acceleration_scaling_factor = self.args.speed
        c = Constraints()
        for name, value in zip(ARM_JOINTS, target):
            c.joint_constraints.append(JointConstraint(
                joint_name=name, position=value, tolerance_above=0.005,
                tolerance_below=0.005, weight=1.0))
        req.goal_constraints = [c]
        goal.request = req
        goal.planning_options = PlanningOptions(plan_only=False)
        self._run_move(goal, label)
        err = max(abs(a - b) for a, b in zip(self.joints(ARM_JOINTS), target))
        self.log(f'{label}: max joint error after execution {err:.4f} rad')
        return err

    def _run_move(self, goal, label):
        handle = self.wait(self.move_ac.send_goal_async(goal))
        if not handle.accepted:
            raise RuntimeError(f'{label}: goal rejected')
        result = self.wait(handle.get_result_async(), 120.0).result
        code = result.error_code.val
        if code != 1:
            raise RuntimeError(f'{label}: MoveIt error code {code}')
        self.log(f'{label}: planned+executed (MoveIt code 1)')

    def ik(self, xyz, label):
        req = GetPositionIK.Request()
        req.ik_request.group_name = ARM_GROUP
        req.ik_request.ik_link_name = EE_LINK
        req.ik_request.avoid_collisions = True
        req.ik_request.timeout = Duration(sec=1)
        ps = PoseStamped()
        ps.header.frame_id = FRAME
        ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = xyz
        ps.pose.orientation = DOWN
        req.ik_request.pose_stamped = ps
        res = self.wait(self.ik_cli.call_async(req))
        if res.error_code.val != 1:
            raise RuntimeError(f'IK failed for {label} at {xyz} '
                               f'(code {res.error_code.val})')
        js = dict(zip(res.solution.joint_state.name,
                      res.solution.joint_state.position))
        return [js[n] for n in ARM_JOINTS]

    def move_pose(self, xyz, label):
        """Pose goal for the flange (position + downward orientation)."""
        goal = MoveGroup.Goal()
        req = MotionPlanRequest()
        req.group_name = ARM_GROUP
        req.num_planning_attempts = 5
        req.allowed_planning_time = 10.0
        req.max_velocity_scaling_factor = self.args.speed
        req.max_acceleration_scaling_factor = self.args.speed
        pc = PositionConstraint()
        pc.header.frame_id = FRAME
        pc.link_name = EE_LINK
        region = SolidPrimitive(type=SolidPrimitive.SPHERE,
                                dimensions=[0.003])
        center = Pose()
        center.position.x, center.position.y, center.position.z = xyz
        center.orientation.w = 1.0
        pc.constraint_region.primitives = [region]
        pc.constraint_region.primitive_poses = [center]
        pc.weight = 1.0
        oc = OrientationConstraint()
        oc.header.frame_id = FRAME
        oc.link_name = EE_LINK
        oc.orientation = DOWN
        oc.absolute_x_axis_tolerance = 0.02
        oc.absolute_y_axis_tolerance = 0.02
        # Yaw must match the Cartesian segments (which use DOWN exactly) and
        # keep the fingers square to the axis-aligned cube faces.
        oc.absolute_z_axis_tolerance = 0.05
        oc.weight = 1.0
        req.goal_constraints = [Constraints(position_constraints=[pc],
                                            orientation_constraints=[oc])]
        goal.request = req
        goal.planning_options = PlanningOptions(plan_only=False)
        self._run_move(goal, label)

    def cartesian(self, xyz, label, collisions=True):
        """Straight-line flange motion (approach / lift / retreat)."""
        req = GetCartesianPath.Request()
        req.header.frame_id = FRAME
        req.group_name = ARM_GROUP
        req.link_name = EE_LINK
        req.max_step = 0.005
        req.avoid_collisions = collisions
        req.max_velocity_scaling_factor = self.args.speed
        req.max_acceleration_scaling_factor = self.args.speed
        target = Pose()
        target.position.x, target.position.y, target.position.z = xyz
        target.orientation = DOWN
        req.waypoints = [target]
        res = self.wait(self.cart_cli.call_async(req))
        if res.fraction < 0.99:
            raise RuntimeError(f'{label}: cartesian fraction '
                               f'{res.fraction:.2f}')
        goal = ExecuteTrajectory.Goal(trajectory=res.solution)
        handle = self.wait(self.exec_ac.send_goal_async(goal))
        result = self.wait(handle.get_result_async(), 120.0).result
        if result.error_code.val != 1:
            raise RuntimeError(f'{label}: execute code '
                               f'{result.error_code.val}')
        self.log(f'{label}: cartesian {res.fraction:.2f} executed')

    def gripper(self, q, label):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = FINGER_JOINTS
        goal.trajectory.points = [JointTrajectoryPoint(
            positions=[q, -q], time_from_start=Duration(sec=2))]
        handle = self.wait(self.grip_ac.send_goal_async(goal))
        result = self.wait(handle.get_result_async(), 30.0).result
        time.sleep(0.5)
        actual = self.joints(FINGER_JOINTS)
        # Closing on the cube is expected to stop short of the command, which
        # the controller may report as a goal-tolerance error.
        self.log(f'{label}: command q={q:.3f}, actual '
                 f'[{actual[0]:.4f}, {actual[1]:.4f}], '
                 f'controller error_code={result.error_code}')
        return actual

    def attach_cube(self, attach):
        aco = AttachedCollisionObject(link_name=EE_LINK)
        aco.object.id = self.args.object_id
        aco.object.header.frame_id = FRAME
        aco.touch_links = FINGER_LINKS
        # Attaching by id moves the existing world object onto the robot;
        # detaching returns it to the world at its current (placed) pose.
        aco.object.operation = (CollisionObject.ADD if attach
                                else CollisionObject.REMOVE)
        scene = PlanningScene()
        scene.robot_state = RobotState(attached_collision_objects=[aco],
                                       is_diff=True)
        self.apply_scene(scene)
        self.log(('Attached' if attach else 'Detached')
                 + f' {self.args.object_id} in the MoveIt planning scene')

    # ------------------------------------------------------------- stages
    def recover(self):
        """After a failure: open the gripper, detach the object, go to ready.

        If the arm was holding the object it is let go where it is (the
        failures so far happened just above the table). Best effort: every
        step may fail on its own."""
        for step in (lambda: self.gripper(OPEN_Q, 'recover: gripper open'),
                     lambda: self.attach_cube(False),
                     self.remove_object,  # else the open fingers start in collision with it
                     lambda: self.move_joints(READY, 'recover: back to ready')):
            try:
                step()
            except Exception as exc:  # noqa: BLE001  (best effort)
                self.log(f'recover step failed: {exc}')

    def remove_object(self):
        gone = CollisionObject()
        gone.id = self.args.object_id
        gone.operation = CollisionObject.REMOVE
        scene = PlanningScene(is_diff=True)
        scene.world.collision_objects = [gone]
        self.apply_scene(scene)

    def run(self):
        self.wait_ready()
        a = self.args
        self.add_scene()
        if a.stage == 'scene':
            return
        # Elbow-up pose above the table corner, flange pointing down
        # (flange at about (0.37, 0.39, 1.14) in the world frame).
        ready = READY
        self.move_joints(ready, 'joint goal: ready pose')
        if a.stage == 'joints':
            self.move_joints([0.7, 0.2, 1.3, 0.0, 1.5708, 0.5],
                             'joint goal: second pose')
            self.move_joints(ready, 'joint goal: back to ready')
            return
        grasp_above = GRASP_TOOL_Z_ABOVE_CUBE_BOTTOM
        if a.object_shape == 'cylinder':
            # The fingers reach 8.5 cm below the gripper body (which ends
            # 0.125 m below the flange): keep the body 5 mm above the top.
            grasp_above = max(grasp_above, a.object_height + GRIPPER_BODY_BOTTOM + 0.005)
        grasp_z = TABLE_TOP_Z + grasp_above
        pre = (a.cube_x, a.cube_y, grasp_z + APPROACH_HEIGHT)
        self.gripper(OPEN_Q, 'gripper open')
        self.ik(pre, 'pre-grasp')
        self.move_pose(pre, 'pose goal: pre-grasp above cube')
        if a.stage == 'ee':
            self.gripper(self.grasp_q, 'gripper close (no object)')
            self.gripper(OPEN_Q, 'gripper open')
            return
        self.cartesian((a.cube_x, a.cube_y, grasp_z), 'approach down')
        self.gripper(self.grasp_q, 'grasp')
        self.attach_cube(True)
        self.cartesian(pre, 'lift', collisions=True)
        place_pre = (a.place_x, a.place_y, grasp_z + APPROACH_HEIGHT)
        self.ik(place_pre, 'pre-place')
        self.move_pose(place_pre, 'pose goal: above place position')
        self.cartesian((a.place_x, a.place_y, grasp_z + 0.005),
                       'lower to place')
        self.gripper(OPEN_Q, 'release')
        self.attach_cube(False)
        self.cartesian(place_pre, 'retreat', collisions=False)
        self.move_joints(ready, 'joint goal: back to ready')


READY = [1.1, 0.0, 1.5708, 0.0, 1.5708, 0.0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', default='pick',
                        choices=['scene', 'joints', 'ee', 'pick'])
    parser.add_argument('--cube-x', type=float, default=0.40)
    parser.add_argument('--cube-y', type=float, default=0.50)
    parser.add_argument('--place-x', type=float, default=0.30)
    parser.add_argument('--place-y', type=float, default=0.65)
    parser.add_argument('--speed', type=float, default=0.2,
                        help='velocity/acceleration scaling (0-1)')
    parser.add_argument('--object-id', default='pick_cube')
    parser.add_argument('--object-shape', choices=['box', 'cylinder'], default='box')
    parser.add_argument('--object-radius', type=float, default=0.045)
    parser.add_argument('--object-height', type=float, default=0.105)
    parser.add_argument('--grasp-q', type=float, default=None,
                        help='finger joint target for the grasp (default: from size)')
    parser.add_argument('--obstacle', action='append',
                        help='extra cylinder obstacle: name,x,y,radius,height')
    args, _ = parser.parse_known_args()
    rclpy.init()
    node = PickPlace(args)
    try:
        node.run()
        node.log(f'Stage "{args.stage}" finished')
        code = 0
    except RuntimeError as exc:
        node.get_logger().error(str(exc))
        code = 1
        if args.stage == 'pick':
            node.recover()
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Send one gripper goal and report finger motion: gripper_monitor.py Q SECONDS (left=Q, right=-Q)."""
import sys, time, rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from sensor_msgs.msg import JointState
q = float(sys.argv[1]); T = int(sys.argv[2])
rclpy.init(); n = Node('gripmon'); st = {}
n.create_subscription(JointState, '/joint_states', lambda m: st.update(zip(m.name, m.position)), 10)
ac = ActionClient(n, FollowJointTrajectory, '/parallel_gripper_controller/follow_joint_trajectory'); ac.wait_for_server()
g = FollowJointTrajectory.Goal(); g.trajectory.joint_names = ['left_finger_joint', 'right_finger_joint']
g.trajectory.points = [JointTrajectoryPoint(positions=[q, -q], time_from_start=Duration(sec=T))]
f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f); h = f.result(); print('accepted', h.accepted)
r = h.get_result_async(); t0 = time.time(); L=[]; R=[]
while not r.done() and time.time() - t0 < T + 5:
    rclpy.spin_once(n, timeout_sec=0.25)
    L.append(st.get('left_finger_joint',0)); R.append(st.get('right_finger_joint',0))
print(f'L {L[0]:+.4f}->{L[-1]:+.4f} (min {min(L):+.4f} max {max(L):+.4f}) R {R[0]:+.4f}->{R[-1]:+.4f} (min {min(R):+.4f} max {max(R):+.4f})'); print('result', r.result().result.error_code if r.done() else 'pending', r.result().result.error_string if r.done() else '')

#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from std_msgs.msg import Float64MultiArray

from dsr_msgs2.srv import GetCurrentPosx, GetToolForce, GetJointTorque


class DSRMonitorNode(Node):
    def __init__(self):
        super().__init__('dsr_monitor_node')

        self.pose_pub = self.create_publisher(Float64MultiArray, '/monitor/tcp_pose', 10)
        self.force_pub = self.create_publisher(Float64MultiArray, '/monitor/tool_force', 10)
        self.torque_pub = self.create_publisher(Float64MultiArray, '/monitor/joint_torque', 10)

        self.posx_cli = self.create_client(GetCurrentPosx, '/dsr01/aux_control/get_current_posx')
        self.force_cli = self.create_client(GetToolForce, '/dsr01/aux_control/get_tool_force')
        self.jtorque_cli = self.create_client(GetJointTorque, '/dsr01/aux_control/get_joint_torque')

        while not self.posx_cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for get_current_posx service...')
        while not self.force_cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for get_tool_force service...')
        while not self.jtorque_cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for get_joint_torque service...')

        self.timer = self.create_timer(0.2, self.timer_callback)  # 5 Hz
        self.busy = False
    def timer_callback(self):
        if self.busy:
            return
        self.busy = True
        self.pending = 3

        self.call_posx()
        self.call_force()
        self.call_joint_torque()

    def check_done(self):
        self.pending -= 1
        if self.pending == 0:
            self.busy = False

    def call_posx(self):
        req = GetCurrentPosx.Request()
        req.ref = 0
        future = self.posx_cli.call_async(req)
        future.add_done_callback(self.posx_done)

    def call_force(self):
        req = GetToolForce.Request()
        req.ref = 0
        future = self.force_cli.call_async(req)
        future.add_done_callback(self.force_done)

    def call_joint_torque(self):
        req = GetJointTorque.Request()
        future = self.jtorque_cli.call_async(req)
        future.add_done_callback(self.joint_torque_done)

    def posx_done(self, future):
        try:
            res = future.result()
            if res.success and len(res.task_pos_info) > 0:
                msg = Float64MultiArray()
                msg.data = list(res.task_pos_info[0].data)
                self.pose_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f'posx service failed: {e}')
        self.check_done()

    def force_done(self, future):
        try:
            res = future.result()
            if res.success:
                msg = Float64MultiArray()
                msg.data = list(res.tool_force)
                self.force_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f'force service failed: {e}')
        self.check_done()

    def joint_torque_done(self, future):
        try:
            res = future.result()
            if res.success:
                msg = Float64MultiArray()
                msg.data = list(res.jts)
                self.torque_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f'joint torque service failed: {e}')
        self.check_done()

    def check_done(self):
        # 단순하게 3개 콜백이 끝날 때마다 busy 풀기엔 카운트가 필요하므로
        # 여기서는 다음 타이머에서 약간 중복 방지용으로만 사용
        self.busy = False


def STT_force_torque(args=None):
    rclpy.init(args=args)
    node = DSRMonitorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

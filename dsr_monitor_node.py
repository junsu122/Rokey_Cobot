#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Vector3Stamped, WrenchStamped
from sensor_msgs.msg import JointState

from dsr_msgs2.srv import GetCurrentPosx, GetToolForce, GetJointTorque


class DSRRqtMonitor(Node):
    def __init__(self):
        super().__init__('dsr_rqt_monitor')

        self.pub_tcp_pos = self.create_publisher(Vector3Stamped, '/monitor/tcp_position', 10)
        self.pub_tcp_rpy = self.create_publisher(Vector3Stamped, '/monitor/tcp_rpy', 10)
        self.pub_wrench = self.create_publisher(WrenchStamped, '/monitor/tool_wrench', 10)
        self.pub_joint_torque = self.create_publisher(JointState, '/monitor/joint_torque', 10)

        self.cli_posx = self.create_client(GetCurrentPosx, '/dsr01/aux_control/get_current_posx')
        self.cli_force = self.create_client(GetToolForce, '/dsr01/aux_control/get_tool_force')
        self.cli_jtorque = self.create_client(GetJointTorque, '/dsr01/aux_control/get_joint_torque')

        for client, name in [
            (self.cli_posx, 'get_current_posx'),
            (self.cli_force, 'get_tool_force'),
            (self.cli_jtorque, 'get_joint_torque'),
        ]:
            while not client.wait_for_service(timeout_sec=1.0):
                self.get_logger().info(f'Waiting for {name} service...')

        self.pending = 0
        self.timer = self.create_timer(0.2, self.timer_callback)  # 5 Hz

        self.joint_names = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']

    def timer_callback(self):
        if self.pending > 0:
            return

        self.pending = 3

        req1 = GetCurrentPosx.Request()
        req1.ref = 0
        future1 = self.cli_posx.call_async(req1)
        future1.add_done_callback(self.cb_posx)

        req2 = GetToolForce.Request()
        req2.ref = 0
        future2 = self.cli_force.call_async(req2)
        future2.add_done_callback(self.cb_force)

        req3 = GetJointTorque.Request()
        future3 = self.cli_jtorque.call_async(req3)
        future3.add_done_callback(self.cb_joint_torque)

    def cb_posx(self, future):
        try:
            res = future.result()
            if res.success and len(res.task_pos_info) > 0:
                data = list(res.task_pos_info[0].data)
                # [x, y, z, rx, ry, rz, sol]
                if len(data) >= 6:
                    now = self.get_clock().now().to_msg()

                    pos_msg = Vector3Stamped()
                    pos_msg.header.stamp = now
                    pos_msg.header.frame_id = 'base'
                    pos_msg.vector.x = float(data[0])
                    pos_msg.vector.y = float(data[1])
                    pos_msg.vector.z = float(data[2])
                    self.pub_tcp_pos.publish(pos_msg)

                    rpy_msg = Vector3Stamped()
                    rpy_msg.header.stamp = now
                    rpy_msg.header.frame_id = 'base'
                    rpy_msg.vector.x = float(data[3])
                    rpy_msg.vector.y = float(data[4])
                    rpy_msg.vector.z = float(data[5])
                    self.pub_tcp_rpy.publish(rpy_msg)
        except Exception as e:
            self.get_logger().error(f'GetCurrentPosx failed: {e}')
        self.pending -= 1

    def cb_force(self, future):
        try:
            res = future.result()
            if res.success and len(res.tool_force) >= 6:
                now = self.get_clock().now().to_msg()

                msg = WrenchStamped()
                msg.header.stamp = now
                msg.header.frame_id = 'tool'
                msg.wrench.force.x = float(res.tool_force[0])
                msg.wrench.force.y = float(res.tool_force[1])
                msg.wrench.force.z = float(res.tool_force[2])
                msg.wrench.torque.x = float(res.tool_force[3])
                msg.wrench.torque.y = float(res.tool_force[4])
                msg.wrench.torque.z = float(res.tool_force[5])
                self.pub_wrench.publish(msg)
        except Exception as e:
            self.get_logger().error(f'GetToolForce failed: {e}')
        self.pending -= 1

    def cb_joint_torque(self, future):
        try:
            res = future.result()
            if res.success:
                now = self.get_clock().now().to_msg()

                msg = JointState()
                msg.header.stamp = now
                msg.name = self.joint_names
                msg.effort = [float(x) for x in res.jts]
                self.pub_joint_torque.publish(msg)
        except Exception as e:
            self.get_logger().error(f'GetJointTorque failed: {e}')
        self.pending -= 1


def main(args=None):
    rclpy.init(args=args)
    node = DSRRqtMonitor()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()









# #!/usr/bin/env python3
# import rclpy
# from rclpy.node import Node

# from std_msgs.msg import Float64MultiArray

# from dsr_msgs2.srv import GetCurrentPosx, GetToolForce, GetJointTorque


# class DSRMonitorNode(Node):
#     def __init__(self):
#         super().__init__('dsr_monitor_node')

#         self.pose_pub = self.create_publisher(Float64MultiArray, '/monitor/tcp_pose', 10)
#         self.force_pub = self.create_publisher(Float64MultiArray, '/monitor/tool_force', 10)
#         self.torque_pub = self.create_publisher(Float64MultiArray, '/monitor/joint_torque', 10)

#         self.posx_cli = self.create_client(GetCurrentPosx, '/dsr01/aux_control/get_current_posx')
#         self.force_cli = self.create_client(GetToolForce, '/dsr01/aux_control/get_tool_force')
#         self.jtorque_cli = self.create_client(GetJointTorque, '/dsr01/aux_control/get_joint_torque')

#         while not self.posx_cli.wait_for_service(timeout_sec=1.0):
#             self.get_logger().info('Waiting for get_current_posx service...')
#         while not self.force_cli.wait_for_service(timeout_sec=1.0):
#             self.get_logger().info('Waiting for get_tool_force service...')
#         while not self.jtorque_cli.wait_for_service(timeout_sec=1.0):
#             self.get_logger().info('Waiting for get_joint_torque service...')

#         self.timer = self.create_timer(0.2, self.timer_callback)  # 5 Hz
#         self.busy = False

#     def timer_callback(self):
#         if self.busy:
#             return
#         self.busy = True

#         self.call_posx()
#         self.call_force()
#         self.call_joint_torque()

#     def call_posx(self):
#         req = GetCurrentPosx.Request()
#         req.ref = 0
#         future = self.posx_cli.call_async(req)
#         future.add_done_callback(self.posx_done)

#     def call_force(self):
#         req = GetToolForce.Request()
#         req.ref = 0
#         future = self.force_cli.call_async(req)
#         future.add_done_callback(self.force_done)

#     def call_joint_torque(self):
#         req = GetJointTorque.Request()
#         future = self.jtorque_cli.call_async(req)
#         future.add_done_callback(self.joint_torque_done)

#     def posx_done(self, future):
#         try:
#             res = future.result()
#             if res.success and len(res.task_pos_info) > 0:
#                 msg = Float64MultiArray()
#                 msg.data = list(res.task_pos_info[0].data)
#                 self.pose_pub.publish(msg)
#         except Exception as e:
#             self.get_logger().error(f'posx service failed: {e}')
#         self.check_done()

#     def force_done(self, future):
#         try:
#             res = future.result()
#             if res.success:
#                 msg = Float64MultiArray()
#                 msg.data = list(res.tool_force)
#                 self.force_pub.publish(msg)
#         except Exception as e:
#             self.get_logger().error(f'force service failed: {e}')
#         self.check_done()

#     def joint_torque_done(self, future):
#         try:
#             res = future.result()
#             if res.success:
#                 msg = Float64MultiArray()
#                 msg.data = list(res.jts)
#                 self.torque_pub.publish(msg)
#         except Exception as e:
#             self.get_logger().error(f'joint torque service failed: {e}')
#         self.check_done()

#     def check_done(self):
#         # 단순하게 3개 콜백이 끝날 때마다 busy 풀기엔 카운트가 필요하므로
#         # 여기서는 다음 타이머에서 약간 중복 방지용으로만 사용
#         self.busy = False


# def main(args=None):
#     rclpy.init(args=args)
#     node = DSRMonitorNode()
#     rclpy.spin(node)
#     node.destroy_node()
#     rclpy.shutdown()


# if __name__ == '__main__':
#     main()

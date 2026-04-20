import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray

ROBOT_ID = "dsr01"

POS_COORDS = {
    0: [408.0, -100.0, 82.5, 0.0, 180.0, 0.0],
    1: [432.2, -100.0, 107.5, 0.0, 180.0, 0.0],
    2: [408.0, -100.0, 107.5, 0.0, 180.0, 0.0],
    3: [383.8, -100.0, 107.5, 0.0, 180.0, 0.0],
    4: [456.4, -100.0, 132.5, 0.0, 180.0, 0.0],
    5: [432.2, -100.0, 132.5, 0.0, 180.0, 0.0],
    6: [408.0, -100.0, 132.5, 0.0, 180.0, 0.0],
    7: [383.8, -100.0, 132.5, 0.0, 180.0, 0.0],
    8: [359.6, -100.0, 132.5, 0.0, 180.0, 0.0],
    9: [480.7, -100.0, 157.5, 0.0, 180.0, 0.0],
    10: [456.4, -100.0, 157.5, 0.0, 180.0, 0.0],
    11: [432.2, -100.0, 157.5, 0.0, 180.0, 0.0],
    12: [408.0, -100.0, 157.5, 0.0, 180.0, 0.0],
    13: [383.8, -100.0, 157.5, 0.0, 180.0, 0.0],
    14: [359.6, -100.0, 157.5, 0.0, 180.0, 0.0],
    15: [335.3, -100.0, 157.5, 0.0, 180.0, 0.0],
    16: [480.7, -100.0, 182.5, 0.0, 180.0, 0.0],
    17: [456.4, -100.0, 182.5, 0.0, 180.0, 0.0],
    18: [432.2, -100.0, 182.5, 0.0, 180.0, 0.0],
    19: [383.8, -100.0, 182.5, 0.0, 180.0, 0.0],
    20: [359.6, -100.0, 182.5, 0.0, 180.0, 0.0],
    21: [335.3, -100.0, 182.5, 0.0, 180.0, 0.0],
    22: [456.4, -100.0, 207.5, 0.0, 180.0, 0.0],
    23: [359.6, -100.0, 207.5, 0.0, 180.0, 0.0],
}

coords_list = []
for i in range(len(POS_COORDS)):
    for j in range(6):
        coords_list.append(POS_COORDS[i][j])


class ParameterPublisher(Node):
    def __init__(self):
        super().__init__("parameter_publisher", namespace=ROBOT_ID)
        self.pub = self.create_publisher(Float64MultiArray, 'new_parameter', 10)
        self.get_logger().info("Publisher ready. Sending once...")
        self.publish_once()

    def publish_once(self):
        msg = Float64MultiArray()
        msg.data = coords_list
        self.pub.publish(msg)
        self.get_logger().info(f"Sent: {msg.data}")

def main(args=None):
    rclpy.init(args=args)
    node = ParameterPublisher()
    rclpy.spin_once(node, timeout_sec=3.0)
    rclpy.shutdown()

if __name__ == "__main__":
    main()
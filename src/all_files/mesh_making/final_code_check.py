import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class TopicTestSubscriber(Node):
    def __init__(self):
        super().__init__('topic_test_subscriber')
        # GUI에서 설정한 토픽명 'make_shape_parameter'와 동일하게 설정
        self.subscription = self.create_subscription(
            String,
            'make_shape_parameter',
            self.listener_callback,
            10
        )
        self.get_logger().info('--- Subscriber 노드가 시작되었습니다. 버튼을 눌러보세요 ---')

    def listener_callback(self, msg):
        # 토픽이 들어오면 실행되는 함수
        self.get_logger().info(f'받은 데이터: "{msg.data}"')

def main(args=None):
    rclpy.init(args=args)
    node = TopicTestSubscriber()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
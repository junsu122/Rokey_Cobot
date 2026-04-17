import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray

class ParamPublisher(Node):
    def __init__(self):
        super().__init__('param_publisher')
        self.publisher_ = self.create_publisher(Float64MultiArray, 'new_parameter', 10)
        
    def send_params(self):
        msg = Float64MultiArray()
        # 데이터 구조 정의: 앞의 6개는 JReady, 뒤의 6개는 pos1
        # 예시: JReady[0,0,90,0,90,0] + pos1[500,80,200,150,179,150]
        new_data = [0.0, 90.0, 90.0, 0.0, 90.0, 0.0, 300.0, 80.0, 100.0, 150.0, 179.0, 150.0]
        msg.data = new_data
        
        self.publisher_.publish(msg)
        self.get_logger().info(f'Publishing: {msg.data}')

def main(args=None):
    rclpy.init(args=args)
    publisher = ParamPublisher()
    
    print("새로운 파라미터를 전송하려면 Enter를 누르세요. (종료: Ctrl+C)")
    try:
        while rclpy.ok():
            input() # 대기
            publisher.send_params()
    except KeyboardInterrupt:
        pass
    
    publisher.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
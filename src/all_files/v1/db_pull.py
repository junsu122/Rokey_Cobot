import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
import firebase_admin
from firebase_admin import credentials, db
import time
from datetime import datetime

class FirebaseToRosPublisher(Node):
    def __init__(self):
        super().__init__('firebase_to_ros_publisher')
        
        # 1. ROS 2 Publisher 설정
        self.publisher_ = self.create_publisher(Float64MultiArray, 'dsr01/new_parameter', 10)
        
        # 2. Firebase 초기화
        cred_path = "/home/junsu/Downloads/rokey-cobot-firebase-adminsdk-fbsvc-f2b3ddb804.json"
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://rokey-cobot-default-rtdb.asia-southeast1.firebasedatabase.app'
        })
        
        self.get_logger().info("🛰️ Firebase 감시 시작... 데이터 수신 시 로그를 출력합니다.")
        db.reference('robot/commands').listen(self.handle_new_data)

    def handle_new_data(self, event):
        data = event.data
        if not data or 'coords' not in data:
            return

        coords = data.get('coords', {})
        ts = data.get('updated_at', 0) / 1000.0
        time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        
        print(f"\n{'='*60}")
        print(f"🔔 [수신 시간: {time_str}] 새로운 좌표 데이터가 도착했습니다!")
        print(f"{'='*60}")

        flat_coords_list = []

        # --- [로그 1] 각 포인트별 원래 좌표 출력 ---
        print("\n📍 [1. 포인트별 원본 데이터]")
        if isinstance(coords, list):
            for i, val in enumerate(coords):
                if val is not None:
                    print(f"   Point {i}: {val}")
                    flat_coords_list.extend(val)
        else:
            sorted_keys = sorted(coords.keys(), key=int)
            for key in sorted_keys:
                val = coords[key]
                print(f"   Point {key}: {val}")
                flat_coords_list.extend(val)

        # --- [로그 2] 한 줄로 합쳐진 리스트 출력 ---
        # 가독성을 위해 소수점 첫째자리까지만 보이게 처리
        formatted_flat = [round(float(x), 1) for x in flat_coords_list]
        
        print("\n📏 [2. 한 줄로 변환된 전체 리스트 (Flattened)]")
        print(f"   {formatted_flat}")
        print(f"\n   ✅ 총 데이터 개수: {len(formatted_flat)} 개 (좌표 {len(formatted_flat)//6}개 분량)")
        print(f"{'='*60}\n")

        # 3. ROS 2 토픽 발행
        msg = Float64MultiArray()
        msg.data = [float(x) for x in flat_coords_list]
        self.publisher_.publish(msg)
        self.get_logger().info(f"Topic '/shape_parameter'로 데이터 전송 완료!")

def main(args=None):
    rclpy.init(args=args)
    node = FirebaseToRosPublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("프로그램을 종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
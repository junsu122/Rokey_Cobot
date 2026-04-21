import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
import firebase_admin
from firebase_admin import credentials, firestore
import threading
import time

ROBOT_ID = "dsr01"

# Firebase 초기화
cred = credentials.Certificate("/home/kng/Documents/project/serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()


class ParameterPublisher(Node):
    def __init__(self):
        super().__init__("parameter_publisher", namespace=ROBOT_ID)
        self.pub = self.create_publisher(Float64MultiArray, 'new_parameter', 10)
        self.get_logger().info("Firestore 감시 시작... ACCEPT 대기 중")

        # Firestore 실시간 감시 (별도 스레드)
        thread = threading.Thread(target=self._listen, daemon=True)
        thread.start()

    def _listen(self):
        def on_snapshot(col_snapshot, changes, read_time):
            for change in changes:
                # 문서가 추가되거나 수정됐을 때
                if change.type.name in ("ADDED", "MODIFIED"):
                    data = change.document.to_dict()

                    # status가 done이고 아직 퍼블리시 안 한 것만 처리
                    if data.get("status") != "done":
                        continue

                    coords_map = data.get("coords", {})
                    if not coords_map:
                        continue

                    # 좌표 파싱: 키 순서대로 정렬
                    all_pos = [
                        [float(v["x"]), float(v["y"]), float(v["z"]),
                         float(v["rx"]), float(v["ry"]), float(v["rz"])]
                        for _, v in sorted(coords_map.items(), key=lambda item: int(item[0]))
                    ]

                    self.get_logger().info(
                        f"수신: {change.document.id} / 좌표 수: {len(all_pos)}"
                    )

                    # 퍼블리시
                    self._publish(all_pos)

                    # 처리 완료 표시 (중복 퍼블리시 방지)
                    change.document.reference.update({"status": "published"})

        # pixel_coords 컬렉션 전체 감시
        db.collection("pixel_coords").on_snapshot(on_snapshot)

        # 스레드 유지
        while rclpy.ok():
            time.sleep(1)

    def _publish(self, all_pos: list):
        msg = Float64MultiArray()
        flat = [float(v) for coord in all_pos for v in coord]
        msg.data = flat

        time.sleep(2.0)
        self.pub.publish(msg)

        self.get_logger().info(f"퍼블리시 완료: {len(all_pos)}개 좌표")
        print(msg.data)  # array('d', [...]) 형태로 자동 출력


def main(args=None):
    rclpy.init(args=args)
    node = ParameterPublisher()

    try:
        rclpy.spin(node)  # 계속 실행 (ACCEPT 대기)
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
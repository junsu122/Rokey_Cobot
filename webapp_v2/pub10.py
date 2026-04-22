import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
import firebase_admin
from firebase_admin import credentials, firestore
import threading
import time

ROBOT_ID = "dsr01"

cred = credentials.Certificate("/home/kng/Rokey_Cobot/webapp_v2/serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# 취소 신호 (0000): sub에서 이 값을 받으면 동작 중단
CANCEL_SIGNAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class ParameterPublisher(Node):
    def __init__(self):
        super().__init__("parameter_publisher", namespace=ROBOT_ID)
        self.pub = self.create_publisher(Float64MultiArray, 'new_parameter', 10)
        self.get_logger().info("Firestore 감시 시작... ACCEPT / 주문취소 대기 중")

        thread = threading.Thread(target=self._listen, daemon=True)
        thread.start()

    def _listen(self):
        last_cancel_ts = 0  # 중복 취소 방지용

        def on_snapshot(col_snapshot, changes, read_time):
            nonlocal last_cancel_ts

            for change in changes:
                if change.type.name not in ("ADDED", "MODIFIED"):
                    continue

                doc_id = change.document.id
                data   = change.document.to_dict()
                status = data.get("status", "")

                # ── 주문 취소 신호 ──────────────────────
                if doc_id == "cancel_signal" and status == "cancel":
                    ts = data.get("timestamp", 0)
                    if ts == last_cancel_ts:
                        continue  # 중복 처리 방지
                    last_cancel_ts = ts

                    self.get_logger().warn("🚫 주문 취소 신호 수신 → [0,0,0,0,0,0] 퍼블리시")
                    self._publish(CANCEL_SIGNAL, is_cancel=True)

                    # 처리 완료 표시
                    change.document.reference.update({"status": "cancel_done"})
                    continue

                # ── 좌표 수신 (done) ────────────────────
                if status != "done":
                    continue

                coords_map = data.get("coords", {})
                if not coords_map:
                    continue

                all_pos = [
                    [float(v["x"]), float(v["y"]), float(v["z"]),
                     float(v["rx"]), float(v["ry"]), float(v["rz"])]
                    for _, v in sorted(coords_map.items(), key=lambda item: int(item[0]))
                ]

                self.get_logger().info(f"✅ 좌표 수신: {doc_id} / {len(all_pos)}개")
                flat = [float(v) for coord in all_pos for v in coord]
                self._publish(flat)

                change.document.reference.update({"status": "published"})

        db.collection("pixel_coords").on_snapshot(on_snapshot)

        while rclpy.ok():
            time.sleep(1)

    def _publish(self, data: list, is_cancel: bool = False):
        msg = Float64MultiArray()
        msg.data = data

        time.sleep(0.5 if is_cancel else 2.0)
        self.pub.publish(msg)

        if is_cancel:
            self.get_logger().warn(f"퍼블리시 (취소): {msg.data}")
        else:
            self.get_logger().info(f"퍼블리시 완료: {len(data) // 6}개 좌표")
        print(msg.data)


def main(args=None):
    rclpy.init(args=args)
    node = ParameterPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
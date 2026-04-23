import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
import firebase_admin
from firebase_admin import credentials, firestore
import threading
import time

# =========================
# CONFIGURATION
# =========================
ROBOT_ID = "dsr01"
SERVICE_ACCOUNT_PATH = "/home/ludix/test_23/serviceAccountKey.json"


CANCEL_SIGNAL = [0.0] * 6
PAUSE_SIGNAL  = [1.0] * 6
RESUME_SIGNAL = [2.0] * 6

# 파이어베이스 초기화
cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
if not firebase_admin._apps: # 중복 초기화 방지
    firebase_admin.initialize_app(cred)
db = firestore.client()


class ParameterPublisher(Node):
    def __init__(self):
        super().__init__("parameter_publisher", namespace=ROBOT_ID)
        self.pub = self.create_publisher(Float64MultiArray, 'new_parameter', 10)

        self.get_logger().info("🔥 Firestore 실시간 감시 시작")

        # 중복 실행 방지용 기록
        self.last_ts = {"cancel": 0, "pause": 0, "resume": 0}

        # 백그라운드 스레드 시작
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def on_snapshot(self, col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name not in ("ADDED", "MODIFIED"):
                continue

            doc_id = change.document.id
            data   = change.document.to_dict()
            status = data.get("status", "")
            ts     = data.get("timestamp", 0)

            # 1. 취소 신호
            if doc_id == "cancel_signal" and status == "cancel":
                if ts != self.last_ts["cancel"]:
                    self.last_ts["cancel"] = ts
                    self.get_logger().warn("🚨 [CANCEL] 전송")
                    self._publish(CANCEL_SIGNAL, "취소")
                    change.document.reference.update({"status": "cancel_done"})

            # 2. 일시정지 신호
            elif doc_id == "control_signal" and status == "pause":
                if ts != self.last_ts["pause"]:
                    self.last_ts["pause"] = ts
                    self.get_logger().warn("⏸️ [PAUSE] 전송")
                    self._publish(PAUSE_SIGNAL, "일시정지")
                    change.document.reference.update({"status": "pause_done"})

            # 3. 재개 신호
            elif doc_id == "control_signal" and status == "resume":
                if ts != self.last_ts["resume"]:
                    self.last_ts["resume"] = ts
                    self.get_logger().info("▶️ [RESUME] 전송")
                    self._publish(RESUME_SIGNAL, "재개")
                    change.document.reference.update({"status": "resume_done"})

            # 4. 좌표 데이터
            elif status == "done":
                coords_map = data.get("coords", {})
                if not coords_map: continue

                processed_coords = []
                # 키값을 숫자로 변환해서 정렬
                sorted_keys = sorted(coords_map.keys(), key=lambda x: int(x))
                
                for k in sorted_keys:
                    v = coords_map[k]
                    raw = [float(v["x"]), float(v["y"]), float(v["z"]),
                           float(v["rx"]), float(v["ry"]), float(v["rz"])]
                    
                    # if raw not in [CANCEL_SIGNAL, PAUSE_SIGNAL, RESUME_SIGNAL]:
                    #     raw[0] += 80.0
                    #     raw[1] += 98.0
                    #     raw[2] += 125.0
                    # processed_coords.append(raw)


                    #################오프셋주는곳##################
                    if raw not in [CANCEL_SIGNAL, PAUSE_SIGNAL, RESUME_SIGNAL]:
                        raw[0] += 0.0
                        raw[1] += 0.0
                        raw[2] += 0.0
                    processed_coords.append(raw)

                flat_data = [val for sublist in processed_coords for val in sublist]
                self.get_logger().info(f"✅ [DATA] {len(processed_coords)}개 전송")
                self._publish(flat_data, "좌표데이터")
                change.document.reference.update({"status": "published"})

    def _listen(self):
        # Firestore 감시 바인딩 (on_snapshot 메서드를 콜백으로 지정)
        db.collection("pixel_coords").on_snapshot(self.on_snapshot)
        
        while rclpy.ok():
            time.sleep(1)

    def _publish(self, data: list, label: str):
        msg = Float64MultiArray()
        msg.data = data
        wait_time = 0.5 if label != "좌표데이터" else 1.5 # 데이터 전송 대기 살짝 줄임
        time.sleep(wait_time)
        self.pub.publish(msg)
        self.get_logger().info(f"📡 전송완료 ({label})")


def main(args=None):
    rclpy.init(args=args)
    node = ParameterPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
import rclpy
import DR_init
import time
import threading
import json
from std_msgs.msg import Float64MultiArray, String
from dsr_msgs2.srv import SetRobotControl

# =========================
# ROBOT CONFIG
# =========================
ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL  = "Tool Weight"
ROBOT_TCP   = "GripperDA_v1"

#1.5배 버젼
HOME_V_J = 450; HOME_ACC_J = 300
CATCH_V_J = 450; CATCH_ACC_J = 300
VELOCITY_L = 400; ACC_L = 300
INSERT_V_L = 600; INSERT_A_L = 500
TARGET_V_L = 350; TARGET_A_L = 200

# DR INIT
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# ✅ DSR 로봇 하드웨어 상태 상수
STATE_ROBOT_STANDBY         = 1
STATE_ROBOT_MOVING          = 2
STATE_ROBOT_SAFE_OFF        = 3
STATE_ROBOT_PROTECTIVE_STOP = 5
STATE_ROBOT_EMERGENCY_STOP  = 6

# ✅ 서보 제어 명령 상수
CONTROL_RESET_SAFE_STOP = 2
CONTROL_RESET_SAFE_OFF  = 3

# =========================
# GLOBAL STATE & FSM
# =========================
STATE_IDLE      = "IDLE"
STATE_BASIC     = "BASIC"
STATE_PAUSED    = "PAUSED"
STATE_REPROCESS = "REPROCESS"

current_state          = STATE_IDLE
pause_signal           = False
cancel_signal_received = False
basic_process          = True
re_process             = False
new_param_received     = False
posx_dic               = {}
resume_from_index      = 0

# ✅ 전역 좌표 딕셔너리
target_pos_dic     = {}
target_up_pos_dic  = {}
target_up_pos_dic1 = {}
target_up_pos_dic2 = {}
target_up_pos_dic3 = {}

HOME_JReady               = [19.20, -6.90, 86.79, 0.07, 100.94, 13.81]
flower_initial_position_J = [40.25, 27.42, 63.42, 87.97, -40.38, 0.53]
WAYPOINT_J                = [24.1, 21.51, 77.77, 3.33, 81.80, 23.66]

# =========================
# ✅ SetRobotControl 서비스 호출
# =========================
def call_set_robot_control(control_value):
    node = DR_init.__dsr__node
    srv_name = f'/{ROBOT_ID}/system/set_robot_control'
    cli = node.create_client(SetRobotControl, srv_name)
    if not cli.wait_for_service(timeout_sec=1.0):
        node.get_logger().error(f"[Err] {srv_name} 서비스를 찾을 수 없습니다.")
        return False
    req = SetRobotControl.Request()
    req.robot_control = control_value
    future = cli.call_async(req)
    start_wait = time.time()
    while not future.done():
        rclpy.spin_once(node, timeout_sec=0.01)
        if time.time() - start_wait > 5.0:
            node.get_logger().error("[Err] 서비스 호출 시간 초과")
            return False
    try:
        return future.result().success
    except Exception as e:
        node.get_logger().error(f"[Err] 서비스 호출 실패: {e}")
        return False

# =========================
# CALLBACK
# =========================
def param_callback(msg):
    global new_param_received, posx_dic, cancel_signal_received, pause_signal
    node = DR_init.__dsr__node

    if len(msg.data) == 6 and all(v == 0.0 for v in msg.data):
        cancel_signal_received = True
        node.get_logger().warn("🚨 취소 신호 감지!")
        return

    if len(msg.data) == 6 and all(v == 1.0 for v in msg.data):
        pause_signal = True
        node.get_logger().warn("⏸️ 일시정지 신호 감지!")
        return

    if len(msg.data) == 6 and all(v == 2.0 for v in msg.data):
        if pause_signal:
            pause_signal = False
            node.get_logger().info("▶️ 재개 신호 감지! 작업을 다시 시작합니다. (Resume)")
        return

    if len(msg.data) % 6 != 0:
        node.get_logger().error("❌ 잘못된 좌표 형식입니다.")
        return

    posx_dic.clear()
    num_poses = len(msg.data) // 6
    for i in range(num_poses):
        posx_dic[i] = list(msg.data[i*6:(i+1)*6])

    new_param_received     = True
    cancel_signal_received = False
    pause_signal           = False
    node.get_logger().info(f"📥 {num_poses}개 좌표 수신")

# =========================
# INIT
# =========================
def initialize_robot():
    from DSR_ROBOT2 import (
        set_tool, set_tcp, set_robot_mode, set_ref_coord,
        ROBOT_MODE_AUTONOMOUS
    )
    node = DR_init.__dsr__node
    set_ref_coord(107)
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    node.get_logger().info("🤖 로봇 초기화 완료 (Ref Coord: 107)")
    time.sleep(1)

# =========================
# TASK EXECUTION
# =========================
def perform_task():
    from DSR_ROBOT2 import (
        posx, movej, movel, get_current_posx, set_ref_coord,
        set_digital_output, OFF, ON, wait, get_tool_force,
        get_robot_state, set_robot_mode, ROBOT_MODE_AUTONOMOUS,
        drl_script_stop, DR_QSTOP_STO
    )
    global new_param_received, cancel_signal_received, basic_process, re_process
    global pause_signal, current_state, resume_from_index
    global target_pos_dic, target_up_pos_dic, target_up_pos_dic1, target_up_pos_dic3

    node = DR_init.__dsr__node

    # ✅ 퍼블리셔 생성
    status_pub = node.create_publisher(String, f'/{ROBOT_ID}/robot_monitor_status', 10)

    # ✅ 마지막으로 확인된 HW 상태를 캐시
    # hw_monitor_thread 는 메인 스레드의 get_robot_state() 결과를 읽기만 함
    hw_cache = {"code": 1}

    # ✅ publish_status: hw_cache 를 사용 → 스레드에서 get_robot_state() 호출 안 함
    def publish_status(log_msg="", log_level="INFO", countdown=0):
        msg = String()
        msg.data = json.dumps({
            "fsm":        current_state,
            "hw_code":    hw_cache["code"],
            "cur_flower": resume_from_index + 1,
            "done":       resume_from_index,
            "total":      len(target_pos_dic),
            "resume_idx": resume_from_index,
            "countdown":  countdown,
            "log":        log_msg,
            "log_level":  log_level,
        })
        status_pub.publish(msg)

    def gripper_open():
        set_digital_output(1, OFF); set_digital_output(2, ON); wait(0.3)

    def gripper_close():
        set_digital_output(1, ON); set_digital_output(2, OFF); wait(0.3)

    def wait_for_pause():
        if pause_signal:
            node.get_logger().warn("⏸️ 일시정지 중... Play 신호를 기다립니다.")
            publish_status("일시정지 — Play 신호 대기", "WARN")
            while pause_signal:
                rclpy.spin_once(node, timeout_sec=0.1)
                wait(0.1)
            publish_status("일시정지 해제 — 재개", "OK")

    # ✅ 모니터 스레드
    # get_robot_state() 는 호출하지 않음
    # hw_cache 값만 읽어서 퍼블리시 — 스레드 안전
    stop_event    = threading.Event()
    publish_event = threading.Event()   # 메인 스레드가 hw_cache 갱신했음을 알림

    def hw_monitor_thread():
        while not stop_event.is_set():
            # hw_cache 는 메인 스레드에서만 갱신 → 읽기만 안전
            hw = hw_cache["code"]
            if hw == STATE_ROBOT_EMERGENCY_STOP:
                node.get_logger().error("🔴 [모니터] 비상정지 감지!")
            elif hw == STATE_ROBOT_PROTECTIVE_STOP:
                node.get_logger().warn("🟡 [모니터] 안전정지 감지!")
            elif hw == STATE_ROBOT_SAFE_OFF:
                node.get_logger().error("⚡ [모니터] 서보 꺼짐 감지!")
            # ✅ 항상 300ms 마다 퍼블리시 — 연결 유지
            publish_status()
            time.sleep(0.3)

    monitor_thread = threading.Thread(target=hw_monitor_thread, daemon=True)
    monitor_thread.start()
    node.get_logger().info("🔍 하드웨어 모니터 스레드 시작")

    # ✅ 메인 스레드 전용 hw 상태 갱신 함수
    # get_robot_state() 는 반드시 이 함수를 통해서만 호출
    def update_hw_cache():
        try:
            hw_cache["code"] = get_robot_state()
        except Exception as e:
            node.get_logger().warn(f"get_robot_state 오류: {e}")

    # ✅ 서보 복구 공통 함수 (메인 스레드에서 호출)
    def recover_servo(current_flower_idx, control_cmd, log_msg):
        node.get_logger().warn(log_msg)
        publish_status(log_msg, "WARN")
        try:
            drl_script_stop(DR_QSTOP_STO)
        except:
            pass
        time.sleep(1.0)
        node.get_logger().warn("   → SetRobotControl 서보 ON 시도...")
        if call_set_robot_control(control_cmd):
            node.get_logger().info("   → 서보 ON 명령 전송. 복구 대기 중...")
            time.sleep(3.0)
            update_hw_cache()   # ✅ 메인 스레드에서 호출
            if hw_cache["code"] == STATE_ROBOT_STANDBY:
                node.get_logger().info("   → ✅ 서보 ON 성공! 초기화 재수행...")
                initialize_robot()
                msg = f"복구 완료! {current_flower_idx + 1}번 꽃부터 재개"
                node.get_logger().info(f"▶️ {msg}")
                publish_status(msg, "OK")
            else:
                node.get_logger().error("   → ❌ 복구 후에도 정상 상태 아님.")
                publish_status("복구 실패 — 수동 조치 필요", "ERROR")
        else:
            node.get_logger().error("   → ❌ SetRobotControl 실패.")
            publish_status("SetRobotControl 실패 — 수동 조치 필요", "ERROR")

    # ✅ 🟡 안전정지(5) 처리 (메인 스레드에서 호출)
    def handle_protective_stop(current_flower_idx):
        recover_servo(
            current_flower_idx,
            CONTROL_RESET_SAFE_STOP,
            f"🟡 안전정지(5) 감지! 보호 정지 해제 시도 ({current_flower_idx + 1}번 꽃 재개 예정)"
        )
        # 해제될 때까지 메인 스레드에서 폴링
        update_hw_cache()
        while hw_cache["code"] == STATE_ROBOT_PROTECTIVE_STOP:
            rclpy.spin_once(node, timeout_sec=0.1)
            update_hw_cache()
        msg = f"안전정지 해제 → {current_flower_idx + 1}번 꽃부터 즉시 재개"
        node.get_logger().info(f"🟡 {msg}")
        publish_status(msg, "OK")

    # ✅ 🔴 비상정지(6) 처리 (메인 스레드에서 호출)
    def handle_emergency_stop(current_flower_idx):
        msg = f"비상정지(6) 감지! 홈 복귀 ({current_flower_idx + 1}번 꽃 재개 예정)"
        node.get_logger().error(f"🔴 {msg}")
        publish_status(msg, "ERROR")
        try:
            gripper_open()
            movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
        except Exception as e:
            node.get_logger().error(f"홈 복귀 오류: {e}")

        # 해제될 때까지 메인 스레드에서 폴링
        node.get_logger().error("🔴 비상정지 해제 대기 중...")
        publish_status("비상정지 해제 대기 중...", "ERROR")
        update_hw_cache()
        while hw_cache["code"] == STATE_ROBOT_EMERGENCY_STOP:
            rclpy.spin_once(node, timeout_sec=0.1)
            update_hw_cache()

        recover_servo(
            current_flower_idx,
            CONTROL_RESET_SAFE_OFF,
            "⚡ 비상정지 해제 후 서보 ON 시도..."
        )

        node.get_logger().info("🟢 5초 후 자동 재개...")
        for r in range(5, 0, -1):
            node.get_logger().info(f"   ⏳ {r}초 후 재개...")
            publish_status(f"비상정지 해제 — {r}초 후 자동 재개", "WARN", countdown=r)
            time.sleep(1)
        msg = f"재개! {current_flower_idx + 1}번 꽃부터"
        node.get_logger().info(f"▶️ {msg}")
        publish_status(msg, "OK", countdown=0)

    # ✅ 이동 래퍼 — 이동 후 메인 스레드에서 hw 상태 확인
    def safe_movej(target, vel, acc, flower_idx):
        while True:
            try:
                movej(target, vel=vel, acc=acc)
            except Exception as e:
                node.get_logger().warn(f"movej 중단: {e}")
            update_hw_cache()   # ✅ 메인 스레드에서 호출
            if hw_cache["code"] == STATE_ROBOT_EMERGENCY_STOP:
                handle_emergency_stop(flower_idx); continue
            if hw_cache["code"] in (STATE_ROBOT_PROTECTIVE_STOP, STATE_ROBOT_SAFE_OFF):
                handle_protective_stop(flower_idx); continue
            break

    def safe_movel(target, vel, acc, flower_idx):
        while True:
            try:
                movel(target, vel=vel, acc=acc)
            except Exception as e:
                node.get_logger().warn(f"movel 중단: {e}")
            update_hw_cache()   # ✅ 메인 스레드에서 호출
            if hw_cache["code"] == STATE_ROBOT_EMERGENCY_STOP:
                handle_emergency_stop(flower_idx); continue
            if hw_cache["code"] in (STATE_ROBOT_PROTECTIVE_STOP, STATE_ROBOT_SAFE_OFF):
                handle_protective_stop(flower_idx); continue
            break

    node.get_logger().info("📡 퍼블리셔로부터 좌표 대기 중...")
    update_hw_cache()
    publish_status("flower_robot_main 시작 — 좌표 대기 중", "INFO")

    try:
        while rclpy.ok():

            # 1. IDLE
            if current_state == STATE_IDLE:
                if new_param_received:
                    current_state      = STATE_BASIC
                    new_param_received = False
                    resume_from_index  = 0
                    publish_status("좌표 수신 → STATE_BASIC", "OK")
                else:
                    rclpy.spin_once(node, timeout_sec=0.1)
                    update_hw_cache()   # ✅ IDLE 루프에서도 주기적으로 갱신
                    continue

            # 2. BASIC
            elif current_state == STATE_BASIC:
                node.get_logger().info(f"▶️ 일반 공정 시작 ({resume_from_index + 1}번 꽃부터)")

                set_ref_coord(107)

                if resume_from_index == 0:
                    target_pos_dic     = {}
                    target_up_pos_dic  = {}
                    target_up_pos_dic1 = {}
                    target_up_pos_dic3 = {}
                    for i in sorted(posx_dic.keys()):
                        target_pos_dic[i]     = posx(posx_dic[i])
                        up = posx_dic[i].copy(); up[1] += 30
                        target_up_pos_dic[i]  = posx(up)
                        up1 = posx_dic[i].copy(); up1[1] += 40; up1[0] -= 70
                        target_up_pos_dic3[i] = posx(up1)
                        exit_pos = posx_dic[i].copy(); exit_pos[2] += 60
                        target_up_pos_dic1[i] = posx(exit_pos)

                movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                gripper_open()

                for i in sorted(target_pos_dic.keys()):
                    if i < resume_from_index:
                        continue

                    wait_for_pause()
                    if cancel_signal_received: break

                    node.get_logger().info(f"🌸 {i+1}번 꽃 작업")
                    publish_status(f"{i+1}번 꽃 작업 시작", "INFO")

                    safe_movej(flower_initial_position_J, CATCH_V_J, CATCH_ACC_J, i)
                    wait_for_pause()

                    gripper_close()
                    wait_for_pause()

                    safe_movej(WAYPOINT_J, HOME_V_J, HOME_ACC_J, i)
                    wait_for_pause()

                    safe_movel(target_up_pos_dic3[i], TARGET_V_L, TARGET_A_L, i)
                    wait_for_pause()

                    safe_movel(target_up_pos_dic[i], TARGET_V_L, TARGET_A_L, i)
                    wait_for_pause()

                    safe_movel(target_pos_dic[i], INSERT_V_L, INSERT_A_L, i)
                    wait_for_pause()

                    gripper_open()
                    wait_for_pause()

                    safe_movel(target_up_pos_dic1[i], VELOCITY_L, ACC_L, i)
                    wait_for_pause()

                    resume_from_index = i + 1
                    node.get_logger().info(f"✅ {i+1}번 꽃 완료")
                    publish_status(f"{i+1}번 꽃 완료", "OK")

                if cancel_signal_received:
                    current_state = STATE_REPROCESS
                else:
                    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                    resume_from_index = 0
                    current_state     = STATE_IDLE
                    publish_status("모든 작업 완료 → IDLE", "OK")

            # 3. REPROCESS
            elif current_state == STATE_REPROCESS:
                node.get_logger().warn("🔄 취소 공정")
                publish_status("취소 공정 — 홈 복귀 중", "WARN")
                gripper_open()
                movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                cancel_signal_received = False
                resume_from_index      = 0
                current_state          = STATE_IDLE
                node.get_logger().info("🔙 홈으로 복귀")
                publish_status("홈 복귀 완료 → IDLE", "OK")

            # 힘제어 잠시 주석
            # start_time = time.time()
            # while (time.time() - start_time) < 5.0:
            #     force = get_tool_force()
            #     if abs(force[1]) > 3.0:
            #         node.get_logger().info("✅ 접촉 감지! 그리퍼 개방")
            #         gripper_open()
            #         break
            #     wait(0.05)

    finally:
        stop_event.set()
        node.get_logger().info("🛑 모니터 스레드 종료")


def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("flower_robot_main", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    node.create_subscription(Float64MultiArray, "new_parameter", param_callback, 10)

    try:
        initialize_robot()
        perform_task()
    except KeyboardInterrupt:
        node.get_logger().warn("사용자에 의해 중단됨")
    finally:
        rclpy.shutdown()

if __name__ == "__main__":
    main()

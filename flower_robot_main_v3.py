import rclpy
import DR_init
import time
import threading
from std_msgs.msg import Float64MultiArray
from dsr_msgs2.srv import SetRobotControl  # ✅ [추가] 서보 ON 서비스

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

# ✅ [추가] DSR 로봇 하드웨어 상태 상수 (참고 코드 기준)
STATE_ROBOT_STANDBY         = 1  # 정상 대기
STATE_ROBOT_MOVING          = 2  # 이동 중
STATE_ROBOT_SAFE_OFF        = 3  # 서보 꺼짐
STATE_ROBOT_PROTECTIVE_STOP = 5  # 🟡 안전정지 (보호 정지)
STATE_ROBOT_EMERGENCY_STOP  = 6  # 🔴 비상정지

# ✅ [추가] 서보 제어 명령 상수
CONTROL_RESET_SAFE_STOP = 2  # 보호 정지 해제
CONTROL_RESET_SAFE_OFF  = 3  # 서보 ON (Safe Off → Standby)

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

resume_from_index = 0  # ✅ [추가] 정지 후 재개할 꽃 인덱스

target_pos_dic     = {}
target_up_pos_dic  = {}
target_up_pos_dic1 = {}
target_up_pos_dic2 = {}
target_up_pos_dic3 = {}

# 티칭된 안전 위치
HOME_JReady               = [19.20, -6.90, 86.79, 0.07, 100.94, 13.81]
flower_initial_position_J = [40.25, 27.42, 63.42, 87.97, -40.38, 0.53]
WAYPOINT_J                = [24.1, 21.51, 77.77, 3.33, 81.80, 23.66]

# =========================
# ✅ [추가] SetRobotControl 서비스 호출
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
        get_robot_state, set_robot_mode, ROBOT_MODE_AUTONOMOUS,  # ✅ [추가]
        drl_script_stop, DR_QSTOP_STO                           # ✅ [추가]
    )
    global new_param_received, cancel_signal_received, basic_process, re_process
    global pause_signal, current_state, resume_from_index

    node = DR_init.__dsr__node

    def gripper_open():
        set_digital_output(1, OFF); set_digital_output(2, ON); wait(0.3)

    def gripper_close():
        set_digital_output(1, ON); set_digital_output(2, OFF); wait(0.3)

    def wait_for_pause():
        if pause_signal:
            node.get_logger().warn("⏸️ 일시정지 중... Play 신호를 기다립니다.")
            while pause_signal:
                rclpy.spin_once(node, timeout_sec=0.1)
                wait(0.1)

    # ✅ [추가] 별도 스레드에서 300ms마다 폴링 — 이동 중에도 실시간 감지
    monitor_flag = {"active": False}
    stop_event   = threading.Event()

    def hw_monitor_thread():
        while not stop_event.is_set():
            if not monitor_flag["active"]:
                time.sleep(0.1)
                continue
            try:
                hw = get_robot_state()
                if hw == STATE_ROBOT_EMERGENCY_STOP:
                    node.get_logger().error("🔴 [모니터] 비상정지 감지!")
                elif hw == STATE_ROBOT_PROTECTIVE_STOP:
                    node.get_logger().warn("🟡 [모니터] 안전정지 감지!")
                elif hw == STATE_ROBOT_SAFE_OFF:
                    node.get_logger().error("⚡ [모니터] 서보 꺼짐 감지!")
            except:
                pass
            time.sleep(0.3)

    monitor_thread = threading.Thread(target=hw_monitor_thread, daemon=True)
    monitor_thread.start()
    node.get_logger().info("🔍 하드웨어 모니터 스레드 시작")

    # ✅ [추가] 서보 ON 복구 공통 함수
    def recover_servo(current_flower_idx, control_cmd, log_msg):
        """안전정지/서보꺼짐 → SetRobotControl → 서보 ON → 초기화 재수행"""
        node.get_logger().warn(log_msg)
        try:
            drl_script_stop(DR_QSTOP_STO)
        except:
            pass
        time.sleep(1.0)

        node.get_logger().warn("   → SetRobotControl 서보 ON 시도...")
        if call_set_robot_control(control_cmd):
            node.get_logger().info("   → 서보 ON 명령 전송. 복구 대기 중...")
            time.sleep(3.0)
            if get_robot_state() == STATE_ROBOT_STANDBY:
                node.get_logger().info("   → ✅ 서보 ON 성공! 초기화 재수행...")
                initialize_robot()
                node.get_logger().info(
                    f"▶️ 복구 완료! {current_flower_idx + 1}번 꽃부터 재개합니다."
                )
            else:
                node.get_logger().error("   → ❌ 복구 후에도 정상 상태 아님. 재시도 대기...")
        else:
            node.get_logger().error("   → ❌ SetRobotControl 실패. 수동 조치 필요")

    # ✅ [추가] 🟡 안전정지(5) 처리 — SetRobotControl(2) 로 해제 후 즉시 재개
    def handle_protective_stop(current_flower_idx):
        recover_servo(
            current_flower_idx,
            CONTROL_RESET_SAFE_STOP,
            f"🟡 안전정지(5) 감지! 보호 정지 해제 시도 ({current_flower_idx + 1}번 꽃 재개 예정)"
        )
        # 해제될 때까지 폴링 (recover_servo 후에도 안 됐을 경우 대비)
        while get_robot_state() == STATE_ROBOT_PROTECTIVE_STOP:
            rclpy.spin_once(node, timeout_sec=0.1)
        node.get_logger().info(f"🟡 안전정지 해제! {current_flower_idx + 1}번 꽃부터 즉시 재개")

    # ✅ [추가] 🔴 비상정지(6) 처리 — 홈 복귀 후 5초 뒤 자동 재개
    def handle_emergency_stop(current_flower_idx):
        node.get_logger().error(
            f"🔴 비상정지(6) 감지! 홈 복귀 ({current_flower_idx + 1}번 꽃 재개 예정)"
        )
        try:
            gripper_open()
            movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
        except Exception as e:
            node.get_logger().error(f"홈 복귀 오류: {e}")

        # 비상정지 해제될 때까지 폴링
        node.get_logger().error("🔴 비상정지 해제 대기 중...")
        while get_robot_state() == STATE_ROBOT_EMERGENCY_STOP:
            rclpy.spin_once(node, timeout_sec=0.1)

        # 해제 후 서보 ON 복구
        recover_servo(
            current_flower_idx,
            CONTROL_RESET_SAFE_OFF,
            "⚡ 비상정지 해제 후 서보 ON 시도..."
        )

        node.get_logger().info("🟢 5초 후 자동 재개...")
        for r in range(5, 0, -1):
            node.get_logger().info(f"   ⏳ {r}초 후 재개...")
            time.sleep(1)
        node.get_logger().info(f"▶️ 재개! {current_flower_idx + 1}번 꽃부터")

    # ✅ [추가] 이동 래퍼 — 정지 감지 시 처리 후 해당 명령 재실행
    def safe_movej(target, vel, acc, flower_idx):
        while True:
            try:
                movej(target, vel=vel, acc=acc)
            except Exception as e:
                node.get_logger().warn(f"movej 중단: {e}")
            hw = get_robot_state()
            if hw == STATE_ROBOT_EMERGENCY_STOP:
                handle_emergency_stop(flower_idx); continue
            if hw in (STATE_ROBOT_PROTECTIVE_STOP, STATE_ROBOT_SAFE_OFF):
                handle_protective_stop(flower_idx); continue
            break

    def safe_movel(target, vel, acc, flower_idx):
        while True:
            try:
                movel(target, vel=vel, acc=acc)
            except Exception as e:
                node.get_logger().warn(f"movel 중단: {e}")
            hw = get_robot_state()
            if hw == STATE_ROBOT_EMERGENCY_STOP:
                handle_emergency_stop(flower_idx); continue
            if hw in (STATE_ROBOT_PROTECTIVE_STOP, STATE_ROBOT_SAFE_OFF):
                handle_protective_stop(flower_idx); continue
            break

    node.get_logger().info("📡 퍼블리셔로부터 좌표 대기 중...")

    try:
        while rclpy.ok():
            # 1. IDLE 상태 및 데이터 수신
            if current_state == STATE_IDLE:
                if new_param_received:
                    current_state      = STATE_BASIC
                    new_param_received = False
                    resume_from_index  = 0
                else:
                    rclpy.spin_once(node, timeout_sec=0.1)
                    continue

            # 2. BASIC 상태 (공정 진행)
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

                monitor_flag["active"] = True
                movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                gripper_open()

                for i in sorted(target_pos_dic.keys()):
                    if i < resume_from_index:
                        continue

                    wait_for_pause()
                    if cancel_signal_received: break

                    node.get_logger().info(f"🌸 {i+1}번 꽃 작업")

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

                monitor_flag["active"] = False

                if cancel_signal_received:
                    current_state = STATE_REPROCESS
                else:
                    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                    resume_from_index = 0
                    current_state     = STATE_IDLE

            # 3. REPROCESS 상태
            elif current_state == STATE_REPROCESS:
                node.get_logger().warn("🔄 취소 공정")
                monitor_flag["active"] = False
                gripper_open()
                movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                cancel_signal_received = False
                resume_from_index      = 0
                current_state          = STATE_IDLE
                node.get_logger().info("🔙 홈으로 복귀")

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
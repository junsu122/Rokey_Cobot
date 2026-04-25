import rclpy
import DR_init
import time
from std_msgs.msg import Float64MultiArray

# =========================
# ROBOT CONFIG
# =========================
ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL  = "Tool Weight"
ROBOT_TCP   = "GripperDA_v1"

# 속도 설정  기본값
# HOME_V_J = 300; HOME_ACC_J = 200
# CATCH_V_J = 300; CATCH_ACC_J = 200        
# VELOCITY_L = 250; ACC_L = 200
# INSERT_V_L = 300; INSERT_A_L = 200
# TARGET_V_L = 200; TARGET_A_L = 100

# 엄청 빠른 버젼
# HOME_V_J = 550; HOME_ACC_J = 350
# CATCH_V_J = 550; CATCH_ACC_J = 350        
# VELOCITY_L = 500; ACC_L = 350
# INSERT_V_L = 600; INSERT_A_L = 500
# TARGET_V_L = 350; TARGET_A_L = 200

#1.5배 버젼
HOME_V_J = 450; HOME_ACC_J = 300
CATCH_V_J = 450; CATCH_ACC_J = 300        
VELOCITY_L = 400; ACC_L = 300
INSERT_V_L = 600; INSERT_A_L = 500
TARGET_V_L = 350; TARGET_A_L = 200

# DR INIT
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# =========================
# GLOBAL STATE & FSM
# =========================
STATE_IDLE      = "IDLE"
STATE_BASIC     = "BASIC"
STATE_PAUSED    = "PAUSED"
STATE_REPROCESS = "REPROCESS"

current_state = STATE_IDLE
pause_signal = False  # 일시정지 신호 [1,1,1,1,1,1] 감지
cancel_signal_received = False # 취소 신호 [0,0,0,0,0,0] 감지
basic_process = True  ### 주문이 되었을때 basic하게 실행되는 공정
re_process = False
new_param_received = False
posx_dic = {}

target_pos_dic = {}
target_up_pos_dic = {}
target_up_pos_dic1 = {}
target_up_pos_dic2 = {}
target_up_pos_dic3 = {}


# 티칭된 안전 위치
HOME_JReady = [19.20, -6.90, 86.79, 0.07, 100.94, 13.81]
flower_initial_position_J = [40.25, 27.42, 63.42, 87.97, -40.38, 0.53]

# 🔥 [추가] 경유점 (Way-point): 꽃을 집고 판으로 가기 전 거치는 중간 관절 각도
# 작업 공간 중앙 상단으로 팔을 뻗는 각도로 설정하세요 (예시 값)
WAYPOINT_J = [24.1, 21.51, 77.77, 3.33, 81.80, 23.66] 

# =========================
# CALLBACK
# =========================
def param_callback(msg):
    global new_param_received, posx_dic , cancel_signal_received, pause_signal
    node = DR_init.__dsr__node
    
    # [체크] 취소 신호 (0,0,0,0,0,0)
    if len(msg.data) == 6 and all(v == 0.0 for v in msg.data):
        cancel_signal_received = True
        node.get_logger().warn("🚨 취소 신호 감지!")
        return
    
    # [체크] 일시정지 신호 (1,1,1,1,1,1)
    if len(msg.data) == 6 and all(v == 1.0 for v in msg.data):
        pause_signal = True
        node.get_logger().warn("⏸️ 일시정지 신호 감지!")
        return
    
    # 3. 🔥 재개 신호 [2,2,2,2,2,2] 추가
    if len(msg.data) == 6 and all(v == 2.0 for v in msg.data):
        if pause_signal:
            pause_signal = False
            node.get_logger().info("▶️ 재개 신호 감지! 작업을 다시 시작합니다. (Resume)")
        return
    
    # 4. 정상 좌표인지 확인
    if len(msg.data) % 6 != 0:
        node.get_logger().error("❌ 잘못된 좌표 형식입니다.")
        return

    posx_dic.clear()
    num_poses = len(msg.data) // 6
    for i in range(num_poses):
        posx_dic[i] = list(msg.data[i*6:(i+1)*6])

    new_param_received = True
    cancel_signal_received = False
    pause_signal = False
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
        set_digital_output, OFF, ON, wait, get_tool_force
    )
    global new_param_received, cancel_signal_received, basic_process, re_process, pause_signal, current_state

    node = DR_init.__dsr__node

    def gripper_open():
        set_digital_output(1, OFF); set_digital_output(2, ON); wait(0.3)

    def gripper_close():
        set_digital_output(1, ON); set_digital_output(2, OFF); wait(0.3)

    # 일시정지 체크 유틸리티
    def wait_for_pause():
        if pause_signal:
            node.get_logger().warn("⏸️ 일시정지 중... Play 신호를 기다립니다.")
            while pause_signal:
                rclpy.spin_once(node, timeout_sec=0.1)
                wait(0.1)


    node.get_logger().info("📡 퍼블리셔로부터 좌표 대기 중...")

    while rclpy.ok():
        # 1. 데이터 수신 대기 구간
        # 1. IDLE 상태 및 데이터 수신
        if current_state == STATE_IDLE:
            if new_param_received:
                current_state = STATE_BASIC
                new_param_received = False
            else:
                rclpy.spin_once(node, timeout_sec=0.1)
                continue

        # 2. BASIC 상태 (공정 진행)
        elif current_state == STATE_BASIC:
            node.get_logger().info("▶️ 일반 공정 시작")
            
            set_ref_coord(107)
            target_pos_dic = {}
            target_up_pos_dic = {}
            target_up_pos_dic1 = {}
            target_up_pos_dic3 = {}

            # 좌표 계산
            for i in sorted(posx_dic.keys()):
                target_pos_dic[i] = posx(posx_dic[i])
                up = posx_dic[i].copy(); up[1] += 30; target_up_pos_dic[i] = posx(up)
                up1 = posx_dic[i].copy(); up1[1] += 40; up1[0] -= 70; target_up_pos_dic3[i] = posx(up1)
                exit_pos = posx_dic[i].copy(); exit_pos[2] += 60; target_up_pos_dic1[i] = posx(exit_pos)

            movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J) #### 홈으로 가는 명령
            gripper_open()                                   #### 그리퍼 열기

            for i in sorted(target_pos_dic.keys()):
                #################################### [체크] 매 이동 명령 전 일시정지 및 취소 확인 ######################################
                wait_for_pause()
                if cancel_signal_received: break 

                node.get_logger().info(f"🌸 {i+1}번 꽃 작업")
                
                movej(flower_initial_position_J, vel=CATCH_V_J, acc=CATCH_ACC_J)
                wait_for_pause() ####################### 이동 직후마다 pause 체크 // 모든 과정에 추가 #########################
                
                gripper_close()
                wait_for_pause()

                movej(WAYPOINT_J, vel=HOME_V_J, acc=HOME_ACC_J)
                wait_for_pause()

                movel(target_up_pos_dic3[i], vel=TARGET_V_L, acc=TARGET_A_L)
                wait_for_pause()

                movel(target_up_pos_dic[i], vel=TARGET_V_L, acc=TARGET_A_L)
                wait_for_pause()
                
                movel(target_pos_dic[i], vel=INSERT_V_L, acc=INSERT_A_L)
                wait_for_pause()

                gripper_open()
                wait_for_pause()

                movel(target_up_pos_dic1[i], vel=VELOCITY_L, acc=ACC_L)
                wait_for_pause()

            # 결과에 따라 상태 전이
            if cancel_signal_received:
                current_state = STATE_REPROCESS
            else:
                movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                current_state = STATE_IDLE

        ################################################################ 3. REPROCESS 상태# ############################################################
        elif current_state == STATE_REPROCESS:
            node.get_logger().warn("🔄 취소 공정")
            gripper_open()
            movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
            
            cancel_signal_received = False
            current_state = STATE_IDLE
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


# ... (main 함수는 기존과 동일)

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
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

FIXED_SIDE_X = 30

# =========================
# GLOBAL STATE
# =========================
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
    global new_param_received, posx_dic
    node = DR_init.__dsr__node
    
    if len(msg.data) % 6 != 0:
        node.get_logger().error("❌ 데이터 오염: 6의 배수가 아님")
        return

    posx_dic.clear()
    num_poses = len(msg.data) // 6
    for i in range(num_poses):
        posx_dic[i] = list(msg.data[i*6:(i+1)*6])

    new_param_received = True
    node.get_logger().info(f"📥 {num_poses}개의 목표 좌표 수신 완료")

# =========================
# pause
# =========================

def call_pause():
    """
    [핵심 기능] 로봇 이동 일시 정지 (Service Call)
    - 라이브러리 함수가 아닌 ROS 2 Service를 직접 호출하여 즉각적인 Pause를 요청합니다.
    """
    from dsr_msgs2.srv import MovePause
    
    # 서비스 클라이언트 생성: /{ROBOT_ID}/motion/move_pause 서비스 호출
    cli = DR_init.__dsr__node.create_client(MovePause, f'/{ROBOT_ID}/motion/move_pause')
    
    # 서비스 서버가 준비될 때까지 대기
    cli.wait_for_service()
    
    # 요청 전송 (비동기 호출) 및 완료 대기
    req = MovePause.Request()
    future = cli.call_async(req)
    rclpy.spin_until_future_complete(DR_init.__dsr__node, future)
    
    print(">>> 이동이 Pause 되었습니다.")

# =========================
# resume
# =========================

def call_resume():
    """
    [핵심 기능] 로봇 이동 재개 (Service Call)
    - Pause 된 로봇의 남은 모션을 재개합니다.
    """
    from dsr_msgs2.srv import MoveResume
    
    # 서비스 클라이언트 생성: /{ROBOT_ID}/motion/move_resume 서비스 호출
    cli = DR_init.__dsr__node.create_client(MoveResume, f'/{ROBOT_ID}/motion/move_resume')
    cli.wait_for_service()
    
    # 요청 전송 및 완료 대기
    req = MoveResume.Request()
    future = cli.call_async(req)
    rclpy.spin_until_future_complete(DR_init.__dsr__node, future)
    
    print(">>> 이동이 Resume 되었습니다.")


# =========================
# INIT
# =========================
def initialize_robot():
    from DSR_ROBOT2 import (
        set_tool, set_tcp, set_robot_mode, set_ref_coord,
        ROBOT_MODE_AUTONOMOUS
    )
    from DSR_ROBOT2 import get_robot_mode,set_robot_mode, set_tool, set_tcp, get_tool, get_tcp

    node = DR_init.__dsr__node
    
    set_ref_coord(107) 
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    print("#" * 50)
    print("Initializing robot with the following settings:")
    print(f"ROBOT_ID: {ROBOT_ID}")
    print(f"ROBOT_MODEL: {ROBOT_MODEL}")
    print(f"ROBOT_TCP: {get_tcp()}") 
    print(f"ROBOT_TOOL: {get_tool()}")
    print(f"ROBOT_MODE 0:수동, 1:자동 : {get_robot_mode()}")

    print("#" * 50)
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
    global new_param_received

    node = DR_init.__dsr__node

    def gripper_open():
        set_digital_output(1, OFF); set_digital_output(2, ON); wait(0.3)

    def gripper_close():
        set_digital_output(1, ON); set_digital_output(2, OFF); wait(0.3)

    node.get_logger().info("📡 퍼블리셔로부터 좌표 대기 중...")

    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if new_param_received:
            new_param_received = False
            break

    set_ref_coord(107) 
    target_pos_dic.clear()
    target_up_pos_dic.clear()

    for i in sorted(posx_dic.keys()):
        # 1. 실제 삽입 목표 (원본 데이터 유지 혹은 필요시 고정)
        target_pos_dic[i] = posx(posx_dic[i])
        
        # 2. 목표 위치 위로 접근 (up)
        up = posx_dic[i].copy()
        up[1] += 40  
        target_up_pos_dic[i] = posx(up)

        # 🔥 [수정] 측면 경유지 (up1 -> target_up_pos_dic3)
        # x좌표를 posx_dic[i][0] 대신 FIXED_SIDE_X로 고정
        up1 = posx_dic[i].copy()
        up1[0] = FIXED_SIDE_X    # X값을 고정값으로 덮어씀
        up1[1] += 50             # 기존 Y 상대이동 유지
        target_up_pos_dic3[i] = posx(up1)

        # 4. 퇴출 위치 (exit_pos)
        exit_pos = posx_dic[i].copy()
        exit_pos[2] += 60 
        target_up_pos_dic1[i] = posx(exit_pos)

    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
    gripper_open()

    # =========================
    # FLOWER LOOP
    # =========================
    for i in sorted(target_pos_dic.keys()):
        node.get_logger().info(f"🌸 {i+1}번 꽃 작업 시작")

        # 1. 꽃 집기 위치로 이동 및 파지
        movej(flower_initial_position_J, vel=CATCH_V_J, acc=CATCH_ACC_J)
        wait(1.5)
        gripper_close()
        wait(0.5)

        # 🚀 [추가] 경유점으로 이동: 꽃을 집어 올린 후 판 근처로 가기 전 중간 지점
        node.get_logger().info("🚀 경유점(Way-point) 이동 중...")
        movej(WAYPOINT_J, vel=HOME_V_J, acc=HOME_ACC_J)

        node.get_logger().info("🚀 경유점(Way-point) 이동 중...1")
        movel(target_up_pos_dic3[i], vel=TARGET_V_L, acc=TARGET_A_L)

        # node.get_logger().info("🚀 경유점(Way-point) 이동 중...2")
        # movel(target_up_pos_dic4[i], vel=TARGET_V_L, acc=TARGET_A_L)

        # 2. 목표 위치 위로 접근 (104번 좌표계 기준)
        node.get_logger().info(f"📍 목표 상단 접근: {target_up_pos_dic[i]}")
        movel(target_up_pos_dic[i], vel=TARGET_V_L, acc=TARGET_A_L)

        # 3. 실제 삽입 위치로 이동하며 힘 감지
        node.get_logger().info("⬇️ 삽입 시작")
        movel(target_pos_dic[i], vel=INSERT_V_L, acc=INSERT_A_L)

        # 힘제어 잠시 주석
        start_time = time.time()
        while (time.time() - start_time) < 5.0:
            force = get_tool_force()
            if  abs(force[1]) > 4.0 :
                node.get_logger().info("✅ 접촉 감지! 그리퍼 개방")
                node.get_logger().info(f"FORCE: {force}")

                gripper_open()
                break
            wait(0.05)
##############################################################################################################

        # start_time = time.time()
        # count = 0

        # while (time.time() - start_time) < 5.0:
        #     force = get_tool_force()

        #     if force is None:
        #         continue

        #     if abs(force[1]) > 5.0:
        #         count += 1
        #     else:
        #         count = 0

        #     if count >= 3:
        #         node.get_logger().info("✅ 접촉 감지! 그리퍼 개방")
        #         gripper_open()
        #         break

        #     wait(0.05)
        # else:
        #     node.get_logger().info("❌ 접촉 없음 (timeout)")

###############################################################################################################




        gripper_open()
        
        # 4. 안전하게 회피 이동 (옆으로 피하지 않고 표면에서 수직 이격만 수행)
        
        # 삽입 위치의 좌표 리스트 복사
        escape_pos = list(target_pos_dic[i])
        
        # [수정] 옆으로 피하지 않기 위해 X, Z는 그대로 두고 Y축(깊이 방향)으로만 후퇴
        # 액자 표면에서 확실히 떨어지도록 5mm~10mm 정도 여유 있게 이격 권장
        escape_pos[1] += 10.0  
        
        node.get_logger().info("⬆️ 표면 수직 이격 중 (Y축 후퇴)")
        movel(posx(escape_pos), vel=VELOCITY_L, acc=ACC_L)

        # 이후 완전히 안전한 높이(Z축 상단)로 이동
        movel(target_up_pos_dic1[i], vel=VELOCITY_L, acc=ACC_L)
        node.get_logger().info(f"✨ {i+1}번 완료")

    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)

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
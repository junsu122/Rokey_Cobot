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
# GLOBAL STATE
# =========================
new_param_received = False
posx_dic = {}

target_pos_dic = {}
target_up_pos_dic = {}
target_up_pos_dic1 = {}
target_up_pos_dic2 = {}

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
        target_pos_dic[i] = posx(posx_dic[i])
        up = posx_dic[i].copy()
        up[1] += 150  
        target_up_pos_dic[i] = posx(up)

        exit_pos = posx_dic[i].copy()
        exit_pos[2] += 50 
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
        gripper_close()
        wait(0.5)

        # 🚀 [추가] 경유점으로 이동: 꽃을 집어 올린 후 판 근처로 가기 전 중간 지점
        node.get_logger().info("🚀 경유점(Way-point) 이동 중...")
        movej(WAYPOINT_J, vel=HOME_V_J, acc=HOME_ACC_J)

        # 2. 목표 위치 위로 접근 (104번 좌표계 기준)
        node.get_logger().info(f"📍 목표 상단 접근: {target_up_pos_dic[i]}")
        movel(target_up_pos_dic[i], vel=TARGET_V_L, acc=TARGET_A_L)

        # 3. 실제 삽입 위치로 이동하며 힘 감지
        node.get_logger().info("⬇️ 삽입 시작")
        movel(target_pos_dic[i], vel=INSERT_V_L, acc=INSERT_A_L)

        start_time = time.time()
        while (time.time() - start_time) < 5.0:
            force = get_tool_force()
            if abs(force[1]) > 3.0:
                node.get_logger().info("✅ 접촉 감지! 그리퍼 개방")
                gripper_open()
                break
            wait(0.05)
        
        # 4. 안전하게 회피 이동
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
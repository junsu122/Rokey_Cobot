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

HOME_V_J = 200          #HOME_VJ
HOME_ACC_J = 100        #HOME_ACC_j

CATCH_V_J = 200         # 홈/ 꽃 잡으러가는 속도
CATCH_ACC_J = 100        

VELOCITY_L = 300        # 삽입후 회피 가동
ACC_L      = 200

INSERT_V_L = 500        # 꽃 삽입 속도
INSERT_A_L = 300

TARGET_V_L = 200        # 꽃 위치 이동
TARGET_A_L = 100

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

HOME_JReady = [19.20, -6.90, 86.79, 0.07, 100.94, 13.81]
# flower_initial_position_J = [40.25, 27.42, 63.42, 87.97, -40.38, 0.53]
flower_initial_position_J = [13.38, -1.58, 92.67, -88.80, 13.56, 0.04]


# =========================
# CALLBACK
# =========================
def param_callback(msg):
    global new_param_received, posx_dic

    node = DR_init.__dsr__node
    new_param_received = True

    if len(msg.data) % 6 != 0:
        node.get_logger().error("❌ 데이터 오류")
        return

    posx_dic.clear()

    for i in range(len(msg.data)//6):
        posx_dic[i] = list(msg.data[i*6:(i+1)*6])

    node.get_logger().info(f"📥 데이터 {len(posx_dic)}개 수신")

# =========================
# INIT
# =========================
def initialize_robot():
    from DSR_ROBOT2 import (
        set_tool, set_tcp,
        set_robot_mode, get_robot_mode,set_ref_coord,
        ROBOT_MODE_MANUAL, ROBOT_MODE_AUTONOMOUS
    )

    node = DR_init.__dsr__node
    set_ref_coord(104)
    set_robot_mode(ROBOT_MODE_MANUAL)
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)

    time.sleep(2)

# =========================
# FORCE INSERT (Y-axis stable)
# =========================
def force_insert_y():
    from DSR_ROBOT2 import (
        task_compliance_ctrl,
        set_ref_coord,
        set_desired_force,
        release_force,
        release_compliance_ctrl,
        DR_FC_MOD_REL,
        wait,
        get_tool_force
    )

    node = DR_init.__dsr__node

    set_ref_coord(104)

    task_compliance_ctrl(stx=[1000, 1000, 200, 200, 200, 200])
    wait(1.0)

    set_desired_force(
        fd=[0, 8, 0, 0, 0, 0],
        dir=[0, 1, 0, 0, 0, 0],
        mod=DR_FC_MOD_REL
    )

    wait(0.5)

    # contact loop
    while rclpy.ok():

        force = get_tool_force()
        node.get_logger().info(f"FORCE: {force}")

        if abs(force[1]) > 6:
            node.get_logger().info("📍 contact detected")
            break

        wait(0.01)

    release_force()
    release_compliance_ctrl()

# =========================
# TASK
# =========================
def perform_task():
    from DSR_ROBOT2 import (
        posx,posj, movej, movel,get_current_posj,get_current_posx,
        set_digital_output, OFF, ON, wait
    )

    global new_param_received

    node = DR_init.__dsr__node

    def gripper_open():
        set_digital_output(1, OFF)
        set_digital_output(2, ON)
        wait(0.3)

    def gripper_close():
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        wait(0.3)

    node.get_logger().info("📡 WAIT PARAM")

    # =========================
    # 🔥 FIX: 정상 WAIT 구조
    # =========================
    while rclpy.ok():

        rclpy.spin_once(node, timeout_sec=0.1)

        if new_param_received:
            node.get_logger().info("🔥 PARAM RECEIVED")
            new_param_received = False
            break

    # =========================
    # 좌표 변환
    # =========================
    target_pos_dic.clear()
    target_up_pos_dic.clear()
    target_up_pos_dic1.clear()
    target_up_pos_dic2.clear()

    for i in posx_dic.keys():

        target_pos_dic[i] = posx(posx_dic[i])

        up = posx_dic[i].copy()
        up[1] += 120
        target_up_pos_dic[i] = posx(up)

        up1 = posx_dic[i].copy()
        up1[2] += 50
        target_up_pos_dic1[i] = posx(up1)

        up2 = posx_dic[i].copy()
        up2[1] += 120
        up2[2] += 50
        target_up_pos_dic2[i] = posx(up2)

    # =========================
    # HOME
    # =========================
    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_V_J) # home
    wait(1)

    gripper_open()

    # =========================
    # FLOWER TASK
    # =========================
    for i in sorted(target_pos_dic.keys()):

        node.get_logger().info(f"🌸 작업 {i}")
        print("현재 관절각도:",get_current_posj())
        print("툴 좌표:",get_current_posx())



        movej(flower_initial_position_J, vel=CATCH_V_J, acc=CATCH_ACC_J)
        
        wait(0.2)

        gripper_close()

        movel(target_up_pos_dic[i], vel=TARGET_V_L, acc=TARGET_A_L)
        wait(0.2)

        # =========================
        # FORCE INSERT
        # =========================
        movel(target_pos_dic[i], vel=INSERT_V_L, acc=INSERT_A_L)

        from DSR_ROBOT2 import get_tool_force

        node.get_logger().info("🌸 insertion + release start")
        print("현재 관절각도:",get_current_posj())
        print("툴 좌표:",get_current_posx())


        while rclpy.ok():

            force = get_tool_force()
            node.get_logger().info(f"FORCE: {force}")
            print("현재 관절각도:",get_current_posj())
            print("툴 좌표:",get_current_posx())


            # ✔ Y축 압력 기준
            if abs(force[1]) > 5:

                node.get_logger().info("📍 pressure detected → release flower")
                print("현재 관절각도:",get_current_posj())
                print("툴 좌표:",get_current_posx())


                # 🔥 여기서 바로 놓기
                gripper_open()

                break 

            wait(0.01)

        wait(0.01)      

        node.get_logger().info("📍 삽입 완료")
        print("현재 관절각도:",get_current_posj())
        print("툴 좌표:",get_current_posx())


        movel(target_up_pos_dic1[i], vel=VELOCITY_L, acc=ACC_L)
        movel(target_up_pos_dic2[i], vel=VELOCITY_L, acc=ACC_L)

    movej(HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)

# =========================
# MAIN
# =========================
def main(args=None):
    rclpy.init(args=args)

    node = rclpy.create_node("move_basic", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    node.create_subscription(
        Float64MultiArray,
        "new_parameter",
        param_callback,
        10
    )

    try:
        initialize_robot()
        perform_task()

    except KeyboardInterrupt:
        node.get_logger().warn("STOP")

    finally:
        try:
            rclpy.shutdown()
        except:
            pass

if __name__ == "__main__":
    main()
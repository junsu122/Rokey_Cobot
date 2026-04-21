import rclpy
import DR_init
import time
from std_msgs.msg import Float64MultiArray

ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL  = "Tool Weight"
ROBOT_TCP   = "GripperDA_v1"
VELOCITY_J    = 80
ACC_J         = 50
VELOCITY_L    = 250
ACC_L         = 60
VELOCITY_fL   = 400
ACC_fL        = 450
HOME_V_J = 200; HOME_ACC_J = 100



DR_init.__dsr__id    = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# current_JReady = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]
current_JReady = [19.20, -6.90, 86.79, 0.07, 100.94, 13.81]
flower_initial_position_J = [40.25,27.42,63.42,87.97,-40.38,0.53]
# flower_initial_position_J = [17.28,7.19,82.19,-87.28,17.80,-185.97]
# flower_initial_position_L = [770.76,359.99,498.57,179.56,-89.26,-91.66]
WAYPOINT_J = [24.1, 21.51, 77.77, 3.33, 81.80, 23.66] 


new_param_received  = False
posx_dic = {}
target_pos_dic = {}
target_up_pos_dic = {}
target_up_pos_dic1 = {}
target_up_pos_dic2 = {}


def param_callback(msg):
    global new_param_received, posx_dic
    new_param_received  = True
    
    if new_param_received == True:
        for i in range(int(len(msg.data)/6)):
            start_idx = i * 6  # 0, 6, 12, ...
            end_idx = (i + 1) * 6  # 6, 12, 18, ...
            posx_dic[i] = list(msg.data[start_idx:end_idx])


def initialize_robot():
    from DSR_ROBOT2 import set_tool, set_tcp, set_robot_mode, get_robot_mode, set_ref_coord, \
                           ROBOT_MODE_MANUAL, ROBOT_MODE_AUTONOMOUS
    set_robot_mode(ROBOT_MODE_MANUAL)
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    set_ref_coord(107)
    time.sleep(2)
    print(f"[초기화 완료] mode={get_robot_mode()}")
    print("토픽 대기 중... (/dsr01/new_parameter)")

def perform_task():
    from DSR_ROBOT2 import posx, movej, movel, set_digital_output, ON, OFF, wait, set_ref_coord
    global current_JReady, posx_dic, target_pos_dic, target_up_pos_dic, new_param_received
    
    def gripper_open():
        set_digital_output(1, OFF)
        set_digital_output(2, ON)
        time.sleep(0.5)

    def gripper_close():
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        time.sleep(0.5)

    set_ref_coord(107) 

    while rclpy.ok():
        rclpy.spin_once(DR_init.__dsr__node, timeout_sec=0.1)

        if new_param_received:
            print(posx_dic)
            new_param_received = False

            movej(WAYPOINT_J, vel=HOME_V_J, acc=HOME_ACC_J)
            
            # 꽃 위치 좌표
            for i in range(len(posx_dic)):
                target_pos_dic[i] = posx(posx_dic[i])
            
            # 꽃 위치의 상승 좌표(전)
            for i in range(len(posx_dic)):
                target_up = posx_dic[i].copy()
                target_up[1] += 150
                target_up_pos_dic[i] = posx(target_up)

            # 꽃 위치의 상승 좌표(후)
            for i in range(len(posx_dic)):
                target_up1 = posx_dic[i].copy()
                target_up1[2] += 50
                target_up_pos_dic1[i] = posx(target_up1)

            # 꽃 위치의 상승 좌표(후)(후)
            for i in range(len(posx_dic)):
                target_up2 = posx_dic[i].copy()
                target_up2[1] += 150
                target_up2[2] += 50
                target_up_pos_dic2[i] = posx(target_up2)    
            
            # 홈 위치에서 시작
            movej(current_JReady, vel=VELOCITY_J, acc=ACC_J)
            wait(1)
            gripper_open()

            # 꽃 꽂기
            for i in range(len(target_pos_dic)):
                # 꽃 초기 위치
                movej(flower_initial_position_J, vel=VELOCITY_J, acc=ACC_J)
                wait(1)
                gripper_close()

                # 해당 좌표에서의 꽃꽂기
                movel(target_up_pos_dic[i], vel=VELOCITY_L, acc=ACC_L)
                movel(target_pos_dic[i], vel=VELOCITY_fL, acc=ACC_fL)
                wait(2)
                gripper_open()
                movel(target_up_pos_dic1[i], vel=VELOCITY_L, acc=ACC_L)
                movel(target_up_pos_dic2[i], vel=VELOCITY_L, acc=ACC_L)

            # 홈으로 돌아가기
            movej(current_JReady, vel=VELOCITY_J, acc=ACC_J)

            print("[완료] 다음 토픽 대기 중...\n")

def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("move_basic", namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    node.create_subscription(Float64MultiArray, 'new_parameter', param_callback, 10)

    try:
        initialize_robot()
        perform_task()
    except KeyboardInterrupt:
        print("\nShutdown...")
    finally:
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
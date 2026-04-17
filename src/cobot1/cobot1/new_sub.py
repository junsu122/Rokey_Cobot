import rclpy
import DR_init
import time
from std_msgs.msg import Float64MultiArray # 토픽 타입 추가

# 로봇 설정 상수
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"
VELOCITY = 40
ACC = 60

# 전역 변수로 좌표 설정 (초기값)
current_JReady = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]
current_pos1_coords = [500.0, 80.0, 200.0, 150.0, 179.0, 150.0]

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

def param_callback(msg):
    """토픽을 받으면 전역 좌표 변수를 업데이트함"""
    global current_JReady, current_pos1_coords
    if len(msg.data) == 12:
        current_JReady = list(msg.data[0:6])
        current_pos1_coords = list(msg.data[6:12])
        print(f"\n[Update] New parameters received!")
        print(f"New JReady: {current_JReady}")
        print(f"New pos1: {current_pos1_coords}\n")

def initialize_robot():
    from DSR_ROBOT2 import set_tool, set_tcp, get_tool, get_tcp, ROBOT_MODE_MANUAL, set_robot_mode, ROBOT_MODE_AUTONOMOUS
    set_robot_mode(ROBOT_MODE_MANUAL)
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2)
    print("Robot Initialized.")

def perform_task():
    from DSR_ROBOT2 import posx, movej, movel
    global current_JReady, current_pos1_coords
    
    print("Performing task... (Waiting for updates)")
    while rclpy.ok():
        # rclpy.spin_once를 호출하여 토픽이 왔는지 확인
        rclpy.spin_once(DR_init.__dsr__node, timeout_sec=0.1)
        
        # 현재 저장된 좌표로 동작 수행
        target_pos1 = posx(current_pos1_coords)
        
        print(f"Moving to JReady: {current_JReady}")
        movej(current_JReady, vel=VELOCITY, acc=ACC)
        
        print(f"Moving to pos1: {current_pos1_coords}")
        movel(target_pos1, vel=VELOCITY, acc=ACC)

def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("move_basic", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    # Subscriber 설정
    node.create_subscription(Float64MultiArray, 'new_parameter', param_callback, 10)

    try:
        initialize_robot()
        perform_task()
    except KeyboardInterrupt:
        print("\nShutdown...")
    finally:
        rclpy.shutdown()

if __name__ == "__main__":
    main()
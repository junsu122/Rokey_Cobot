import rclpy
import DR_init
import sys

# 로봇 설정 상수
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA"

# DR_init 설정 (임포트 직후에 수행)
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

def perform_task():
    # 여기서 필요한 함수들을 로컬 임포트합니다.
    from DSR_ROBOT2 import (
        task_compliance_ctrl, set_desired_force, move_periodic,
        release_force, release_compliance_ctrl, DR_FC_MOD_REL, DR_TOOL
    )
    
    print("Starting Task...")
    task_compliance_ctrl(stx=[3000, 3000, 100, 100, 100, 100])
    
    fd = [0, 0, -20, 0, 0, 0]
    fctrl_dir= [0, 0, 1, 0, 0, 0]
    set_desired_force(fd, dir=fctrl_dir, mod=DR_FC_MOD_REL) 
    
    move_periodic(amp =[0,0,20,0,0,60], period=2, atime=1, repeat=2, ref=DR_TOOL)
    
    release_force()
    release_compliance_ctrl()
    print("Task Completed.")

def main(args=None):
    rclpy.init(args=args)
    
    # 1. 노드 생성
    node = rclpy.create_node("move_periodic_node", namespace=ROBOT_ID)
    
    # 2. DR_init에 노드 전달 (가장 중요!)
    DR_init.__dsr__node = node

    try:
        # 3. 노드 설정 후 라이브러리 함수 임포트 및 사용
        from DSR_ROBOT2 import set_tool, set_tcp
        
        print("Initializing Robot...")
        set_tool(ROBOT_TOOL)
        set_tcp(ROBOT_TCP)

        # 작업 수행
        perform_task()

    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
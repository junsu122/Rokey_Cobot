#!/usr/bin/env python3
"""
flower_robot_main.py  ─  최종 완성본 v2
────────────────────────────────────────────────────────────────
M0609 꽃 삽입 로봇 + 실시간 모니터링 + 안전정지 + 비상정지

[개선 사항]
  1. 부분 재개: 완료한 꽃은 건너뛰고 다음 꽃부터 시작
  2. 안전정지 로직 개선: 지속적 외력일 때만 비상정지로 격상
     - 순간 충격(일시적 외력) → 안전정지 → 해소 → 재개
     - 지속적 외력(80% 이상) → 안전정지 → 비상정지 격상

실행: python3 flower_robot_main.py
"""

import rclpy
from rclpy.node import Node
import DR_init
import time
import threading
import math
import json
import copy
from dataclasses import dataclass, field
from typing import List

from std_msgs.msg import Float64MultiArray, String
from sensor_msgs.msg import JointState


# ══════════════════════════════════════════════════════
# ROBOT CONFIG
# ══════════════════════════════════════════════════════
ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL  = "Tool Weight"
ROBOT_TCP   = "GripperDA_v1"

HOME_V_J = 450;  HOME_ACC_J  = 300
CATCH_V_J = 450; CATCH_ACC_J = 300
VELOCITY_L = 400; ACC_L      = 300
INSERT_V_L = 600; INSERT_A_L = 500
TARGET_V_L = 350; TARGET_A_L = 200

DR_init.__dsr__id    = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

HOME_JReady               = [19.20, -6.90, 86.79,  0.07, 100.94, 13.81]
flower_initial_position_J = [40.25,  27.42, 63.42, 87.97, -40.38,  0.53]
WAYPOINT_J                = [24.10,  21.51, 77.77,  3.33,  81.80, 23.66]

# 안전 임계값
SAFETY_FORCE_N       = 10.0   # 안전정지 (실물 기준)
ESTOP_FORCE_N        = 100.0   # 비상정지
SAFETY_STOP_WAIT_SEC = 5.0    # 안전정지 후 재개 대기
ESTOP_RECOVERY_WAIT_SEC = 10.0  # E-STOP 후 복구 대기


# ══════════════════════════════════════════════════════
# FSM 상태
# ══════════════════════════════════════════════════════
STATE_IDLE        = "IDLE"
STATE_BASIC       = "BASIC"
STATE_PAUSED      = "PAUSED"
STATE_REPROCESS   = "REPROCESS"
STATE_SAFETY_STOP = "SAFETY_STOP"
STATE_ESTOP       = "ESTOP"

# 로봇 상태 코드
ROBOT_STATE_MAP = {
    0:"INITIALIZING", 1:"STANDBY", 2:"MOVING", 3:"SAFE_OFF",
    4:"TEACHING", 5:"SAFE_STOP", 6:"EMERGENCY_STOP",
    7:"HOMMING", 8:"RECOVERY", 9:"SAFE_STOP2", 10:"SAFE_OFF2", 15:"NOT_READY"
}
ROBOT_STATE_STANDBY   = 1
ROBOT_STATE_SAFE_OFF  = 3
ROBOT_STATE_SAFE_STOP = 5
CONTROL_RESET_SAFE_STOP = 2
CONTROL_RESET_SAFE_OFF  = 3


# ══════════════════════════════════════════════════════
# 전역 플래그
# ══════════════════════════════════════════════════════
current_state          = STATE_IDLE
pause_signal           = False
cancel_signal_received = False
basic_process          = True
re_process             = False
new_param_received     = False
posx_dic               = {}

_safety_stop_event = threading.Event()
_estop_event       = threading.Event()
_estop_start_time  = 0.0


# ══════════════════════════════════════════════════════
# DSR 함수 전역 참조
# ══════════════════════════════════════════════════════
_f = {}


def _load_dsr():
    import DSR_ROBOT2 as m
    _f['posx']               = m.posx
    _f['movej']              = m.movej
    _f['movel']              = m.movel
    _f['set_tool']           = m.set_tool
    _f['set_tcp']            = m.set_tcp
    _f['set_robot_mode']     = m.set_robot_mode
    _f['set_ref_coord']      = m.set_ref_coord
    _f['set_digital_output'] = m.set_digital_output
    _f['get_tool_force']     = m.get_tool_force
    _f['get_robot_state']    = m.get_robot_state
    _f['get_last_alarm']     = m.get_last_alarm
    _f['drl_script_stop']    = m.drl_script_stop
    _f['wait']               = m.wait
    _f['OFF']                = m.OFF
    _f['ON']                 = m.ON
    _f['ROBOT_MODE_AUTONOMOUS'] = m.ROBOT_MODE_AUTONOMOUS
    _f['ROBOT_MODE_MANUAL']     = m.ROBOT_MODE_MANUAL
    _f['DR_QSTOP_STO']          = m.DR_QSTOP_STO


# ══════════════════════════════════════════════════════
# 모니터링 공유 상태
# ══════════════════════════════════════════════════════

@dataclass
class MonitorState:
    fsm_state:         str       = "IDLE"
    current_flower:    int       = 0
    total_flowers:     int       = 0
    flower_step:       str       = ""
    flower_step_start: float     = 0.0
    completed_flowers: List[int] = field(default_factory=list)
    received_coords:   List[List[float]] = field(default_factory=list)
    gripper_open:      bool      = True
    joint_pos:  List[float] = field(default_factory=lambda: [0.0]*6)
    joint_vel:  List[float] = field(default_factory=lambda: [0.0]*6)
    tool_force: List[float] = field(default_factory=lambda: [0.0]*6)
    force_mag:  float       = 0.0
    safety_level: int       = 0
    event_log: List[str]    = field(default_factory=list)

    def log(self, msg: str, level: str = "info"):
        icons = {"info":"ℹ","warn":"⚠","error":"✖","ok":"✔","move":"→"}
        self.event_log.insert(0,
            f"[{time.strftime('%H:%M:%S')}] {icons.get(level,'·')} {msg}")
        if len(self.event_log) > 60:
            self.event_log.pop()

    def to_json(self) -> str:
        return json.dumps({
            "fsm_state":         self.fsm_state,
            "current_flower":    self.current_flower,
            "total_flowers":     self.total_flowers,
            "flower_step":       self.flower_step,
            "flower_step_start": self.flower_step_start,
            "completed_flowers": self.completed_flowers,
            "received_coords":   self.received_coords,
            "gripper_open":      self.gripper_open,
            "joint_pos":         self.joint_pos,
            "joint_vel":         self.joint_vel,
            "tool_force":        self.tool_force,
            "force_mag":         self.force_mag,
            "safety_level":      self.safety_level,
            "event_log":         self.event_log[:30],
            "stamp":             time.time(),
        })


_state      = MonitorState()
_state_lock = threading.Lock()


def _set_phase(fsm, msg="", level="info"):
    with _state_lock:
        _state.fsm_state = fsm
        if msg: _state.log(msg, level)

def _set_step(step):
    labels = {
        "MOVE_INIT":"① 초기위치","GRIP":"② 파지","WAYPOINT":"③ 경유점",
        "APPROACH":"④ 접근","INSERT":"⑤ 삽입","RELEASE":"⑥ 개방","EXIT":"⑦ 이탈",
    }
    with _state_lock:
        _state.flower_step = step
        _state.flower_step_start = time.time()
        _state.log(f"  [{_state.current_flower}/{_state.total_flowers}] {labels.get(step,step)}", "move")

def _set_flower(idx, total):
    with _state_lock:
        _state.current_flower = idx
        _state.total_flowers  = total
        _state.flower_step    = "START"
        _state.flower_step_start = time.time()
        _state.log(f"🌸 {idx}/{total}번 꽃 작업 시작", "move")

def _complete_flower(idx):
    with _state_lock:
        if idx not in _state.completed_flowers:
            _state.completed_flowers.append(idx)
        _state.flower_step = "DONE"
        _state.log(f"✔ {idx}번 꽃 완료", "ok")

def _set_gripper(is_open):
    with _state_lock:
        _state.gripper_open = is_open
        _state.log("그리퍼 열림" if is_open else "그리퍼 닫힘", "info")


# ══════════════════════════════════════════════════════
# 모니터링 전용 노드
# ══════════════════════════════════════════════════════

class MonitorNode(Node):
    def __init__(self):
        super().__init__("flower_robot_monitor", namespace=ROBOT_ID)
        self.create_subscription(JointState, f"/{ROBOT_ID}/joint_states", self._joint_cb, 10)
        self._pub = self.create_publisher(String, "robot_state", 10)
        self.create_timer(0.1, self._publish_state)
        self.get_logger().info("📊 모니터링 노드 시작")

    def _joint_cb(self, msg):
        try:
            n2i   = {n:i for i,n in enumerate(msg.name)}
            order = ["joint_1","joint_2","joint_3","joint_4","joint_5","joint_6"]
            pos   = [math.degrees(msg.position[n2i[n]]) if n in n2i else 0.0 for n in order]
            vel   = [msg.velocity[n2i[n]] if n in n2i and msg.velocity else 0.0 for n in order]
            with _state_lock:
                _state.joint_pos = pos
                _state.joint_vel = vel
        except Exception:
            pass

    def _publish_state(self):
        with _state_lock:
            snap = copy.deepcopy(_state)
        msg      = String()
        msg.data = snap.to_json()
        self._pub.publish(msg)


def _monitor_spin_thread(monitor_node):
    from rclpy.executors import SingleThreadedExecutor
    executor = SingleThreadedExecutor()
    executor.add_node(monitor_node)
    try:
        executor.spin()
    except Exception:
        pass
    finally:
        executor.shutdown()


# ══════════════════════════════════════════════════════
# Thread-3: E-STOP 감시
# ══════════════════════════════════════════════════════

def _estop_thread():
    while True:
        _estop_event.wait()
        try:
            _f['drl_script_stop'](_f['DR_QSTOP_STO'])
            DR_init.__dsr__node.get_logger().error("🛑 drl_script_stop 호출")
        except Exception as e:
            DR_init.__dsr__node.get_logger().error(f"E-STOP 오류: {e}")
        with _state_lock:
            _state.fsm_state    = STATE_ESTOP
            _state.safety_level = 2
            _state.log("🛑 비상정지 실행", "error")
        time.sleep(0.05)


# ══════════════════════════════════════════════════════
# 외력 체크
# ══════════════════════════════════════════════════════

def _check_force():
    try:
        tf = _f['get_tool_force']()
        fm = math.sqrt(sum(v**2 for v in tf[:3]))
        with _state_lock:
            _state.tool_force = list(tf)
            _state.force_mag  = fm
            if fm > ESTOP_FORCE_N:
                if not _estop_event.is_set():
                    _state.log(f"🛑 외력 비상정지: {fm:.1f}N", "error")
                    _state.safety_level = 2
                _estop_event.set()
            elif fm > SAFETY_FORCE_N:
                if not _safety_stop_event.is_set():
                    _state.log(f"⚠ 외력 안전정지: {fm:.1f}N", "warn")
                    _state.safety_level = 1
                _safety_stop_event.set()
            else:
                if not _estop_event.is_set():
                    _state.safety_level = 0
    except Exception:
        pass


# ══════════════════════════════════════════════════════
# SetRobotControl 서비스 호출 (복구용)
# ══════════════════════════════════════════════════════

def _call_set_robot_control(control_value: int) -> bool:
    from dsr_msgs2.srv import SetRobotControl
    node     = DR_init.__dsr__node
    srv_name = f'/{ROBOT_ID}/system/set_robot_control'
    cli      = node.create_client(SetRobotControl, srv_name)

    if not cli.wait_for_service(timeout_sec=2.0):
        node.get_logger().error(f"서비스 미응답: {srv_name}")
        return False

    req               = SetRobotControl.Request()
    req.robot_control = control_value
    future            = cli.call_async(req)

    deadline = time.time() + 5.0
    while not future.done():
        rclpy.spin_once(node, timeout_sec=0.05)
        if time.time() > deadline:
            return False
    try:
        return future.result().success
    except Exception:
        return False


# ══════════════════════════════════════════════════════
# CALLBACK
# ══════════════════════════════════════════════════════

def param_callback(msg):
    global new_param_received, posx_dic, cancel_signal_received, pause_signal
    node = DR_init.__dsr__node
    data = list(msg.data)

    if len(data) == 6 and all(v == 0.0 for v in data):
        cancel_signal_received = True
        with _state_lock: _state.log("🚨 취소 신호 수신", "warn")
        node.get_logger().warn("🚨 취소 신호 감지!")
        return

    if len(data) == 6 and all(v == 1.0 for v in data):
        pause_signal = True
        with _state_lock:
            _state.fsm_state = STATE_PAUSED
            _state.log("⏸ 일시정지 신호 수신", "warn")
        node.get_logger().warn("⏸️ 일시정지 신호 감지!")
        return

    if len(data) == 6 and all(v == 2.0 for v in data):
        if pause_signal:
            pause_signal = False
            with _state_lock:
                _state.fsm_state = STATE_BASIC
                _state.log("▶️ 재개 신호 수신", "ok")
            node.get_logger().info("▶️ 재개 신호 감지!")
        return

    if len(data) == 6 and all(v == 3.0 for v in data):
        _estop_event.set()
        with _state_lock: _state.log("🛑 E-STOP 신호 수신", "error")
        node.get_logger().error("🛑 E-STOP 신호 감지!")
        return

    if len(data) % 6 != 0:
        node.get_logger().error("❌ 잘못된 좌표 형식")
        return

    if _estop_event.is_set():
        node.get_logger().warn("⚠ E-STOP 상태: 좌표 무시")
        return

    posx_dic.clear()
    num = len(data) // 6
    for i in range(num):
        posx_dic[i] = list(data[i*6:(i+1)*6])

    new_param_received     = True
    cancel_signal_received = False
    pause_signal           = False
    _safety_stop_event.clear()

    with _state_lock:
        _state.received_coords   = [list(data[i*6:(i+1)*6]) for i in range(num)]
        _state.total_flowers     = num
        _state.completed_flowers = []
        _state.log(f"📥 {num}개 좌표 수신", "ok")
    node.get_logger().info(f"📥 {num}개 좌표 수신")


# ══════════════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════════════

def initialize_robot():
    _f['set_robot_mode'](_f['ROBOT_MODE_MANUAL'])
    _f['set_tool'](ROBOT_TOOL)
    _f['set_tcp'](ROBOT_TCP)
    _f['set_robot_mode'](_f['ROBOT_MODE_AUTONOMOUS'])
    with _state_lock: _state.log("🤖 로봇 초기화 완료", "ok")
    DR_init.__dsr__node.get_logger().info("🤖 로봇 초기화 완료")
    time.sleep(2)


# ══════════════════════════════════════════════════════
# E-STOP 복구
# ══════════════════════════════════════════════════════

def _try_recover_from_estop() -> bool:
    node = DR_init.__dsr__node
    try:
        state      = _f['get_robot_state']()
        state_desc = ROBOT_STATE_MAP.get(state, "UNKNOWN")
        node.get_logger().warn(f"🔧 복구 시작 - 현재 상태: [{state}] {state_desc}")
        _set_phase(STATE_ESTOP, f"🔧 복구 중: {state_desc}", "warn")
    except Exception as e:
        node.get_logger().error(f"상태 조회 실패: {e}")
        return False

    if state == ROBOT_STATE_STANDBY:
        initialize_robot()
        return True

    elif state in (ROBOT_STATE_SAFE_STOP, 9):
        _f['drl_script_stop'](_f['DR_QSTOP_STO'])
        time.sleep(3.0)
        if _call_set_robot_control(CONTROL_RESET_SAFE_STOP):
            time.sleep(2.0)
            if _f['get_robot_state']() == ROBOT_STATE_STANDBY:
                node.get_logger().info("✅ 복구 성공")
                initialize_robot()
                return True

    elif state in (ROBOT_STATE_SAFE_OFF, 10):
        _f['drl_script_stop'](_f['DR_QSTOP_STO'])
        time.sleep(0.5)
        if _call_set_robot_control(CONTROL_RESET_SAFE_OFF):
            time.sleep(3.0)
            if _f['get_robot_state']() == ROBOT_STATE_STANDBY:
                node.get_logger().info("✅ 복구 성공")
                initialize_robot()
                return True

    node.get_logger().warn("⚠ 복구 실패")
    return False


# ══════════════════════════════════════════════════════
# TASK EXECUTION
# ══════════════════════════════════════════════════════

def perform_task():
    global new_param_received, cancel_signal_received
    global basic_process, re_process, pause_signal, current_state
    global _estop_start_time

    node = DR_init.__dsr__node

    def gripper_open():
        _f['set_digital_output'](1, _f['OFF'])
        _f['set_digital_output'](2, _f['ON'])
        _f['wait'](0.3)
        _set_gripper(True)

    def gripper_close():
        _f['set_digital_output'](1, _f['ON'])
        _f['set_digital_output'](2, _f['OFF'])
        _f['wait'](0.3)
        _set_gripper(False)

    def wait_for_pause() -> bool:
        """
        True  → 루프 break
        False → 정상 계속
        """
        if _estop_event.is_set():
            return True

        if _safety_stop_event.is_set():
            node.get_logger().warn(
                f"⚠ 안전정지! {SAFETY_STOP_WAIT_SEC:.0f}초 대기 중..."
            )
            _set_phase(STATE_SAFETY_STOP,
                       f"⚠ 안전정지 → {SAFETY_STOP_WAIT_SEC:.0f}초 대기", "warn")

            deadline  = time.time() + SAFETY_STOP_WAIT_SEC
            resolved  = False
            
            # ─────────────────────────────────────────────────────
            # 개선: 5초 동안 외력 모니터링
            # - 외력 해소되면 즉시 복구
            # - 5초 동안 계속 높으면 비상정지 격상
            # ─────────────────────────────────────────────────────
            high_force_count = 0
            check_count = 0
            
            while time.time() < deadline:
                if _estop_event.is_set():
                    return True
                
                rclpy.spin_once(node, timeout_sec=0.1)
                
                with _state_lock:
                    fm = _state.force_mag
                
                check_count += 1
                
                # 외력 해소 확인
                if fm < SAFETY_FORCE_N:
                    node.get_logger().info(f"✅ 외력 해소 ({fm:.2f}N) → 재개 준비")
                    resolved = True
                    break
                else:
                    high_force_count += 1
                
                remaining = int(deadline - time.time()) + 1
                with _state_lock:
                    _state.fsm_state = f"SAFETY_STOP ({remaining}s, {fm:.1f}N)"

            # ─────────────────────────────────────────────────────
            # 판단: 5초 중 80% 이상 외력이 지속되면 비상정지
            # ─────────────────────────────────────────────────────
            if resolved:
                # 외력 해소 → 로봇 상태 확인 후 복구
                try:
                    state = _f['get_robot_state']()
                    state_desc = ROBOT_STATE_MAP.get(state, "UNKNOWN")
                    node.get_logger().info(f"   로봇 상태: [{state}] {state_desc}")

                    if state == ROBOT_STATE_SAFE_STOP:
                        node.get_logger().warn("   SAFE_STOP → SetRobotControl(2)")
                        if _call_set_robot_control(CONTROL_RESET_SAFE_STOP):
                            time.sleep(1.0)
                            initialize_robot()
                        else:
                            node.get_logger().error("   해제 실패 → 홈 복귀")
                            _safety_stop_event.clear()
                            return True

                    elif state == ROBOT_STATE_SAFE_OFF:
                        node.get_logger().warn("   SAFE_OFF → SetRobotControl(3)")
                        if _call_set_robot_control(CONTROL_RESET_SAFE_OFF):
                            time.sleep(2.0)
                            initialize_robot()
                        else:
                            node.get_logger().error("   서보 ON 실패 → 홈 복귀")
                            _safety_stop_event.clear()
                            return True

                    elif state == ROBOT_STATE_STANDBY:
                        node.get_logger().info("   STANDBY → 바로 재개")

                except Exception as e:
                    node.get_logger().error(f"   상태 확인 오류: {e}")

                _safety_stop_event.clear()
                with _state_lock:
                    _state.safety_level = 0
                _set_phase(STATE_BASIC, "✅ 안전정지 해제 → 재개", "ok")
                node.get_logger().info("✅ 작업 재개")
                return False

            else:
                # 5초 후에도 외력 지속
                with _state_lock: 
                    fm = _state.force_mag
                
                force_persistence = high_force_count / max(check_count, 1)
                
                # 80% 이상 지속적으로 외력이 높았다면 비상정지
                if force_persistence > 0.8:
                    node.get_logger().error(
                        f"🛑 외력 지속 ({fm:.1f}N, {force_persistence*100:.0f}%) → 비상정지 격상"
                    )
                    _estop_event.set()
                    return True
                else:
                    # 간헐적 외력 → 안전정지 해제하고 재개
                    node.get_logger().warn(
                        f"⚠ 간헐적 외력 감지 ({force_persistence*100:.0f}%) → 재개 시도"
                    )
                    _safety_stop_event.clear()
                    with _state_lock:
                        _state.safety_level = 0
                    _set_phase(STATE_BASIC, "⚠ 안전정지 해제 → 재개", "warn")
                    return False

        if pause_signal:
            node.get_logger().warn("⏸️ 일시정지 중... Play 신호를 기다립니다.")
            _set_phase(STATE_PAUSED, "⏸ 재개 신호 대기", "warn")
            while pause_signal:
                if _estop_event.is_set():
                    return True
                rclpy.spin_once(node, timeout_sec=0.1)
                _f['wait'](0.1)
            _set_phase(STATE_BASIC, "▶️ 재개", "ok")

        return False

    _set_phase(STATE_IDLE, "📡 좌표 대기 중...", "info")
    node.get_logger().info("📡 퍼블리셔로부터 좌표 대기 중...")

    # ─────────────────────────────────────────────────
    # 복구 시 재개할 상태 저장 변수 추가
    # ─────────────────────────────────────────────────
    state_before_estop = STATE_IDLE

    while rclpy.ok():

        # ── E-STOP 처리 (10초 후 자동 복구) ────────────
        if _estop_event.is_set():
            if _estop_start_time == 0.0:
                _estop_start_time = time.time()
                # E-STOP 발생 시점의 상태 저장
                state_before_estop = current_state
                node.get_logger().warn(
                    f"🛑 E-STOP (현재: {current_state}) → {ESTOP_RECOVERY_WAIT_SEC:.0f}초 후 자동 복구"
                )
            
            elapsed   = time.time() - _estop_start_time
            remaining = ESTOP_RECOVERY_WAIT_SEC - elapsed
            if remaining > 0:
                with _state_lock:
                    _state.fsm_state = f"ESTOP ({int(remaining)+1}s)"
                rclpy.spin_once(node, timeout_sec=0.1)
                continue

            _estop_event.clear()
            if _try_recover_from_estop():
                _estop_start_time = 0.0
                _safety_stop_event.clear()
                with _state_lock: 
                    _state.safety_level = 0
                
                # ────────────────────────────────────────
                # 핵심 수정: 복구 후 원래 상태로 복귀
                # ────────────────────────────────────────
                if state_before_estop == STATE_BASIC and posx_dic:
                    # 작업 중이었다면 STATE_REPROCESS로 → 홈 복귀 후 재시작
                    current_state = STATE_REPROCESS
                    _set_phase(STATE_REPROCESS, "✅ E-STOP 복구 → 홈 복귀 후 재시작", "ok")
                    node.get_logger().info("✅ E-STOP 복구 완료 → 작업 재시작 준비")
                else:
                    # 대기 중이었다면 IDLE로
                    current_state = STATE_IDLE
                    cancel_signal_received = False
                    _set_phase(STATE_IDLE, "✅ E-STOP 복구 완료 → 대기", "ok")
            else:
                _estop_start_time = time.time()
                _estop_event.set()
                with _state_lock: 
                    _state.log("⚠ 복구 실패 → 10초 후 재시도", "warn")
            continue

        # ── STATE_IDLE ──────────────────────────────────
        if current_state == STATE_IDLE:
            if new_param_received:
                new_param_received = False
                current_state      = STATE_BASIC
                _set_phase(STATE_BASIC, "▶️ 일반 공정 시작", "ok")
            else:
                rclpy.spin_once(node, timeout_sec=0.1)
                continue

        # ── STATE_BASIC ─────────────────────────────────
        elif current_state == STATE_BASIC:
            node.get_logger().info("▶️ 일반 공정 시작")

            _f['set_ref_coord'](107)

            target_pos_dic    = {}
            target_up_pos_dic  = {}
            target_up_pos_dic1 = {}
            target_up_pos_dic3 = {}
            for i in sorted(posx_dic.keys()):
                target_pos_dic[i]     = _f['posx'](posx_dic[i])
                up  = posx_dic[i].copy(); up[1]  += 30
                target_up_pos_dic[i]  = _f['posx'](up)
                up1 = posx_dic[i].copy(); up1[1] += 40; up1[0] -= 70
                target_up_pos_dic3[i] = _f['posx'](up1)
                ep  = posx_dic[i].copy(); ep[2]  += 60
                target_up_pos_dic1[i] = _f['posx'](ep)

            _f['movej'](HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
            gripper_open()

            total = len(target_pos_dic)
            with _state_lock:
                _state.total_flowers = total

            for i in sorted(target_pos_dic.keys()):
                # ─────────────────────────────────────────────────────
                # 부분 재개: 이미 완료한 꽃은 건너뛰기
                # ─────────────────────────────────────────────────────
                with _state_lock:
                    if (i + 1) in _state.completed_flowers:
                        node.get_logger().info(f"⏭ {i+1}번 꽃 이미 완료 → 건너뛰기")
                        continue
                
                if wait_for_pause(): break
                if cancel_signal_received: break

                _set_flower(i + 1, total)
                node.get_logger().info(f"🌸 {i+1}번 꽃 작업")

                _set_step("MOVE_INIT")
                _f['movej'](flower_initial_position_J, vel=CATCH_V_J, acc=CATCH_ACC_J)
                _check_force()
                if wait_for_pause(): break

                _set_step("GRIP")
                gripper_close()
                if wait_for_pause(): break

                _set_step("WAYPOINT")
                _f['movej'](WAYPOINT_J, vel=HOME_V_J, acc=HOME_ACC_J)
                _check_force()
                if wait_for_pause(): break

                _set_step("APPROACH")
                _f['movel'](target_up_pos_dic3[i], vel=TARGET_V_L, acc=TARGET_A_L)
                _check_force()
                if wait_for_pause(): break
                _f['movel'](target_up_pos_dic[i],  vel=TARGET_V_L, acc=TARGET_A_L)
                _check_force()
                if wait_for_pause(): break

                _set_step("INSERT")
                _f['movel'](target_pos_dic[i], vel=INSERT_V_L, acc=INSERT_A_L)
                _check_force()
                if wait_for_pause(): break

                _set_step("RELEASE")
                gripper_open()
                if wait_for_pause(): break

                _set_step("EXIT")
                _f['movel'](target_up_pos_dic1[i], vel=VELOCITY_L, acc=ACC_L)
                _check_force()
                if wait_for_pause(): break

                _complete_flower(i + 1)

            if _estop_event.is_set():
                pass
            elif cancel_signal_received or _safety_stop_event.is_set():
                current_state = STATE_REPROCESS
                _set_phase(STATE_REPROCESS, "🔄 취소/안전정지 → 재공정", "warn")
            else:
                _f['movej'](HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
                current_state = STATE_IDLE
                _set_phase(STATE_IDLE, f"✅ {total}개 완료 → 대기", "ok")

        # ── STATE_REPROCESS ─────────────────────────────
        elif current_state == STATE_REPROCESS:
            node.get_logger().warn("🔄 재공정: 홈 복귀")
            gripper_open()
            _f['movej'](HOME_JReady, vel=HOME_V_J, acc=HOME_ACC_J)
            
            # ────────────────────────────────────────────
            # 핵심 수정: 좌표가 남아있으면 재시작
            # ────────────────────────────────────────────
            if posx_dic and not cancel_signal_received:
                # 좌표 존재 → 작업 재시작 (완료된 꽃은 건너뛰기)
                _safety_stop_event.clear()
                current_state = STATE_BASIC
                with _state_lock: 
                    _state.safety_level = 0
                    # 완료 기록 유지 (부분 재개)
                _set_phase(STATE_BASIC, "🔄 홈 복귀 완료 → 작업 재시작", "ok")
                node.get_logger().info("🔄 작업 재시작 (완료된 꽃은 건너뛰기)")
            else:
                # 좌표 없음 or 취소됨 → 대기
                cancel_signal_received = False
                _safety_stop_event.clear()
                current_state = STATE_IDLE
                with _state_lock: 
                    _state.safety_level = 0
                _set_phase(STATE_IDLE, "🔙 홈 복귀 완료 → 대기", "info")
                node.get_logger().info("🔙 홈으로 복귀 → 대기")


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

def main(args=None):
    rclpy.init(args=args)

    # DSR 전용 노드 (g_node)
    node = rclpy.create_node("flower_robot_main", namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    node.create_subscription(Float64MultiArray, "new_parameter", param_callback, 10)

    # STEP 1: DSR_ROBOT2 단 한 번만 import
    print("[INFO] DSR_ROBOT2 로딩 중...")
    try:
        _load_dsr()
        print("[INFO] DSR_ROBOT2 로딩 완료")
    except Exception as e:
        print(f"[ERROR] DSR_ROBOT2 로딩 실패: {e}")
        rclpy.shutdown()
        return

    # STEP 2: 로봇 초기화
    try:
        initialize_robot()
    except Exception as e:
        print(f"[ERROR] 초기화 실패: {e}")
        rclpy.shutdown()
        return

    # STEP 3: 모니터링 노드 생성 + 스레드 시작
    monitor_node = MonitorNode()

    threading.Thread(
        target=_monitor_spin_thread, args=(monitor_node,),
        daemon=True, name="Thread-2_Monitor"
    ).start()

    threading.Thread(
        target=_estop_thread,
        daemon=True, name="Thread-3_EStop"
    ).start()

    # STEP 4: FSM 루프
    try:
        perform_task()
    except KeyboardInterrupt:
        node.get_logger().warn("사용자에 의해 중단됨")
    finally:
        monitor_node.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
monitor_node.py
────────────────────────────────────────────────────────────────
Doosan M0609 Flower Robot 실시간 TUI 모니터링 노드

[구독 토픽]
  /dsr01/robot_monitor_status  (std_msgs/String / JSON)
  → flower.py 의 hw_monitor_thread 가 300ms 주기로 발행

[발행 토픽]
  /dsr01/recovery_command  (std_msgs/String)
  → TUI [R] 복구 버튼 클릭 시 "RECOVER" 발행
    flower.py 가 수신하면 복구 절차 시작

[Firestore 기록]
  꽃 1개 완료될 때마다  → pixel_coords/job_status  (per_flower 배열 갱신)
  전체 작업 완료 시      → pixel_coords/job_status  (status = "all_done")

[키바인딩]
  Q : 종료
  R : 복구 명령 전송 (안전정지/비상정지 대기 중일 때만 활성)
  P : TUI 일시정지/재개

실행:    python3 monitor_node.py
의존성:  pip install textual firebase-admin
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import threading
import time
import json
import copy

import firebase_admin
from firebase_admin import credentials, firestore as fs_admin
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


# ══════════════════════════════════════════════════════
# Firebase 초기화 (parameter_publisher.py 와 공존 가능)
# ══════════════════════════════════════════════════════

SERVICE_ACCOUNT_PATH = "/home/ludix/test_23/serviceAccountKey.json"

if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

db = fs_admin.client()

# Firestore 기록 대상 — parameter_publisher.py 와 같은 컬렉션 사용
FS_COLLECTION = "pixel_coords"
FS_DOC_ID     = "job_status"


# ══════════════════════════════════════════════════════
# Firestore 헬퍼
# ══════════════════════════════════════════════════════

class FirestoreLogger:
    """
    꽃 완료 / 전체 완료를 Firestore 에 기록.
    모든 쓰기는 데몬 스레드에서 비동기 실행 → ROS2/TUI 블로킹 없음.
    """

    def _run(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def record_job_start(self):
        """노드 시작 시 job_status 문서를 완전히 초기화 (이전 데이터 덮어씀)"""
        def _write():
            try:
                ref = db.collection(FS_COLLECTION).document(FS_DOC_ID)
                ref.set(
                    {
                        "status":           "waiting",
                        "done":             0,
                        "total":            0,
                        "last_flower_done": 0,
                        "completed_at":     "",
                        "updated_at":       SERVER_TIMESTAMP,
                        "per_flower":       [],   # ← 배열 완전 초기화
                    }
                    # merge=True 없음 → 문서 전체를 새로 덮어씀
                )
            except Exception as e:
                print(f"[Firestore] job_start 초기화 실패: {e}")

        self._run(_write)

    def record_job_cancelled(self):
        """취소 신호 수신 시 job_status 문서를 cancelled 상태로 초기화"""
        def _write():
            try:
                ref = db.collection(FS_COLLECTION).document(FS_DOC_ID)
                ref.set(
                    {
                        "status":           "cancelled",
                        "done":             0,
                        "total":            0,
                        "last_flower_done": 0,
                        "completed_at":     "",
                        "cancelled_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "updated_at":       SERVER_TIMESTAMP,
                        "per_flower":       [],
                    }
                    # merge=True 없음 → 문서 전체를 새로 덮어씀
                )
            except Exception as e:
                print(f"[Firestore] job_cancelled 초기화 실패: {e}")

        self._run(_write)

    def record_flower_done(self, flower_idx: int, done: int, total: int):
        """꽃 1개 완료 → pixel_coords/job_status (per_flower 배열에 항목 추가)"""
        def _write():
            try:
                ref = db.collection(FS_COLLECTION).document(FS_DOC_ID)
                ref.set(
                    {
                        "last_flower_done": flower_idx,
                        "done":             done,
                        "total":            total,
                        "status":           "in_progress",
                        "updated_at":       SERVER_TIMESTAMP,
                        "per_flower": fs_admin.ArrayUnion([
                            {
                                "flower_index": flower_idx,
                                "done_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                        ]),
                    },
                    merge=True,  # 기존 필드 유지, 문서 없으면 신규 생성
                )
            except Exception as e:
                print(f"[Firestore] flower_done 쓰기 실패 (idx={flower_idx}): {e}")

        self._run(_write)

    def record_job_complete(self, total: int):
        """전체 완료 → pixel_coords/job_status (status = 'all_done')"""
        def _write():
            try:
                ref = db.collection(FS_COLLECTION).document(FS_DOC_ID)
                ref.set(
                    {
                        "done":         total,
                        "total":        total,
                        "status":       "all_done",
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "updated_at":   SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
            except Exception as e:
                print(f"[Firestore] job_complete 쓰기 실패: {e}")

        self._run(_write)


# 싱글턴
fs_logger = FirestoreLogger()


# ══════════════════════════════════════════════════════
# 수신 상태 파싱
# ══════════════════════════════════════════════════════

class RobotSnapshot:

    HW_MAP = {
        1: ("STANDBY",   "정상 대기 중",              "green"),
        2: ("MOVING",    "이동 명령 실행 중",          "cyan"),
        3: ("SAFE_OFF",  "서보 꺼짐 — 복구 필요",     "red"),
        5: ("PROT_STOP", "보호 정지 — 원인 해소 필요", "yellow"),
        6: ("EMRG_STOP", "비상정지 — 버튼 해제 필요",  "red"),
    }

    FSM_COLOR = {
        "IDLE":      "bright_black",
        "BASIC":     "bright_green",
        "PAUSED":    "bright_blue",
        "REPROCESS": "bright_yellow",
    }

    def __init__(self, d: dict):
        self.fsm_state        = d.get("fsm",              "IDLE")
        self.hw_code          = int(d.get("hw_code",       1))
        self.cur_flower       = int(d.get("cur_flower",    0))
        self.done             = int(d.get("done",          0))
        self.total            = int(d.get("total",         0))
        self.resume_idx       = int(d.get("resume_idx",    0))
        self.countdown        = int(d.get("countdown",     0))
        self.stamp            = d.get("stamp",             time.time())
        self.waiting_recovery = bool(d.get("waiting_recovery", False))

    @property
    def connected(self):
        return (time.time() - self.stamp) < 8.0

    @property
    def hw_label(self):  return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[0]
    @property
    def hw_detail(self): return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[1]
    @property
    def hw_color(self):  return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[2]
    @property
    def fsm_color(self): return self.FSM_COLOR.get(self.fsm_state, "white")


# ══════════════════════════════════════════════════════
# ROS2 모니터링 노드
# ══════════════════════════════════════════════════════

class MonitorNode(Node):
    def __init__(self):
        super().__init__("flower_monitor_node")
        self._lock     = threading.Lock()
        self._snapshot = RobotSnapshot({})
        self._logs     = []

        # Firestore 중복 기록 방지
        self._last_done:         int  = 0
        self._job_complete_sent: bool = False

        self.create_subscription(
            String,
            "/dsr01/robot_monitor_status",
            self._cb,
            10,
        )

        # 취소 신호 구독 → Firestore job_status 초기화
        self.create_subscription(
            String,
            "/dsr01/cancel_signal",
            self._cb_cancel,
            10,
        )

        self._recovery_pub = self.create_publisher(
            String, "/dsr01/recovery_command", 10
        )

        # 노드 시작 시 Firestore 초기화 (이전 작업 데이터 리셋)
        fs_logger.record_job_start()

        self._add_log("INFO", "monitor_node 시작")
        self._add_log("INFO", "Firestore job_status 초기화 완료")
        self._add_log("INFO", "/dsr01/robot_monitor_status 구독 대기 중...")

    # ── ROS2 콜백 ────────────────────────────────────

    def _cb(self, msg: String):
        try:
            d = json.loads(msg.data)
            d["stamp"] = time.time()
            snap    = RobotSnapshot(d)
            log_msg = d.get("log", "")

            with self._lock:
                self._snapshot = snap
                if log_msg:
                    self._add_log(d.get("log_level", "INFO"), log_msg)

            # Firestore 기록 (락 바깥 — 비동기이므로 OK)
            self._maybe_record_firestore(snap)

        except Exception as e:
            self._add_log("ERROR", f"파싱 오류: {e}")

    def _cb_cancel(self, msg: String):
        """
        /dsr01/cancel_signal 수신 시 호출.
        parameter_publisher.py 가 발행하는 'cancel' 페이로드와 호환.
        → Firestore job_status 를 cancelled 상태로 초기화
        """
        try:
            payload = msg.data.strip()
            # parameter_publisher 는 "cancel" 문자열 또는 JSON {"status":"cancel"} 발행
            is_cancel = (
                payload == "cancel"
                or (payload.startswith("{") and json.loads(payload).get("status") == "cancel")
            )
            if not is_cancel:
                return

            # 인메모리 상태도 리셋 → 재시작 시 중복 기록 방지
            self._last_done         = 0
            self._job_complete_sent = False

            fs_logger.record_job_cancelled()
            self._add_log("WARN", "🚨 취소 신호 수신 → Firestore job_status 초기화")

        except Exception as e:
            self._add_log("ERROR", f"cancel_signal 처리 오류: {e}")

    # ── Firestore 트리거 ─────────────────────────────

    def _maybe_record_firestore(self, s: RobotSnapshot):
        """
        done 값 증가 감지 → 꽃 완료 기록
        done >= total     → 전체 완료 기록 (최초 1회)
        """
        if s.total == 0:
            return

        # ① 꽃 1개씩 완료
        if s.done > self._last_done:
            for idx in range(self._last_done + 1, s.done + 1):
                fs_logger.record_flower_done(idx, idx, s.total)
                self._add_log("OK", f"🌸 Firestore: flower {idx}/{s.total} 완료 기록")
            self._last_done = s.done

        # ② 전체 완료
        if s.done >= s.total and not self._job_complete_sent:
            self._job_complete_sent = True
            fs_logger.record_job_complete(s.total)
            self._add_log("OK", f"✅ Firestore: 전체 {s.total}개 작업 완료 기록")

    # ── 유틸 ─────────────────────────────────────────

    def _add_log(self, level: str, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._logs.append((ts, level.upper(), msg))
        if len(self._logs) > 100:
            self._logs.pop(0)

    def get_snapshot(self) -> RobotSnapshot:
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def get_logs(self) -> list:
        with self._lock:
            return list(self._logs)

    def send_recovery(self):
        out = String()
        out.data = "RECOVER"
        self._recovery_pub.publish(out)
        self._add_log("OK", "🔧 복구 명령 전송 → flower_robot_main")


# ══════════════════════════════════════════════════════
# TUI 대시보드
# ══════════════════════════════════════════════════════

def run_tui(node: MonitorNode):
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, Static, Label, Button
    from textual.containers import Horizontal, Vertical, ScrollableContainer

    def _prog_bar(done, total, w=26):
        if total == 0:
            return "[dim]" + "░" * w + "[/]", 0
        pct    = min(100, int(100 * done / total))
        filled = int(w * done / total)
        return (
            "[bright_green]" + "█" * filled + "[/]"
            + "[dim]" + "░" * (w - filled) + "[/]"
        ), pct

    # ── 위젯: 공정 상태 ───────────────────────────────
    class ProcessPanel(Static):
        DEFAULT_CSS = "ProcessPanel { border: solid #1e2d3d; padding: 0 1; height: 11; }"

        def compose(self):
            yield Label("[bold #2ea86a]◈ PROCESS STATUS[/]")
            yield Static(id="proc_body")

        def update_data(self, s: RobotSnapshot):
            if not s.connected:
                self.query_one("#proc_body", Static).update(
                    "[dim]flower_robot_main 연결 대기 중...[/]"
                )
                return
            bar_str, pct = _prog_bar(s.done, s.total)
            cur_str = (
                f"[bold cyan]{s.cur_flower}[/]번 꽃 작업 중"
                if s.cur_flower > 0 else "[dim]—[/]"
            )
            cd_line = (
                f"\n[dim]Countdown :[/]  [bold red]{s.countdown}초[/] 후 자동 재개"
                if s.countdown > 0 else ""
            )
            self.query_one("#proc_body", Static).update(
                f"[dim]FSM       :[/]  [bold {s.fsm_color}]{s.fsm_state}[/]\n"
                f"[dim]Progress  :[/]  {bar_str}  "
                f"[bright_green]{s.done}[/][dim]/[/]{s.total} 완료  ({pct}%)\n"
                f"[dim]Current   :[/]  {cur_str}\n"
                f"[dim]Resume @  :[/]  [dim]{s.resume_idx + 1}번 꽃부터 재개 예정[/]"
                f"{cd_line}"
            )

    # ── 위젯: 하드웨어 상태 ───────────────────────────
    class HWPanel(Static):
        DEFAULT_CSS = "HWPanel { border: solid #1e2d3d; padding: 0 1; height: 11; }"

        HW_GUIDE = {
            1: "[dim]—[/]",
            2: "[dim]—[/]",
            3: "[yellow]→ TUI 복구 버튼([R])으로 서보 ON[/]",
            5: "[yellow]→ TUI 복구 버튼([R])으로 보호 정지 해제[/]",
            6: "[red]→ 버튼 먼저 해제 후 TUI 복구 버튼([R]) 클릭[/]",
        }

        def compose(self):
            yield Label("[bold #7ec8e3]◈ HARDWARE STATE[/]")
            yield Static(id="hw_body")

        def update_data(self, s: RobotSnapshot):
            if not s.connected:
                self.query_one("#hw_body", Static).update("[dim]—[/]")
                return
            guide = self.HW_GUIDE.get(s.hw_code, "[dim]—[/]")
            self.query_one("#hw_body", Static).update(
                f"[dim]Code    :[/]  [{s.hw_color}]{s.hw_code}[/]\n"
                f"[dim]State   :[/]  [{s.hw_color}]{s.hw_label}[/] ●\n"
                f"[dim]Detail  :[/]  [{s.hw_color}]{s.hw_detail}[/]\n"
                f"[dim]Action  :[/]  {guide}"
            )

    # ── 위젯: 수동 복구 패널 ──────────────────────────
    class RecoveryPanel(Static):
        DEFAULT_CSS = """
        RecoveryPanel { border: solid #1e2d3d; padding: 0 1; height: 7; }
        RecoveryPanel Button { width: 100%; margin-top: 1; }
        """
        _last_armed: bool = False

        def compose(self):
            yield Label("[bold #c3aed6]◈ MANUAL RECOVERY[/]")
            yield Static("[dim]정상 운전 중[/]", id="recovery_status")
            yield Button("복구 실행  [R]", id="recovery_btn", disabled=True)

        def update_data(self, s: RobotSnapshot):
            armed = s.waiting_recovery
            if armed == self._last_armed:
                return
            self._last_armed = armed
            st  = self.query_one("#recovery_status", Static)
            btn = self.query_one("#recovery_btn", Button)
            if armed:
                stop_label = {
                    5: "안전정지 (Protective Stop)",
                    6: "비상정지 (Emergency Stop)",
                    3: "서보 꺼짐 (Safe Off)",
                }.get(s.hw_code, "정지 감지")
                st.update(
                    f"[yellow]{stop_label} 발생[/]\n"
                    f"[dim]{s.resume_idx + 1}번 꽃부터 재개 예정 — 확인 후 복구 버튼을 누르세요[/]"
                )
                btn.disabled = False
                btn.label    = "⚙  복구 실행  [R]"
            else:
                st.update("[dim]정상 운전 중[/]")
                btn.disabled = True
                btn.label    = "복구 실행  [R]"

        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "recovery_btn" and not event.button.disabled:
                node.send_recovery()

    # ── 위젯: 꽃 그리드 ───────────────────────────────
    class FlowerGridPanel(Static):
        DEFAULT_CSS = "FlowerGridPanel { border: solid #1e2d3d; padding: 0 1; height: 9; }"
        COLS = 20

        def compose(self):
            yield Label("[bold #ffd3b6]◈ FLOWER GRID[/]")
            yield Static(id="grid_body")

        def update_data(self, s: RobotSnapshot):
            if s.total == 0:
                self.query_one("#grid_body", Static).update("[dim]좌표 수신 대기 중...[/]")
                return
            rows, row = [], []
            for i in range(1, s.total + 1):
                if i <= s.done:
                    cell = f"[bright_green]{i:3d}[/]"
                elif i == s.cur_flower:
                    cell = f"[bold yellow]{i:3d}[/]"
                else:
                    cell = f"[dim]{i:3d}[/]"
                row.append(cell)
                if len(row) == self.COLS:
                    rows.append(" ".join(row))
                    row = []
            if row:
                rows.append(" ".join(row))
            legend = "[bright_green]■[/] 완료  [bold yellow]■[/] 현재  [dim]·[/] 대기\n"
            self.query_one("#grid_body", Static).update(legend + "\n".join(rows))

    # ── 위젯: Resume 정보 ─────────────────────────────
    class ResumePanel(Static):
        DEFAULT_CSS = "ResumePanel { border: solid #1e2d3d; padding: 0 1; height: 5; }"

        def compose(self):
            yield Label("[bold #c3aed6]◈ RESUME INFO[/]")
            yield Static(id="resume_body")

        def update_data(self, s: RobotSnapshot):
            if not s.connected:
                self.query_one("#resume_body", Static).update("[dim]—[/]")
                return
            remaining = max(s.total - s.done, 0)
            if s.hw_code in (3, 5, 6):
                stop_type = {
                    5: "[bold yellow]안전정지 (Protective Stop)[/]",
                    6: "[bold red]비상정지 (Emergency Stop)[/]",
                    3: "[bold red]서보 꺼짐 (Safe Off)[/]",
                }.get(s.hw_code, "")
                body = (
                    f"[dim]Stop type :[/]  {stop_type}\n"
                    f"[dim]Resume @  :[/]  [bold cyan]{s.resume_idx + 1}번 꽃[/]부터 재개 예정"
                )
            else:
                body = (
                    f"[dim]Completed :[/]  [bright_green]{s.done}[/] / {s.total} 개\n"
                    f"[dim]Remaining :[/]  [cyan]{remaining}[/] 개 남음"
                )
            self.query_one("#resume_body", Static).update(body)

    # ── 위젯: 이벤트 로그 ─────────────────────────────
    class EventLogPanel(ScrollableContainer):
        DEFAULT_CSS = "EventLogPanel { border: solid #1e2d3d; padding: 0 1; height: 27; }"

        def compose(self):
            yield Label("[bold #c3aed6]◈ EVENT LOG  ←  flower_robot_main[/]")
            yield Static(id="log_lines")

        def update_data(self, logs: list):
            recent = logs[-22:]
            lines  = []
            for ts, lvl, msg in reversed(recent):
                if   lvl == "ERROR":            lc = "red"
                elif lvl in ("WARN","WARNING"): lc = "yellow"
                elif lvl == "OK":               lc = "bright_green"
                else:                           lc = "dim"
                lines.append(
                    f"[dim]{ts}[/]  [{lc}][{lvl[:4]:4s}][/]  [{lc}]{msg}[/]"
                )
            self.query_one("#log_lines", Static).update(
                "\n".join(lines) if lines else "[dim](로그 없음)[/]"
            )

    # ── 메인 TUI 앱 ───────────────────────────────────
    class MonitorDashboard(App):
        TITLE     = "M0609 · Flower Robot Monitor"
        SUB_TITLE = "monitor_node  ←  /dsr01/robot_monitor_status"

        CSS = """
        Screen { background: #080c10; }
        Header { background: #0d1520; color: #4a7fa5; text-style: bold; }
        Footer { background: #0d1520; color: #2a4a6a; }
        .left  { width: 1fr; }
        .right { width: 1fr; }
        Label  { padding: 0 0 1 0; text-style: bold; }
        """

        BINDINGS = [
            ("q", "quit",         "Quit"),
            ("r", "send_recover", "Recover [R]"),
            ("p", "pause_tui",    "Pause / Resume TUI"),
        ]

        def __init__(self):
            super().__init__()
            self._paused = False

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                with Vertical(classes="left"):
                    yield ProcessPanel(id="proc_panel")
                    yield FlowerGridPanel(id="grid_panel")
                    yield ResumePanel(id="resume_panel")
                with Vertical(classes="right"):
                    yield HWPanel(id="hw_panel")
                    yield RecoveryPanel(id="recovery_panel")
                    yield EventLogPanel(id="event_log")
            yield Footer()

        def on_mount(self):
            self.set_interval(1 / 10, self._tick)

        def _tick(self):
            if self._paused:
                return
            s    = node.get_snapshot()
            logs = node.get_logs()
            self.query_one("#proc_panel",     ProcessPanel).update_data(s)
            self.query_one("#hw_panel",       HWPanel).update_data(s)
            self.query_one("#grid_panel",     FlowerGridPanel).update_data(s)
            self.query_one("#resume_panel",   ResumePanel).update_data(s)
            self.query_one("#recovery_panel", RecoveryPanel).update_data(s)
            self.query_one("#event_log",      EventLogPanel).update_data(logs)

        def action_send_recover(self):
            if node.get_snapshot().waiting_recovery:
                node.send_recovery()

        def action_pause_tui(self):
            self._paused = not self._paused
            self.sub_title = (
                "⏸ TUI PAUSED  (P 키로 재개)"
                if self._paused
                else "monitor_node  ←  /dsr01/robot_monitor_status"
            )

    MonitorDashboard().run()


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

def main(args=None):
    rclpy.init(args=args)
    node = MonitorNode()

    spin_thread = threading.Thread(
        target=rclpy.spin,
        args=(node,),
        daemon=True,
        name="ROS2_spin",
    )
    spin_thread.start()

    try:
        run_tui(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

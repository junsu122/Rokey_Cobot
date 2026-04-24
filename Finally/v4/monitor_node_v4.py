#!/usr/bin/env python3
"""
monitor_node.py
────────────────────────────────────────────────────────────────
Doosan M0609 Flower Robot 실시간 TUI 모니터링 노드

[flower.py hw_cache 갱신 시점]
  - refresh_hw() 는 메인 스레드에서만 호출
  - movej/movel 완료 직후 호출 → STANDBY(1) 또는 에러 코드 반영
  - 이동 중에는 이전 hw_code 값이 유지됨 (MOVING=2 는 전달되지 않음)
  - IDLE 루프에서 rclpy.spin_once 후 주기적으로 호출

[job_status 매핑 — flower.py 실제 동작 기준]
  hw=3/5/6          → "stopped"
  FSM=IDLE + hw=1   → "idle"
  FSM=BASIC + hw=1  → "running"   (이동 중/대기 모두 포함)
  FSM=PAUSED        → "paused"
  FSM=REPROCESS     → "cancelled"

[Firestore 기록]
  컬렉션 : robot_status / 문서 ID: dsr01
  필드   : cur_flower_index, job_status, done, total,
           hw_code, hw_state, robot_connected, updated_at
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
# Firebase 초기화
# ══════════════════════════════════════════════════════

SERVICE_ACCOUNT_PATH = "/home/ludix/test_23/serviceAccountKey.json"
ROBOT_ID             = "dsr01"

if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

db = fs_admin.client()

FS_COLLECTION = "robot_status"
FS_DOC_ID     = ROBOT_ID


# ══════════════════════════════════════════════════════
# Firestore 헬퍼
# ══════════════════════════════════════════════════════

class FirestoreLogger:

    def _run(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def push_status(
        self,
        index:           int,
        job_status:      str,
        done:            int,
        total:           int,
        hw_code:         int,
        hw_state:        str,
        robot_connected: bool,
    ):
        """
        robot_status/dsr01 에 현재 상태 전체 기록.

        hw_code / hw_state — flower.py refresh_hw() 호출 시점 기준:
          1 / "STANDBY"   - 이동 완료 후 정상 대기
          3 / "SAFE_OFF"  - 서보 꺼짐  (이동 완료 후 감지)
          5 / "PROT_STOP" - 안전정지   (이동 완료 후 감지)
          6 / "EMRG_STOP" - 비상정지   (이동 완료 후 감지)
          ※ MOVING(2) 은 refresh_hw() 가 이동 완료 후 호출되므로 실제로는 전달 안 됨

        robot_connected:
          True  - 최근 8초 이내 토픽 수신
          False - 8초 이상 토픽 없음
        """
        def _write():
            try:
                ref = db.collection(FS_COLLECTION).document(FS_DOC_ID)
                ref.set(
                    {
                        "cur_flower_index": index,
                        "job_status":       job_status,
                        "done":             done,
                        "total":            total,
                        "hw_code":          hw_code,
                        "hw_state":         hw_state,
                        "robot_connected":  robot_connected,
                        "updated_at":       SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
            except Exception as e:
                print(
                    f"[Firestore] push_status 실패"
                    f" (idx={index}, status={job_status},"
                    f" hw={hw_code}/{hw_state},"
                    f" connected={robot_connected}): {e}"
                )

        self._run(_write)


fs_logger = FirestoreLogger()


# ══════════════════════════════════════════════════════
# 수신 상태 파싱
# ══════════════════════════════════════════════════════

class RobotSnapshot:

    HW_MAP = {
        1: ("Standby",   "정상 대기 중",              "green"),
        2: ("Moving",    "이동 명령 실행 중",          "cyan"),
        3: ("Safe Off",  "서보 꺼짐 — 복구 필요",     "red"),
        5: ("Prot Stop", "보호 정지 — 원인 해소 필요", "yellow"),
        6: ("Emrg Stop", "비상정지 — 버튼 해제 필요",  "red"),
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
    def connected(self) -> bool:
        return (time.time() - self.stamp) < 8.0

    @property
    def hw_label(self):  return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[0]
    @property
    def hw_detail(self): return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[1]
    @property
    def hw_color(self):  return self.HW_MAP.get(self.hw_code, ("???", "알 수 없음", "white"))[2]
    @property
    def fsm_color(self): return self.FSM_COLOR.get(self.fsm_state, "white")

    @property
    def hw_state(self) -> str:
        return self.HW_MAP.get(self.hw_code, ("UNKNOWN",))[0]

    @property
    def job_status(self) -> str:
        """
        flower.py 실제 동작 기준 job_status 결정.

        flower.py 에서 get_robot_state() 는 이동 완료 후에만 호출되므로
        MOVING(2) 은 토픽으로 전달되지 않음.
        FSM 상태 + hw_code 조합으로 판단:

          hw 3/5/6      → "stopped"   (에러 감지 최우선)
          FSM=REPROCESS → "cancelled" (취소 공정 중)
          FSM=PAUSED    → "paused"
          FSM=BASIC     → "running"   (이동 중 포함, hw=1)
          FSM=IDLE      → "idle"
        """
        if self.hw_code in (3, 5, 6):
            return "stopped"
        if self.hw_code == 2:          # ✅ safe_movej/movel 에서 수동 설정
            return "running"
        return {
            "REPROCESS": "cancelled",
            "PAUSED":    "paused",
            "BASIC":     "running",
            "IDLE":      "idle",
        }.get(self.fsm_state, "idle")


# ══════════════════════════════════════════════════════
# ROS2 모니터링 노드
# ══════════════════════════════════════════════════════

class MonitorNode(Node):
    def __init__(self):
        super().__init__("flower_monitor_node")
        self._lock     = threading.Lock()
        self._snapshot = RobotSnapshot({})
        self._logs     = []

        # (cur_flower, job_status, done, total, hw_code, connected)
        self._last_pushed: tuple = (-1, "", -1, -1, -1, None)

        self.create_subscription(
            String,
            "/dsr01/robot_monitor_status",
            self._cb,
            10,
        )

        self._recovery_pub = self.create_publisher(
            String, "/dsr01/recovery_command", 10
        )

        self.create_timer(1.0, self._firestore_timer_cb)

        self._add_log("INFO", "monitor_node 시작")
        self._add_log("INFO", "/dsr01/robot_monitor_status 구독 대기 중...")

    # ── ROS2 콜백 ────────────────────────────────────

    def _cb(self, msg: String):
        try:
            d = json.loads(msg.data)
            d["stamp"] = time.time()
            snap    = RobotSnapshot(d)
            log_msg = d.get("log", "")

            with self._lock:
                prev_flower    = self._snapshot.cur_flower
                prev_status    = self._snapshot.job_status
                prev_done      = self._snapshot.done
                prev_hw_code   = self._snapshot.hw_code
                prev_connected = self._snapshot.connected
                self._snapshot = snap
                if log_msg:
                    self._add_log(d.get("log_level", "INFO"), log_msg)

            changed = (
                snap.cur_flower != prev_flower
                or snap.job_status != prev_status
                or snap.done      != prev_done
                or snap.hw_code   != prev_hw_code
                or snap.connected != prev_connected
            )
            if changed:
                # ── 상태 전이 로그 ──────────────────────────────
                if snap.job_status == "cancelled" and prev_status != "cancelled":
                    self._add_log("WARN", "🚫 주문 취소 감지 → DB cancelled 기록")

                if prev_status == "cancelled" and snap.job_status == "idle":
                    self._add_log("OK", "✅ 취소 완료 — 리셋 완료 → DB idle 기록")

                if snap.job_status == "running" and prev_status == "idle":
                    self._add_log("INFO", "▶️ 작업 시작 → DB running 기록")

                if snap.job_status == "idle" and prev_status == "running":
                    self._add_log("OK", "🎊 작업 완료 → DB idle 기록")

                # hw 에러 전이 로그
                if snap.hw_code == 5 and prev_hw_code != 5:
                    self._add_log("WARN",  "🟡 안전정지(PROT_STOP) 감지 → DB stopped 기록")
                if snap.hw_code == 6 and prev_hw_code != 6:
                    self._add_log("ERROR", "🔴 비상정지(EMRG_STOP) 감지 → DB stopped 기록")
                if snap.hw_code == 3 and prev_hw_code != 3:
                    self._add_log("ERROR", "⚡ 서보 꺼짐(SAFE_OFF) 감지 → DB stopped 기록")

                # hw 복구 전이 로그
                if prev_hw_code in (3, 5, 6) and snap.hw_code == 1:
                    self._add_log("OK", f"✅ HW 복구 완료 ({prev_hw_code} → STANDBY)")

                # 연결 끊김/복귀 로그
                if not snap.connected and prev_connected:
                    self._add_log("WARN",  "📡 flower_robot_main 연결 끊김")
                if snap.connected and not prev_connected:
                    self._add_log("OK",    "📡 flower_robot_main 연결 복귀")

                self._do_push(snap)

        except Exception as e:
            self._add_log("ERROR", f"파싱 오류: {e}")

    # ── Firestore heartbeat (1 Hz) ───────────────────

    def _firestore_timer_cb(self):
        snap = self.get_snapshot()

        current = (
            snap.cur_flower,
            snap.job_status,
            snap.done,
            snap.total,
            snap.hw_code,
            snap.connected,
        )
        if current != self._last_pushed:
            self._do_push(snap)
        elif int(time.time()) % 30 == 0:
            # 30초마다 updated_at heartbeat
            self._do_push(snap)

    # ── 실제 push ────────────────────────────────────

    def _do_push(self, snap: RobotSnapshot):
        self._last_pushed = (
            snap.cur_flower,
            snap.job_status,
            snap.done,
            snap.total,
            snap.hw_code,
            snap.connected,
        )
        fs_logger.push_status(
            index           = snap.cur_flower,
            job_status      = snap.job_status,
            done            = snap.done,
            total           = snap.total,
            hw_code         = snap.hw_code,
            hw_state        = snap.hw_state,
            robot_connected = snap.connected,
        )
        self._add_log(
            "INFO",
            f"📤 DB → idx:{snap.cur_flower}  status:{snap.job_status}"
            f"  done:{snap.done}/{snap.total}"
            f"  hw:{snap.hw_state}({snap.hw_code})  conn:{snap.connected}",
        )

    # ── 유틸 ─────────────────────────────────────────

    def _add_log(self, level: str, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._logs.append((ts, level.upper(), msg))
        if len(self._logs) > 200:
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

    class ProcessPanel(Static):
        DEFAULT_CSS = "ProcessPanel { border: solid #1e2d3d; padding: 0 1; height: 12; }"

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
            STATUS_LABEL = {
                "idle":      "[dim]대기 중[/]",
                "running":   "[bright_green]작업 중[/]",
                "paused":    "[bold blue]일시정지[/]",
                "stopped":   "[bold red]정지됨[/]",
                "cancelled": "[bold yellow]취소됨 — 홈 복귀 중[/]",
            }
            # hw_code 기준 배지 — flower.py 실제 전달값 기준
            HW_BADGE = {
                1: "[green]● STANDBY[/]",
                2: "[cyan]▶ MOVING[/]",    # 실제 수신 드묾
                3: "[red]✕ SAFE_OFF[/]",
                5: "[yellow]⚠ PROT_STOP[/]",
                6: "[red]🛑 EMRG_STOP[/]",
            }
            hw_badge = HW_BADGE.get(s.hw_code, f"[dim]{s.hw_state}[/]")

            self.query_one("#proc_body", Static).update(
                f"[dim]FSM       :[/]  [bold {s.fsm_color}]{s.fsm_state}[/]  {hw_badge}\n"
                f"[dim]Job Status:[/]  {STATUS_LABEL.get(s.job_status, s.job_status)}\n"
                f"[dim]Progress  :[/]  {bar_str}  "
                f"[bright_green]{s.done}[/][dim]/[/]{s.total} 완료  ({pct}%)\n"
                f"[dim]Current   :[/]  {cur_str}\n"
                f"[dim]Resume @  :[/]  [dim]{s.resume_idx + 1}번 꽃부터 재개 예정[/]"
                f"{cd_line}"
            )

    class HWPanel(Static):
        DEFAULT_CSS = "HWPanel { border: solid #1e2d3d; padding: 0 1; height: 11; }"

        # flower.py 실제 hw_code 전달값 기준 안내
        HW_GUIDE = {
            1: "[dim]정상 대기 — 이동 완료 상태[/]",
            2: "[cyan]이동 명령 실행 중[/]",
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

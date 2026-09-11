from __future__ import annotations

import base64
import ctypes
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from .fusion_eyes_runtime import EYES_PROXY_PORT, build_eyes_process_specs
    from .fusion_hands_runtime import HANDS_MCP_PORT, SHIMMER_ADDIN_PORT, build_hands_process_specs, ensure_hands_overlay
except ImportError:  # Direct pythonw launch from the agents directory.
    from fusion_eyes_runtime import EYES_PROXY_PORT, build_eyes_process_specs
    from fusion_hands_runtime import HANDS_MCP_PORT, SHIMMER_ADDIN_PORT, build_hands_process_specs, ensure_hands_overlay

BRIDGE_HOST = "mcp.vigilante.website"
BRIDGE_URL = "https://mcp.vigilante.website"
NODE_ID = "fusion-workstation"
FUSION_HOST = "127.0.0.1"
FUSION_PORT = 27182
FUSION_URL = "http://127.0.0.1:27182/mcp"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DevelopmentBridgeFusion"
TOKEN_FILE = APP_DIR / "desktop-node-token.dpapi"
LOG_FILE = APP_DIR / "relay.log"
EYES_RELAY_LOG = APP_DIR / "eyes-relay.log"
EYES_PROXY_LOG = APP_DIR / "eyes-proxy.log"
HANDS_RELAY_LOG = APP_DIR / "hands-relay.log"
HANDS_SIDECAR_LOG = APP_DIR / "hands-sidecar.log"
ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "windows_fusion_agent.py"
TIMESTAMPED_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s")
HANDS_STARTUP_DEADLINE_SECONDS = 20.0


def timestamp_log_line(line: str, now: float | None = None) -> str:
    """Prefix a local millisecond timestamp once while preserving parser text."""
    clean = line.rstrip("\r\n")
    if TIMESTAMPED_LINE.match(clean):
        return clean
    moment = time.time() if now is None else now
    local = time.localtime(moment)
    millis = int(moment * 1000) % 1000
    return time.strftime("%H:%M:%S", local) + f".{millis:03d} " + clean


class RestartBackoff:
    def __init__(self, delays: tuple[float, ...] = (2.0, 5.0, 10.0, 30.0)) -> None:
        self.delays = delays
        self.failures = 0
        self.retry_at = 0.0

    def fail(self, *, now: float | None = None) -> float:
        moment = time.monotonic() if now is None else now
        delay = self.delays[min(self.failures, len(self.delays) - 1)]
        self.failures += 1
        self.retry_at = moment + delay
        return self.retry_at

    def ready(self, *, now: float | None = None) -> bool:
        return (time.monotonic() if now is None else now) >= self.retry_at

    def recovered(self) -> None:
        self.failures = 0
        self.retry_at = 0.0


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def dpapi_protect(text: str) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI is available only on Windows")
    incoming, holder = _blob(text.encode("utf-8"))
    outgoing = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(incoming), None, None, None, None, 0, ctypes.byref(outgoing)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


def dpapi_unprotect(data: bytes) -> str:
    if os.name != "nt":
        raise RuntimeError("DPAPI is available only on Windows")
    incoming, holder = _blob(data)
    outgoing = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(incoming), None, None, None, None, 0, ctypes.byref(outgoing)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


def save_token(token: str) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_bytes(base64.b64encode(dpapi_protect(token)))


def load_token() -> str | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return dpapi_unprotect(base64.b64decode(TOKEN_FILE.read_bytes()))
    except Exception:
        return None


def tcp_open(host: str, port: int, timeout: float = 0.65) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class FusionBridgeGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fusion Bridge")
        self.geometry("720x520")
        self.minsize(640, 430)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.proc: subprocess.Popen[str] | None = None
        self.eyes_proxy_proc: subprocess.Popen[str] | None = None
        self.eyes_relay_proc: subprocess.Popen[str] | None = None
        self.eyes_runtime_present: bool | None = None
        self.eyes_connected = False
        self.eyes_problem: str | None = None
        self.hands_sidecar_proc: subprocess.Popen[str] | None = None
        self.hands_relay_proc: subprocess.Popen[str] | None = None
        self.hands_runtime_present: bool | None = None
        self.hands_connected = False
        self.hands_problem: str | None = None
        self.hands_sidecar_deadline = 0.0
        self.hands_pending_relay: tuple[dict[str, object], int] | None = None
        self.supervision_enabled = True
        self.backoffs = {name: RestartBackoff() for name in ("reference", "eyes", "hands")}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.connected = False
        self.heartbeat_ok: bool | None = None
        self.heartbeat_failures = 0
        self.delivery_degraded = False
        self.outbox_count = 0
        self._build()
        self._update_token_state()
        threading.Thread(target=self._status_worker, daemon=True).start()
        self.after(100, self._drain_events)
        self.after(250, self._supervise)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="ChatGPT ↔ Development Bridge ↔ Autodesk Fusion", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 12))

        status = ttk.LabelFrame(outer, text="Статус", padding=10)
        status.pack(fill="x")
        self.fusion_label = ttk.Label(status, text="Fusion MCP: проверка…")
        self.bridge_label = ttk.Label(status, text="Bridge: проверка…")
        self.relay_label = ttk.Label(status, text="Reference — Autodesk MCP / fusion-workstation: ожидание…")
        self.connection_label = ttk.Label(status, text="MCP session: не подключена")
        self.heartbeat_label = ttk.Label(status, text="Bridge heartbeat: ожидание…")
        self.delivery_label = ttk.Label(status, text="Result delivery: ожидание…")
        self.eyes_label = ttk.Label(status, text="Eyes — PERISCOPE / fusion-eyes: ожидание…")
        self.hands_label = ttk.Label(status, text="Hands — Shimmer / fusion-hands: ожидание…")
        for widget in (self.fusion_label, self.bridge_label, self.relay_label, self.connection_label, self.heartbeat_label, self.delivery_label, self.eyes_label, self.hands_label):
            widget.pack(anchor="w", pady=2)

        token_frame = ttk.LabelFrame(outer, text="Desktop-node token", padding=10)
        token_frame.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(token_frame)
        row.pack(fill="x")
        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(row, textvariable=self.token_var, show="•")
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.remember_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Запомнить на этом ПК", variable=self.remember_var).pack(side="left", padx=(10, 0))
        self.token_state = ttk.Label(token_frame, text="")
        self.token_state.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=10)
        self.start_button = ttk.Button(buttons, text="▶ Retry / Start", command=self.start_relay)
        self.stop_button = ttk.Button(buttons, text="■ Stop", command=self.stop_relay, state="disabled")
        self.forget_button = ttk.Button(buttons, text="Забыть токен", command=self.forget_token)
        self.open_log_button = ttk.Button(buttons, text="Открыть лог", command=self.open_log)
        for widget in (self.start_button, self.stop_button, self.forget_button, self.open_log_button):
            widget.pack(side="left", padx=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="Лог", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, wrap="word", height=12, state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(outer, text="Закрытие окна останавливает relay. Токен хранится локально через Windows DPAPI.").pack(anchor="w", pady=(8, 0))

    def _set_text(self, widget: ttk.Label, prefix: str, ok: bool, detail: str) -> None:
        widget.configure(text=f"{prefix}: {'●' if ok else '○'} {detail}")

    def _status_worker(self) -> None:
        while not self.stop_event.is_set():
            fusion = tcp_open(FUSION_HOST, FUSION_PORT)
            bridge = tcp_open(BRIDGE_HOST, 443)
            shimmer_addin = tcp_open("127.0.0.1", SHIMMER_ADDIN_PORT)
            self.events.put(("network", (fusion, bridge, shimmer_addin)))
            self.stop_event.wait(2.0)

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "network":
                    fusion, bridge, shimmer_addin = value  # type: ignore[misc]
                    self._set_text(self.fusion_label, "Fusion MCP", bool(fusion), "127.0.0.1:27182 доступен" if fusion else "порт 27182 закрыт")
                    self._set_text(self.bridge_label, "Bridge", bool(bridge), "доступен" if bridge else "недоступен")
                    if not fusion:
                        self.connected = False
                        self.eyes_connected = False
                    if not shimmer_addin:
                        self.hands_connected = False
                elif kind == "log":
                    self._append_log(str(value))
                elif kind == "connected":
                    self.connected = bool(value)
                    if self.connected and self.heartbeat_ok is None:
                        self.heartbeat_ok = True
                    if self.connected:
                        self.backoffs["reference"].recovered()
                elif kind == "eyes_connected":
                    event_proc, connected = value  # type: ignore[misc]
                    if event_proc is self.eyes_relay_proc:
                        self.eyes_connected = bool(connected)
                        if connected:
                            self.backoffs["eyes"].recovered()
                elif kind == "eyes_proxy_stopped":
                    event_proc, _returncode = value  # type: ignore[misc]
                    if event_proc is self.eyes_proxy_proc:
                        self._stop_eyes_stack()
                        self.eyes_problem = f"mcp-proxy завершился (код {_returncode})"
                        self.backoffs["eyes"].fail()
                elif kind == "eyes_stopped":
                    event_proc, _returncode = value  # type: ignore[misc]
                    if event_proc is self.eyes_relay_proc:
                        self._stop_eyes_stack()
                        self.eyes_problem = f"fusion-eyes relay завершился (код {_returncode})"
                        self.backoffs["eyes"].fail()
                elif kind == "hands_connected":
                    event_proc, connected = value  # type: ignore[misc]
                    if event_proc is self.hands_relay_proc:
                        self.hands_connected = bool(connected)
                        if connected:
                            self.backoffs["hands"].recovered()
                elif kind == "hands_sidecar_stopped":
                    event_proc, _returncode = value  # type: ignore[misc]
                    if event_proc is self.hands_sidecar_proc:
                        self._stop_hands_stack()
                        self.hands_problem = f"Shimmer sidecar завершился (код {_returncode})"
                        self.backoffs["hands"].fail()
                elif kind == "hands_stopped":
                    event_proc, _returncode = value  # type: ignore[misc]
                    if event_proc is self.hands_relay_proc:
                        self._stop_hands_stack()
                        self.hands_problem = f"fusion-hands relay завершился (код {_returncode})"
                        self.backoffs["hands"].fail()
                elif kind == "stopped":
                    event_proc, _returncode = value  # type: ignore[misc]
                    if event_proc is self.proc:
                        self.proc = None
                        self.connected = False
                        self.heartbeat_ok = None
                        self.heartbeat_failures = 0
                        self.delivery_degraded = False
                        self.outbox_count = 0
                        self.backoffs["reference"].fail()
                self._refresh_relay_labels()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._drain_events)

    def _refresh_relay_labels(self) -> None:
        running = self.proc is not None and self.proc.poll() is None
        self._set_text(self.relay_label, "Reference — Autodesk MCP / fusion-workstation", running and self.connected, "online" if running and self.connected else ("ожидание Fusion/Bridge" if running else "failed/retrying"))
        self._set_text(self.connection_label, "MCP session", running and self.connected, "Fusion зарегистрирован в Bridge" if running and self.connected else "ожидание регистрации")
        if not running:
            self._set_text(self.heartbeat_label, "Bridge heartbeat", False, "relay остановлен")
        elif self.heartbeat_ok is False:
            self._set_text(self.heartbeat_label, "Bridge heartbeat", False, f"сбои подряд: {self.heartbeat_failures}")
        elif self.heartbeat_ok is True:
            self._set_text(self.heartbeat_label, "Bridge heartbeat", True, "OK")
        else:
            self.heartbeat_label.configure(text="Bridge heartbeat: ожидание…")
        if not running:
            self._set_text(self.delivery_label, "Result delivery", False, "relay остановлен")
        elif self.delivery_degraded:
            self._set_text(self.delivery_label, "Result delivery", False, f"degraded; outbox: {self.outbox_count}")
        else:
            self._set_text(self.delivery_label, "Result delivery", True, f"OK; outbox: {self.outbox_count}")

        eyes_relay_running = self.eyes_relay_proc is not None and self.eyes_relay_proc.poll() is None
        eyes_proxy_running = self.eyes_proxy_proc is not None and self.eyes_proxy_proc.poll() is None
        if self.eyes_problem:
            self._set_text(self.eyes_label, "Eyes — PERISCOPE / fusion-eyes", False, self.eyes_problem)
        elif self.eyes_runtime_present is False:
            self._set_text(self.eyes_label, "Eyes — PERISCOPE / fusion-eyes", False, "PERISCOPE runtime не установлен")
        elif eyes_relay_running and self.eyes_connected:
            self._set_text(self.eyes_label, "Eyes — PERISCOPE / fusion-eyes", True, "online; зарегистрирован в Bridge")
        elif eyes_relay_running:
            detail = "ожидание MCP session" if eyes_proxy_running else "proxy не запущен"
            self._set_text(self.eyes_label, "Eyes — PERISCOPE / fusion-eyes", False, detail)
        else:
            self._set_text(self.eyes_label, "Eyes — PERISCOPE / fusion-eyes", False, "waiting/retrying")

        hands_relay_running = self.hands_relay_proc is not None and self.hands_relay_proc.poll() is None
        hands_sidecar_running = self.hands_sidecar_proc is not None and self.hands_sidecar_proc.poll() is None
        if self.hands_problem:
            self._set_text(self.hands_label, "Hands — Shimmer / fusion-hands", False, self.hands_problem)
        elif self.hands_runtime_present is False:
            self._set_text(self.hands_label, "Hands — Shimmer / fusion-hands", False, "runtime/overlay отсутствует или не квалифицирован")
        elif hands_relay_running and self.hands_connected:
            self._set_text(self.hands_label, "Hands — Shimmer / fusion-hands", True, "online; qualification is Bridge-owned/session-scoped")
        elif hands_relay_running:
            self._set_text(self.hands_label, "Hands — Shimmer / fusion-hands", False, "overlay applied; qualification is Bridge-owned/session-scoped" if hands_sidecar_running else "sidecar не запущен")
        else:
            self._set_text(self.hands_label, "Hands — Shimmer / fusion-hands", False, "waiting/retrying")

    def _append_log(self, line: str) -> None:
        line = timestamp_log_line(line)
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 600:
            self.log.delete("1.0", f"{lines-500}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _update_token_state(self) -> None:
        self.token_state.configure(text="Токен: сохранён для текущего пользователя Windows" if load_token() else "Токен: не сохранён")

    def _token_for_start(self) -> str | None:
        typed = self.token_var.get().strip()
        if typed:
            if self.remember_var.get():
                try:
                    save_token(typed)
                    self._update_token_state()
                except Exception as exc:
                    messagebox.showerror("Fusion Bridge", f"Не удалось сохранить токен через DPAPI:\n{exc}")
                    return None
            return typed
        return load_token()

    def _supervise(self) -> None:
        if self.supervision_enabled and not self.stop_event.is_set():
            self._continue_hands_start()
            self.start_relay(automatic=True)
        if self.winfo_exists():
            self.after(2000, self._supervise)

    def start_relay(self, automatic: bool = False) -> None:
        if not automatic:
            self.supervision_enabled = True
            for backoff in self.backoffs.values():
                backoff.recovered()
        token = load_token() if automatic else self._token_for_start()
        if not token:
            if not automatic:
                messagebox.showwarning("Fusion Bridge", "Вставь desktop-node token один раз и нажми Start.")
                self.token_entry.focus_set()
            return
        if not AGENT.exists():
            if not automatic:
                messagebox.showerror("Fusion Bridge", f"Не найден агент:\n{AGENT}")
            return
        APP_DIR.mkdir(parents=True, exist_ok=True)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        python = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
        if (self.proc is None or self.proc.poll() is not None) and self.backoffs["reference"].ready():
            env = os.environ.copy()
            env.update({
                "DEVELOPMENT_BRIDGE_URL": BRIDGE_URL,
                "DEVELOPMENT_BRIDGE_NODE_ID": NODE_ID,
                "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN": token,
                "FUSION_MCP_URL": FUSION_URL,
                "PYTHONUNBUFFERED": "1",
            })
            try:
                self.proc = subprocess.Popen(
                    [python, str(AGENT)], cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=creationflags,
                )
                self._append_log("[reference] relay starting; waits for Fusion automatically")
                threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
            except Exception as exc:
                self.proc = None
                self.backoffs["reference"].fail()
                self._append_log(f"[reference] запуск не удался: {type(exc).__name__}: {exc}")
        self.token_var.set("")
        self.stop_button.configure(state="normal")
        if self.eyes_proxy_proc is None and self.eyes_relay_proc is None and self.backoffs["eyes"].ready():
            self._start_eyes_stack(token, python, creationflags)
        if self.hands_sidecar_proc is None and self.hands_relay_proc is None and self.backoffs["hands"].ready():
            self._start_hands_stack(token, python, creationflags)
        self._refresh_relay_labels()

    def _start_eyes_stack(self, token: str, relay_python: str, creationflags: int) -> None:
        self._stop_eyes_stack()
        specs = build_eyes_process_specs(
            token,
            app_dir=APP_DIR,
            root=ROOT,
            relay_python=Path(relay_python),
            environ=os.environ,
            bridge_url=BRIDGE_URL,
        )
        if specs is None:
            self.eyes_runtime_present = False
            self.eyes_problem = "PERISCOPE runtime не установлен"
            self._append_log("[eyes] PERISCOPE runtime отсутствует; fusion-workstation продолжает работать")
            self.backoffs["eyes"].fail()
            return
        self.eyes_runtime_present = True
        self.eyes_problem = None
        proxy_spec, relay_spec = specs
        APP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if tcp_open("127.0.0.1", EYES_PROXY_PORT):
                self.eyes_problem = "порт 18769 занят; Fusion Eyes не запущен"
                self._append_log("[eyes] " + self.eyes_problem)
                self.backoffs["eyes"].fail()
                return
            with EYES_PROXY_LOG.open("a", encoding="utf-8") as proxy_log:
                self.eyes_proxy_proc = subprocess.Popen(
                    proxy_spec["argv"],
                    cwd=proxy_spec["cwd"],
                    env=proxy_spec["env"],
                    stdout=proxy_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            self._append_log("[eyes] PERISCOPE mcp-proxy запущен на 127.0.0.1:18769")
            threading.Thread(
                target=self._eyes_proxy_watcher, args=(self.eyes_proxy_proc,), daemon=True
            ).start()

            self.eyes_relay_proc = subprocess.Popen(
                relay_spec["argv"],
                cwd=relay_spec["cwd"],
                env=relay_spec["env"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            threading.Thread(
                target=self._eyes_reader, args=(self.eyes_relay_proc,), daemon=True
            ).start()
            self._append_log("[eyes] fusion-eyes relay запущен; ждёт PERISCOPE MCP")
        except Exception as exc:
            problem = f"запуск не удался: {type(exc).__name__}: {exc}"
            self._append_log("[eyes] " + problem)
            self._stop_eyes_stack()
            self.eyes_problem = problem
            self.backoffs["eyes"].fail()

    def _eyes_proxy_watcher(self, proc: subprocess.Popen[str]) -> None:
        proc.wait()
        self.events.put(("eyes_proxy_stopped", (proc, proc.returncode)))

    def _eyes_reader(self, proc: subprocess.Popen[str]) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with EYES_RELAY_LOG.open("a", encoding="utf-8") as logfile:
            assert proc.stdout is not None
            for line in proc.stdout:
                stamped = timestamp_log_line(line)
                logfile.write(stamped + "\n")
                logfile.flush()
                if "Connected: Fusion MCP tools discovered:" in line:
                    self.events.put(("eyes_connected", (proc, True)))
                elif "Fusion MCP watchdog: port unavailable" in line or "Fusion/Bridge unavailable" in line:
                    self.events.put(("eyes_connected", (proc, False)))
                self.events.put(("log", "[eyes] " + line.rstrip()))
        proc.wait()
        self.events.put(("eyes_stopped", (proc, proc.returncode)))

    def _start_hands_stack(self, token: str, relay_python: str, creationflags: int) -> None:
        self._stop_hands_stack()
        specs = build_hands_process_specs(
            token, app_dir=APP_DIR, root=ROOT, relay_python=Path(relay_python),
            environ=os.environ, bridge_url=BRIDGE_URL,
        )
        if specs is None:
            self.hands_runtime_present = False
            self.hands_problem = "Shimmer runtime не установлен"
            self.backoffs["hands"].fail()
            return
        overlay = ensure_hands_overlay(APP_DIR, environ=os.environ)
        if overlay.state != "applied":
            self.hands_runtime_present = False
            self.hands_problem = f"overlay {overlay.state}: {overlay.detail}"
            self._append_log("[hands] " + self.hands_problem)
            self.backoffs["hands"].fail()
            return
        self.hands_runtime_present = True
        self.hands_problem = None
        sidecar_spec, relay_spec = specs
        try:
            if tcp_open("127.0.0.1", HANDS_MCP_PORT):
                self.hands_problem = "порт 18768 занят; Hands не запущен"
                self._append_log("[hands] " + self.hands_problem)
                self.backoffs["hands"].fail()
                return
            with HANDS_SIDECAR_LOG.open("a", encoding="utf-8") as sidecar_log:
                self.hands_sidecar_proc = subprocess.Popen(
                    sidecar_spec["argv"], cwd=sidecar_spec["cwd"], env=sidecar_spec["env"],
                    stdout=sidecar_log, stderr=subprocess.STDOUT, creationflags=creationflags,
                )
            threading.Thread(target=self._hands_sidecar_watcher, args=(self.hands_sidecar_proc,), daemon=True).start()
            self.hands_sidecar_deadline = time.monotonic() + HANDS_STARTUP_DEADLINE_SECONDS
            self.hands_pending_relay = (relay_spec, creationflags)
            self._append_log("[hands] Shimmer starting; waiting for owned sidecar on 18768")
        except Exception as exc:
            problem = f"запуск не удался: {type(exc).__name__}: {exc}"
            self._stop_hands_stack()
            self.hands_problem = problem
            self.backoffs["hands"].fail()

    def _continue_hands_start(self) -> None:
        pending = self.hands_pending_relay
        proc = self.hands_sidecar_proc
        if pending is None or proc is None:
            return
        if proc.poll() is not None:
            return  # The watcher reports and independently backs off this stack.
        if not tcp_open("127.0.0.1", HANDS_MCP_PORT):
            if time.monotonic() < self.hands_sidecar_deadline:
                return
            self.hands_pending_relay = None
            self._terminate_owned_process(proc, tree=True)
            if self.hands_sidecar_proc is proc:
                self.hands_sidecar_proc = None
            self.hands_problem = "owned Shimmer sidecar readiness deadline exceeded"
            self._append_log("[hands] " + self.hands_problem)
            self.backoffs["hands"].fail()
            return
        relay_spec, creationflags = pending
        self.hands_pending_relay = None
        try:
            self.hands_relay_proc = subprocess.Popen(
                relay_spec["argv"], cwd=relay_spec["cwd"], env=relay_spec["env"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1, creationflags=creationflags,
            )
            threading.Thread(target=self._hands_reader, args=(self.hands_relay_proc,), daemon=True).start()
            self._append_log("[hands] owned Shimmer ready; fusion-hands relay starting")
        except Exception as exc:
            self._stop_hands_stack()
            self.hands_problem = f"relay запуск не удался: {type(exc).__name__}: {exc}"
            self.backoffs["hands"].fail()

    def _hands_sidecar_watcher(self, proc: subprocess.Popen[str]) -> None:
        proc.wait()
        self.events.put(("hands_sidecar_stopped", (proc, proc.returncode)))

    def _hands_reader(self, proc: subprocess.Popen[str]) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with HANDS_RELAY_LOG.open("a", encoding="utf-8") as logfile:
            assert proc.stdout is not None
            for line in proc.stdout:
                stamped = timestamp_log_line(line)
                logfile.write(stamped + "\n")
                logfile.flush()
                if "Connected: Fusion MCP tools discovered:" in line:
                    self.events.put(("hands_connected", (proc, True)))
                elif "Fusion MCP watchdog: port unavailable" in line or "Fusion/Bridge unavailable" in line:
                    self.events.put(("hands_connected", (proc, False)))
                self.events.put(("log", "[hands] " + line.rstrip()))
        proc.wait()
        self.events.put(("hands_stopped", (proc, proc.returncode)))

    @staticmethod
    def _terminate_owned_process(proc: subprocess.Popen[str] | None, *, tree: bool = False) -> None:
        if proc is None or proc.poll() is not None:
            return
        if tree and os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                proc.wait(timeout=2)
                return
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _stop_eyes_stack(self) -> None:
        self._terminate_owned_process(self.eyes_relay_proc)
        self.eyes_relay_proc = None
        self.eyes_connected = False
        self._terminate_owned_process(self.eyes_proxy_proc, tree=True)
        self.eyes_proxy_proc = None
        self.eyes_problem = None

    def _stop_hands_stack(self) -> None:
        self.hands_pending_relay = None
        self.hands_sidecar_deadline = 0.0
        self._terminate_owned_process(self.hands_relay_proc)
        self.hands_relay_proc = None
        self.hands_connected = False
        self._terminate_owned_process(self.hands_sidecar_proc, tree=True)
        self.hands_sidecar_proc = None
        self.hands_problem = None

    def _reader(self, proc: subprocess.Popen[str]) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as logfile:
            assert proc.stdout is not None
            for line in proc.stdout:
                stamped = timestamp_log_line(line)
                logfile.write(stamped + "\n")
                logfile.flush()
                if "Connected: Fusion MCP tools discovered:" in line:
                    self.heartbeat_ok = True
                    self.heartbeat_failures = 0
                    self.events.put(("connected", True))
                elif "Fusion MCP watchdog: port unavailable" in line or "Fusion/Bridge unavailable" in line:
                    self.events.put(("connected", False))
                if "Bridge heartbeat degraded:" in line:
                    match = re.search(r"failures=(\d+)", line)
                    self.heartbeat_failures = int(match.group(1)) if match else max(1, self.heartbeat_failures + 1)
                    self.heartbeat_ok = False
                elif "Bridge heartbeat recovered" in line:
                    self.heartbeat_failures = 0
                    self.heartbeat_ok = True
                if "Bridge result delivery degraded:" in line or "Bridge result delivery exhausted" in line or "retained in outbox" in line:
                    self.delivery_degraded = True
                    match = re.search(r"outbox=(\d+)", line)
                    self.outbox_count = int(match.group(1)) if match else max(1, self.outbox_count)
                elif "Bridge result delivery recovered:" in line:
                    self.outbox_count = 0
                    self.delivery_degraded = False
                self.events.put(("log", stamped))
        proc.wait()
        self.events.put(("stopped", (proc, proc.returncode)))

    def stop_relay(self) -> None:
        self.supervision_enabled = False
        self.stop_button.configure(state="disabled")
        self._stop_eyes_stack()
        self._stop_hands_stack()
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        self._terminate_owned_process(self.proc)
        self.events.put(("stopped", (proc, proc.returncode)))

    def forget_token(self) -> None:
        try:
            TOKEN_FILE.unlink(missing_ok=True)
            self.token_var.set("")
            self._update_token_state()
        except OSError as exc:
            messagebox.showerror("Fusion Bridge", f"Не удалось удалить сохранённый токен:\n{exc}")

    def open_log(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
        try:
            os.startfile(LOG_FILE)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Fusion Bridge", str(exc))

    def _close(self) -> None:
        self.stop_event.set()
        self.stop_relay()
        self.destroy()


if __name__ == "__main__":
    APP_DIR.mkdir(parents=True, exist_ok=True)
    FusionBridgeGUI().mainloop()

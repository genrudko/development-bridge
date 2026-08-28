from __future__ import annotations

import base64
import ctypes
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk

BRIDGE_HOST = "mcp.vigilante.website"
BRIDGE_URL = "https://mcp.vigilante.website"
NODE_ID = "fusion-workstation"
FUSION_HOST = "127.0.0.1"
FUSION_PORT = 27182
FUSION_URL = "http://127.0.0.1:27182/mcp"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DevelopmentBridgeFusion"
TOKEN_FILE = APP_DIR / "desktop-node-token.dpapi"
LOG_FILE = APP_DIR / "relay.log"
ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "windows_fusion_agent.py"


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
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.connected = False
        self._build()
        self._update_token_state()
        threading.Thread(target=self._status_worker, daemon=True).start()
        self.after(100, self._drain_events)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="ChatGPT ↔ Development Bridge ↔ Autodesk Fusion", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 12))

        status = ttk.LabelFrame(outer, text="Статус", padding=10)
        status.pack(fill="x")
        self.fusion_label = ttk.Label(status, text="Fusion MCP: проверка…")
        self.bridge_label = ttk.Label(status, text="Bridge: проверка…")
        self.relay_label = ttk.Label(status, text="Relay: остановлен")
        self.connection_label = ttk.Label(status, text="Связка: не подключена")
        for widget in (self.fusion_label, self.bridge_label, self.relay_label, self.connection_label):
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
        self.start_button = ttk.Button(buttons, text="▶ Start", command=self.start_relay)
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
            self.events.put(("network", (fusion, bridge)))
            self.stop_event.wait(2.0)

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "network":
                    fusion, bridge = value  # type: ignore[misc]
                    self._set_text(self.fusion_label, "Fusion MCP", bool(fusion), "127.0.0.1:27182 доступен" if fusion else "порт 27182 закрыт")
                    self._set_text(self.bridge_label, "Bridge", bool(bridge), "доступен" if bridge else "недоступен")
                elif kind == "log":
                    self._append_log(str(value))
                elif kind == "connected":
                    self.connected = bool(value)
                elif kind == "stopped":
                    self.proc = None
                    self.connected = False
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                self._refresh_relay_labels()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._drain_events)

    def _refresh_relay_labels(self) -> None:
        running = self.proc is not None and self.proc.poll() is None
        self._set_text(self.relay_label, "Relay", running, "работает" if running else "остановлен")
        self._set_text(self.connection_label, "Связка", running and self.connected, "Fusion подключён к Bridge" if running and self.connected else "ожидание подключения")

    def _append_log(self, line: str) -> None:
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

    def start_relay(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return
        token = self._token_for_start()
        if not token:
            messagebox.showwarning("Fusion Bridge", "Вставь desktop-node token один раз и нажми Start.")
            self.token_entry.focus_set()
            return
        if not AGENT.exists():
            messagebox.showerror("Fusion Bridge", f"Не найден агент:\n{AGENT}")
            return
        APP_DIR.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({
            "DEVELOPMENT_BRIDGE_URL": BRIDGE_URL,
            "DEVELOPMENT_BRIDGE_NODE_ID": NODE_ID,
            "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN": token,
            "FUSION_MCP_URL": FUSION_URL,
            "PYTHONUNBUFFERED": "1",
        })
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        python = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
        self.proc = subprocess.Popen(
            [python, str(AGENT)], cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=creationflags,
        )
        self.token_var.set("")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._append_log("--- relay started ---")
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        self._refresh_relay_labels()

    def _reader(self, proc: subprocess.Popen[str]) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as logfile:
            assert proc.stdout is not None
            for line in proc.stdout:
                logfile.write(line)
                logfile.flush()
                if "Connected: Fusion MCP tools discovered:" in line:
                    self.events.put(("connected", True))
                elif "Fusion/Bridge unavailable" in line:
                    self.events.put(("connected", False))
                self.events.put(("log", line))
        proc.wait()
        self.events.put(("stopped", proc.returncode))

    def stop_relay(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.events.put(("stopped", 0))
            return
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        self.events.put(("stopped", proc.returncode))

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

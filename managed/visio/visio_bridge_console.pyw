from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

CONSOLE_VERSION = "2026.10.02.1"
ROOT = Path(os.environ.get("VISIO_MCP_ROOT", Path(os.environ["LOCALAPPDATA"]) / "OpenAI" / "VisioMCP")).resolve()
START_SCRIPT = ROOT / "START_VISIO_AGENT.ps1"
TEST_SCRIPT = ROOT / "TEST_VISIO_LIVE_BRIDGE.ps1"
COM_LOG = ROOT / "live-bridge-v4.log"
WORKSPACE = ROOT / "workspace"
LOG_DIR = ROOT / "console-logs"
CHAT_ROOT = ROOT / "operator-chat"
PENDING_DIR = CHAT_ROOT / "pending"
ACKED_DIR = CHAT_ROOT / "acked"
REPLIES_DIR = CHAT_ROOT / "replies"

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def existing_agent_pids() -> list[int]:
    script = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -and $_.CommandLine -like '*windows_visio_agent.py*' }; "
        "$p | ForEach-Object { $_.ProcessId }"
    )
    try:
        raw = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=8,
        )
        return [int(line.strip()) for line in raw.splitlines() if line.strip().isdigit()]
    except Exception:
        return []


class VisioBridgeConsole(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Visio Bridge Console  •  {CONSOLE_VERSION}")
        self.geometry("1120x760")
        self.minsize(900, 620)

        for d in (LOG_DIR, PENDING_DIR, ACKED_DIR, REPLIES_DIR, WORKSPACE):
            d.mkdir(parents=True, exist_ok=True)

        self.agent_proc: subprocess.Popen[str] | None = None
        self.agent_queue: queue.Queue[str] = queue.Queue()
        self.agent_log_handle = None
        self.com_log_offset = 0
        self.last_chat_signature: tuple = ()
        self.attach_state = "Не проверено"
        self.bridge_state = "Остановлен"
        self.tool_count: int | None = None
        self._closing = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if is_admin():
            self.admin_label.config(
                text="⚠ Запущено от администратора — START ЗАБЛОКИРОВАН (ROT/UAC)",
                foreground="#b00020",
            )
            self.start_button.config(state="disabled")
        else:
            self.admin_label.config(text="✓ Обычный пользователь (правильный режим)", foreground="#187a2f")

        pids = existing_agent_pids()
        if pids:
            self.bridge_state = "Уже запущен вне Console"
            self._append_agent(f"Найден уже работающий windows_visio_agent.py: PID {', '.join(map(str, pids))}\n")

        self.after(150, self._poll_agent_queue)
        self.after(500, self._poll_com_log)
        self.after(750, self._poll_chat)
        self.after(1000, self._refresh_status)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        self.admin_label = ttk.Label(top, text="")
        self.admin_label.pack(side="left", padx=(0, 18))

        self.agent_status = ttk.Label(top, text="Агент: —")
        self.agent_status.pack(side="left", padx=8)
        self.visio_status = ttk.Label(top, text="Visio: —")
        self.visio_status.pack(side="left", padx=8)
        self.chat_status = ttk.Label(top, text="Сообщения: —")
        self.chat_status.pack(side="left", padx=8)

        controls = ttk.Frame(self, padding=(8, 0, 8, 8))
        controls.pack(fill="x")

        self.start_button = ttk.Button(controls, text="▶ Запустить агент", command=self.start_agent)
        self.start_button.pack(side="left", padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="■ Остановить", command=self.stop_agent)
        self.stop_button.pack(side="left", padx=6)
        ttk.Button(controls, text="✓ Проверить Visio", command=self.test_visio).pack(side="left", padx=6)
        ttk.Button(controls, text="📁 Workspace", command=lambda: self._open_path(WORKSPACE)).pack(side="left", padx=6)
        ttk.Button(controls, text="📁 Логи", command=lambda: self._open_path(LOG_DIR)).pack(side="left", padx=6)
        ttk.Button(controls, text="📁 VisioMCP", command=lambda: self._open_path(ROOT)).pack(side="left", padx=6)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        agent_tab = ttk.Frame(self.tabs)
        com_tab = ttk.Frame(self.tabs)
        chat_tab = ttk.Frame(self.tabs)
        self.tabs.add(agent_tab, text="Агент")
        self.tabs.add(com_tab, text="COM / Live Bridge")
        self.tabs.add(chat_tab, text="Операторский чат")

        self.agent_text = scrolledtext.ScrolledText(agent_tab, wrap="word", font=("Consolas", 10), state="disabled")
        self.agent_text.pack(fill="both", expand=True)
        self.com_text = scrolledtext.ScrolledText(com_tab, wrap="none", font=("Consolas", 10), state="disabled")
        self.com_text.pack(fill="both", expand=True)

        hint = ttk.Label(
            chat_tab,
            text=(
                "Сообщение попадёт в локальную очередь Visio Bridge. ChatGPT увидит его на следующем "
                "инструментальном checkpoint внутри текущего turn. Это не мгновенное прерывание генерации."
            ),
            wraplength=900,
        )
        hint.pack(fill="x", padx=8, pady=(8, 4))

        self.chat_history = scrolledtext.ScrolledText(chat_tab, wrap="word", font=("Segoe UI", 10), state="disabled")
        self.chat_history.pack(fill="both", expand=True, padx=8, pady=4)
        self.chat_history.tag_configure("user", foreground="#0b5394")
        self.chat_history.tag_configure("assistant", foreground="#38761d")
        self.chat_history.tag_configure("pending", foreground="#8a5a00")
        self.chat_history.tag_configure("system", foreground="#666666")

        input_frame = ttk.Frame(chat_tab)
        input_frame.pack(fill="x", padx=8, pady=(4, 8))
        self.chat_input = tk.Text(input_frame, height=4, wrap="word")
        self.chat_input.pack(side="left", fill="x", expand=True)
        self.chat_input.bind("<Control-Return>", lambda _e: self.send_note())
        buttons = ttk.Frame(input_frame)
        buttons.pack(side="left", padx=(8, 0), fill="y")
        ttk.Button(buttons, text="Отправить\nCtrl+Enter", command=self.send_note).pack(fill="x", pady=(0, 4))
        ttk.Button(buttons, text="Очистить историю", command=self.clear_chat_history).pack(fill="x")

    def _append_widget(self, widget: scrolledtext.ScrolledText, text: str, tag: str | None = None) -> None:
        widget.configure(state="normal")
        widget.insert("end", text, tag or ())
        widget.see("end")
        widget.configure(state="disabled")

    def _append_agent(self, text: str) -> None:
        self._append_widget(self.agent_text, text)

    def _append_com(self, text: str) -> None:
        self._append_widget(self.com_text, text)

    def _open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))

    def start_agent(self) -> None:
        if is_admin():
            messagebox.showerror("Нельзя", "Запусти Visio Bridge Console НЕ от администратора.")
            return
        if self.agent_proc is not None and self.agent_proc.poll() is None:
            return
        pids = existing_agent_pids()
        if pids:
            messagebox.showwarning(
                "Агент уже работает",
                "Найден windows_visio_agent.py вне этой Console.\n\nPID: " + ", ".join(map(str, pids)) +
                "\n\nЗакрой старое PowerShell-окно/агент и нажми Запустить ещё раз.",
            )
            return
        if not START_SCRIPT.exists():
            messagebox.showerror("Нет START script", str(START_SCRIPT))
            return

        log_path = LOG_DIR / ("agent-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log")
        self.agent_log_handle = log_path.open("a", encoding="utf-8", buffering=1)
        self._append_agent(f"\n=== START {now_iso()} ===\nLOG={log_path}\n")
        try:
            self.agent_proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as exc:
            self.agent_proc = None
            messagebox.showerror("Не удалось запустить агент", str(exc))
            return

        self.bridge_state = "Запускается"
        self.tool_count = None
        threading.Thread(target=self._agent_reader, daemon=True).start()

    def _agent_reader(self) -> None:
        proc = self.agent_proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                if self.agent_log_handle:
                    self.agent_log_handle.write(line)
                self.agent_queue.put(line)
        finally:
            code = proc.wait()
            self.agent_queue.put(f"\n=== AGENT EXIT code={code} {now_iso()} ===\n")
            if self.agent_log_handle:
                try:
                    self.agent_log_handle.close()
                except Exception:
                    pass
                self.agent_log_handle = None

    def _poll_agent_queue(self) -> None:
        try:
            while True:
                line = self.agent_queue.get_nowait()
                self._append_agent(line)
                if "Connected: Visio MCP tools discovered:" in line:
                    try:
                        self.tool_count = int(line.rsplit(":", 1)[1].strip())
                    except Exception:
                        self.tool_count = None
                    self.bridge_state = "ONLINE"
                elif "heartbeat degraded" in line.lower():
                    self.bridge_state = "DEGRADED"
                elif "Visio/Bridge unavailable" in line:
                    self.bridge_state = "RECONNECTING"
        except queue.Empty:
            pass
        self.after(120, self._poll_agent_queue)

    def stop_agent(self) -> None:
        proc = self.agent_proc
        if proc is None or proc.poll() is not None:
            self.agent_proc = None
            return
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.bridge_state = "Остановлен"
        self.tool_count = None
        self.agent_proc = None

    def test_visio(self) -> None:
        if is_admin():
            messagebox.showerror("Нельзя", "Диагностику live attach тоже запускай в non-admin контексте.")
            return
        if not TEST_SCRIPT.exists():
            messagebox.showerror("Нет test script", str(TEST_SCRIPT))
            return
        self._append_agent(f"\n=== VISIO TEST {now_iso()} ===\n")
        threading.Thread(target=self._run_visio_test, daemon=True).start()

    def _run_visio_test(self) -> None:
        try:
            cp = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TEST_SCRIPT)],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=45,
            )
            text = (cp.stdout or "") + (cp.stderr or "")
            self.agent_queue.put(text)
            self.attach_state = "PASS" if "VISIO_LIVE_APPLICATION=PASS" in text else "FAIL"
        except Exception as exc:
            self.attach_state = "FAIL"
            self.agent_queue.put(f"VISIO TEST ERROR: {exc}\n")

    def _poll_com_log(self) -> None:
        try:
            if COM_LOG.exists():
                size = COM_LOG.stat().st_size
                if size < self.com_log_offset:
                    self.com_log_offset = 0
                with COM_LOG.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.com_log_offset)
                    chunk = f.read()
                    self.com_log_offset = f.tell()
                if chunk:
                    self._append_com(chunk)
        except Exception:
            pass
        self.after(900, self._poll_com_log)

    def send_note(self) -> None:
        text = self.chat_input.get("1.0", "end").strip()
        if not text:
            return
        if len(text) > 8000:
            messagebox.showwarning("Слишком длинно", "Максимум 8000 символов на одно сообщение.")
            return
        note_id = "note-" + uuid.uuid4().hex
        payload = {
            "id": note_id,
            "created_at": now_iso(),
            "text": text,
            "source": "visio-bridge-console",
            "console_version": CONSOLE_VERSION,
        }
        atomic_json(PENDING_DIR / f"{note_id}.json", payload)
        self.chat_input.delete("1.0", "end")
        self._poll_chat(force=True)

    def clear_chat_history(self) -> None:
        if not messagebox.askyesno("Очистить историю", "Удалить прочитанные сообщения и ответы? Непрочитанные останутся."):
            return
        for directory in (ACKED_DIR, REPLIES_DIR):
            for path in directory.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
        self._poll_chat(force=True)

    def _chat_rows(self) -> list[tuple[str, dict, str]]:
        rows: list[tuple[str, dict, str]] = []
        for status, directory in (("pending", PENDING_DIR), ("acked", ACKED_DIR), ("reply", REPLIES_DIR)):
            for path in directory.glob("*.json"):
                payload = load_json(path)
                if payload:
                    rows.append((status, payload, path.name))
        rows.sort(key=lambda row: (str(row[1].get("created_at", "")), row[2]))
        return rows

    def _poll_chat(self, force: bool = False) -> None:
        rows = self._chat_rows()
        signature = tuple((status, payload.get("id"), payload.get("created_at"), payload.get("text")) for status, payload, _ in rows)
        if force or signature != self.last_chat_signature:
            self.last_chat_signature = signature
            self.chat_history.configure(state="normal")
            self.chat_history.delete("1.0", "end")
            for status, payload, _ in rows:
                stamp = str(payload.get("created_at", ""))[11:19]
                text = str(payload.get("text", ""))
                if status == "reply":
                    self.chat_history.insert("end", f"[{stamp}] ChatGPT:\n", "assistant")
                    self.chat_history.insert("end", text + "\n\n", "assistant")
                else:
                    marker = "⏳ ожидает" if status == "pending" else "✓ прочитано"
                    tag = "pending" if status == "pending" else "user"
                    self.chat_history.insert("end", f"[{stamp}] Вы ({marker}):\n", tag)
                    self.chat_history.insert("end", text + "\n\n", tag)
            self.chat_history.see("end")
            self.chat_history.configure(state="disabled")
        if not self._closing:
            self.after(900, self._poll_chat)

    def _refresh_status(self) -> None:
        proc_running = self.agent_proc is not None and self.agent_proc.poll() is None
        if proc_running:
            suffix = f" / {self.tool_count} tools" if self.tool_count is not None else ""
            agent = f"Агент: {self.bridge_state}{suffix}"
        else:
            external = existing_agent_pids()
            agent = "Агент: вне Console" if external else "Агент: остановлен"
        pending = len(list(PENDING_DIR.glob("*.json")))
        self.agent_status.config(text=agent)
        self.visio_status.config(text=f"Visio live attach: {self.attach_state}")
        self.chat_status.config(text=f"Сообщения: {pending} ожидают")
        if not self._closing:
            self.after(2500, self._refresh_status)

    def _on_close(self) -> None:
        running = self.agent_proc is not None and self.agent_proc.poll() is None
        if running:
            answer = messagebox.askyesnocancel(
                "Закрыть Visio Bridge Console",
                "Агент запущен.\n\nДа — остановить агент и закрыть.\nНет — оставить агент работать и закрыть Console.\nОтмена — не закрывать.",
            )
            if answer is None:
                return
            if answer:
                self.stop_agent()
        self._closing = True
        self.destroy()


if __name__ == "__main__":
    VisioBridgeConsole().mainloop()

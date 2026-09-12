"""Tk operator console for the Windows Blender Hub."""
from __future__ import annotations

import argparse
import asyncio
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import tkinter as tk
from tkinter import ttk

from app.blender_bridge.operator_inbox import InboxPrompt, OperatorInboxBackend
from agents.blender_hub_runtime import run


class BlenderHubGui:
    def __init__(
        self,
        root: tk.Tk,
        *,
        bridge_url: str,
        node_id: str,
        token: str,
        providers: Path,
    ) -> None:
        self.root = root
        self.bridge_url = bridge_url
        self.node_id = node_id
        self.token = token
        self.providers = providers
        self.operator = OperatorInboxBackend(timeout_seconds=285.0)
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.current_prompt: InboxPrompt | None = None
        self.worker_loop: asyncio.AbstractEventLoop | None = None
        self.worker_task: asyncio.Task[None] | None = None
        self.worker_lock = threading.Lock()
        self.worker: threading.Thread | None = None

        self.status_var = tk.StringVar(value="Starting Blender Hub…")
        self.prompt_var = tk.StringVar(value="No operator question pending")
        self.operation_var = tk.StringVar(value="")
        self.reply_var = tk.StringVar(value="")
        self.choice_frame: ttk.Frame
        self.transcript: tk.Text
        self.reply_entry: ttk.Entry
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll)
        self._start_worker()

    def _build_ui(self) -> None:
        self.root.title("Blender Bridge / Hub")
        self.root.geometry("760x560")
        self.root.minsize(620, 430)

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Blender Bridge / Hub", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(2, 10))

        self.transcript = tk.Text(outer, height=16, wrap="word", state="disabled")
        self.transcript.pack(fill="both", expand=True)

        prompt_box = ttk.LabelFrame(outer, text="Operator inbox", padding=10)
        prompt_box.pack(fill="x", pady=(10, 0))
        ttk.Label(prompt_box, textvariable=self.prompt_var, wraplength=700).pack(anchor="w")
        ttk.Label(prompt_box, textvariable=self.operation_var).pack(anchor="w", pady=(2, 6))

        self.choice_frame = ttk.Frame(prompt_box)
        self.choice_frame.pack(fill="x", pady=(0, 6))

        reply_row = ttk.Frame(prompt_box)
        reply_row.pack(fill="x")
        self.reply_entry = ttk.Entry(reply_row, textvariable=self.reply_var)
        self.reply_entry.pack(side="left", fill="x", expand=True)
        self.reply_entry.bind("<Return>", lambda _event: self._send_text())
        ttk.Button(reply_row, text="Send", command=self._send_text).pack(side="left", padx=(8, 0))

    def _append(self, author: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{author}: {text}\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _start_worker(self) -> None:
        def worker_main() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = loop.create_task(
                run(
                    bridge_url=self.bridge_url,
                    node_id=self.node_id,
                    token=self.token,
                    provider_config_path=self.providers,
                    heartbeat_seconds=10.0,
                    claim_wait_seconds=20.0,
                    operator=self.operator,
                    status_sink=self.events.put,
                )
            )
            with self.worker_lock:
                self.worker_loop = loop
                self.worker_task = task
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                self.events.put({
                    "type": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                })
            finally:
                with self.worker_lock:
                    self.worker_task = None
                    self.worker_loop = None
                loop.close()

        self.worker = threading.Thread(target=worker_main, name="BlenderHubRuntime", daemon=True)
        self.worker.start()

    def _poll(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event.get("type") == "connected":
                providers = event.get("providers", [])
                online = [item["namespace"] for item in providers if item.get("connected")]
                offline = [item["namespace"] for item in providers if not item.get("connected")]
                suffix = f"; offline: {', '.join(offline)}" if offline else ""
                self.status_var.set(
                    f"Connected · tools {event.get('tool_count', 0)} · providers: {', '.join(online) or 'none'}{suffix}"
                )
            elif event.get("type") == "error":
                self.status_var.set("Hub stopped with error")
                self._append("Hub", str(event.get("message", "unknown error")))

        if self.current_prompt is not None:
            if self.current_prompt.prompt_id not in self.operator.pending_prompt_ids():
                self._append("Hub", "Operator prompt expired or was cancelled")
                self._clear_prompt()

        if self.current_prompt is None:
            prompt = self.operator.next_prompt()
            if prompt is not None:
                self._show_prompt(prompt)

        if self.root.winfo_exists():
            self.root.after(100, self._poll)

    def _show_prompt(self, prompt: InboxPrompt) -> None:
        self.current_prompt = prompt
        self.prompt_var.set(prompt.question)
        self.operation_var.set(
            f"Operation: {prompt.operation_id}" if prompt.operation_id else ""
        )
        self._append("Agent", prompt.question)
        for child in self.choice_frame.winfo_children():
            child.destroy()
        for choice in prompt.choices:
            ttk.Button(
                self.choice_frame,
                text=choice,
                command=lambda value=choice: self._answer(value),
            ).pack(side="left", padx=(0, 6))
        self.reply_entry.focus_set()

    def _send_text(self) -> None:
        value = self.reply_var.get().strip()
        if value:
            self._answer(value)

    def _answer(self, value: str) -> None:
        prompt = self.current_prompt
        if prompt is None:
            return
        if self.operator.answer(prompt.prompt_id, value):
            self._append("You", value)
        else:
            self._append("Hub", "Prompt was no longer pending")
        self.reply_var.set("")
        self._clear_prompt()

    def _clear_prompt(self) -> None:
        self.current_prompt = None
        self.prompt_var.set("No operator question pending")
        self.operation_var.set("")
        for child in self.choice_frame.winfo_children():
            child.destroy()

    def _close(self) -> None:
        with self.worker_lock:
            loop = self.worker_loop
            task = self.worker_task
        if loop is not None and task is not None and not task.done():
            loop.call_soon_threadsafe(task.cancel)
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blender Bridge / Hub GUI")
    parser.add_argument("--bridge-url", default=os.environ.get("DEVELOPMENT_BRIDGE_URL"))
    parser.add_argument("--node-id", default="blender-workstation")
    parser.add_argument(
        "--providers",
        type=Path,
        default=Path(__file__).with_name("blender_hub_providers.json"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    token = os.environ.get("DEVELOPMENT_BRIDGE_DESKTOP_TOKEN")
    if not args.bridge_url:
        raise SystemExit("DEVELOPMENT_BRIDGE_URL or --bridge-url is required")
    if not token:
        raise SystemExit("DEVELOPMENT_BRIDGE_DESKTOP_TOKEN is required")
    root = tk.Tk()
    BlenderHubGui(
        root,
        bridge_url=args.bridge_url,
        node_id=args.node_id,
        token=token,
        providers=args.providers,
    )
    root.mainloop()


if __name__ == "__main__":
    main()

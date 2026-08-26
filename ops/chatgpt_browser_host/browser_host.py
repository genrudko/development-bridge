#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import signal
from secrets import token_urlsafe
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import websocket

TRANSIENT_CDP_ERRORS = (
    OSError,
    TimeoutError,
    requests.RequestException,
    getattr(websocket, "WebSocketException", OSError),
)


@dataclass(frozen=True)
class Config:
    chrome: str
    chrome_lib: str
    xvfb: str
    xvfb_lib: str
    profile: str
    display: str
    debug_port: int
    target_url: str
    route_id: str
    channel_id: str
    public_ip: str
    bridge_unit: str
    coordinator_local_url: str
    check_interval: float
    startup_timeout: float
    poll_window: int
    poll_grace: float
    listener_recovery_timeout: float
    state_dir: Path
    route_registry: Path
    chat_registry: Path
    discovery_interval: float

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def lock_file(self) -> Path:
        return self.state_dir / "browser-host.lock"

    @property
    def web_backoff_file(self) -> Path:
        return self.state_dir.parent / "web-backoff.json"


def env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def canonical_chat_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.netloc != "chatgpt.com":
        raise ValueError("BROWSER_HOST_TARGET_URL must be an https://chatgpt.com URL")
    if "/c/" not in parts.path:
        raise ValueError("BROWSER_HOST_TARGET_URL must point to a ChatGPT conversation")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def is_target_url(value: str, target: str) -> bool:
    try:
        return canonical_chat_url(value) == target
    except ValueError:
        return False


def load_config() -> Config:
    home = Path.home()
    chrome_base = home / ".local/chrome-cft"
    state_dir = Path(env(
        "BROWSER_HOST_STATE_DIR",
        str(home / ".local/state/development-bridge/browser-host"),
    ))
    target = env("BROWSER_HOST_TARGET_URL", "")
    if not target:
        raise ValueError("BROWSER_HOST_TARGET_URL is required")
    return Config(
        chrome=env("BROWSER_HOST_CHROME", str(chrome_base / "chrome-linux64/chrome")),
        chrome_lib=env(
            "BROWSER_HOST_CHROME_LIB",
            str(chrome_base / "runtime-libs/usr/lib/x86_64-linux-gnu"),
        ),
        xvfb=env(
            "BROWSER_HOST_XVFB",
            str(home / ".local/xvfb-local/root/usr/bin/Xvfb"),
        ),
        xvfb_lib=env(
            "BROWSER_HOST_XVFB_LIB",
            str(home / ".local/xvfb-local/root/usr/lib/x86_64-linux-gnu"),
        ),
        profile=env("BROWSER_HOST_PROFILE", str(chrome_base / "profile")),
        display=env("BROWSER_HOST_DISPLAY", ":99"),
        debug_port=int(env("BROWSER_HOST_DEBUG_PORT", "9222")),
        target_url=canonical_chat_url(target),
        route_id=env("BROWSER_HOST_ROUTE_ID", "ad5x"),
        channel_id=env("BROWSER_HOST_CHANNEL_ID", "telegram-supervisor"),
        public_ip=env("BROWSER_HOST_PUBLIC_IP", ""),
        bridge_unit=env("BROWSER_HOST_BRIDGE_UNIT", "development-bridge.service"),
        coordinator_local_url=env(
            "BROWSER_HOST_COORDINATOR_LOCAL_URL",
            "http://127.0.0.1:8789/mcp/x/coordinator/",
        ).rstrip("/") + "/",
        check_interval=float(env("BROWSER_HOST_CHECK_INTERVAL", "5")),
        startup_timeout=float(env("BROWSER_HOST_STARTUP_TIMEOUT", "45")),
        poll_window=int(env("BROWSER_HOST_POLL_WINDOW", "15")),
        poll_grace=float(env("BROWSER_HOST_POLL_GRACE", "45")),
        listener_recovery_timeout=float(env("BROWSER_HOST_LISTENER_RECOVERY_TIMEOUT", "120")),
        state_dir=state_dir,
        route_registry=Path(env("BROWSER_HOST_ROUTE_REGISTRY", str(home / ".local/state/development-bridge/routes.json"))),
        chat_registry=Path(env("BROWSER_HOST_CHAT_REGISTRY", str(home / ".local/state/development-bridge/chat-registry.json"))),
        discovery_interval=float(env("BROWSER_HOST_DISCOVERY_INTERVAL", "60")),
    )


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def terminate(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=8)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


class BrowserHost:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.stop = False
        self.xvfb: subprocess.Popen | None = None
        self.chrome: subprocess.Popen | None = None
        self.repair_count = 0
        self.listener_recovery_count = 0
        self.route_id = cfg.route_id
        self.target_url = cfg.target_url
        self.channel_id = cfg.channel_id
        self.last_discovery = 0.0
        self.discovered_chats = 0
        self.route_generation = 0
        self.rate_limit_count = 0
        self.rate_limit_until = 0.0
        self.last_bridge_turn_id = 0
        self.last_bridge_turn_key: str | None = None
        self.bridge_turn_baselined = False
        self.model_turn_observation_count = 0
        self.rollover_count = 0
        self.rollover_abort_count = 0

    @property
    def cdp_base(self) -> str:
        return f"http://127.0.0.1:{self.cfg.debug_port}"

    def write_state(self, **extra) -> None:
        payload = {
            "updated_at": utcnow(),
            "route_id": self.route_id,
            "channel_id": self.channel_id,
            "target_url": self.target_url,
            "route_generation": self.route_generation,
            "xvfb_pid": self.xvfb.pid if self.xvfb and self.xvfb.poll() is None else None,
            "chrome_pid": self.chrome.pid if self.chrome and self.chrome.poll() is None else None,
            "repair_count": self.repair_count,
            "listener_recovery_count": self.listener_recovery_count,
            "discovered_chats": self.discovered_chats,
            "last_bridge_turn_id": self.last_bridge_turn_id,
            "last_bridge_turn_key": self.last_bridge_turn_key,
            "bridge_turn_baselined": self.bridge_turn_baselined,
            "model_turn_observation_count": self.model_turn_observation_count,
            "rollover_count": self.rollover_count,
            "rollover_abort_count": self.rollover_abort_count,
        }
        payload.update(extra)
        atomic_json(self.cfg.state_file, payload)

    def ensure_debug_port_free(self) -> None:
        try:
            response = requests.get(f"{self.cdp_base}/json/version", timeout=1)
        except requests.RequestException:
            return
        if response.ok:
            raise RuntimeError(
                f"debug port {self.cfg.debug_port} is already in use; stop the old browser host first"
            )

    def start_xvfb(self) -> None:
        xvfb_env = os.environ.copy()
        xvfb_env["LD_LIBRARY_PATH"] = self.cfg.xvfb_lib + (
            ":" + xvfb_env["LD_LIBRARY_PATH"] if xvfb_env.get("LD_LIBRARY_PATH") else ""
        )
        self.xvfb = subprocess.Popen(
            [
                self.cfg.xvfb,
                self.cfg.display,
                "-screen", "0", "1280x900x24",
                "-nolisten", "tcp",
                "-ac",
            ],
            env=xvfb_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        time.sleep(1)
        if self.xvfb.poll() is not None:
            raise RuntimeError("Xvfb exited during startup")

    def start_chrome(self) -> None:
        chrome_env = os.environ.copy()
        chrome_env["DISPLAY"] = self.cfg.display
        libs = [self.cfg.chrome_lib, self.cfg.xvfb_lib]
        if chrome_env.get("LD_LIBRARY_PATH"):
            libs.append(chrome_env["LD_LIBRARY_PATH"])
        chrome_env["LD_LIBRARY_PATH"] = ":".join(libs)
        Path(self.cfg.profile).mkdir(parents=True, exist_ok=True)
        self.chrome = subprocess.Popen(
            [
                self.cfg.chrome,
                f"--user-data-dir={self.cfg.profile}",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.cfg.debug_port}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-dev-shm-usage",
                "--disable-session-crashed-bubble",
                "--window-size=1280,900",
                self.target_url,
            ],
            env=chrome_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def wait_cdp(self) -> None:
        deadline = time.monotonic() + self.cfg.startup_timeout
        while time.monotonic() < deadline:
            if self.chrome and self.chrome.poll() is not None:
                raise RuntimeError("Chrome exited during startup")
            try:
                response = requests.get(f"{self.cdp_base}/json/version", timeout=1)
                if response.ok:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
        raise RuntimeError("Chrome DevTools endpoint did not become ready")

    def pages(self) -> list[dict]:
        response = requests.get(f"{self.cdp_base}/json/list", timeout=2)
        response.raise_for_status()
        return [
            item for item in response.json()
            if item.get("type") == "page" and item.get("url", "").startswith("https://chatgpt.com")
        ]

    def create_blank_page(self) -> dict:
        response = requests.put(f"{self.cdp_base}/json/new?about:blank", timeout=2)
        response.raise_for_status()
        page = response.json()
        if (
            not isinstance(page, dict)
            or not page.get("id")
            or not page.get("webSocketDebuggerUrl")
        ):
            raise RuntimeError("Chrome did not create a debuggable page")
        return page

    def navigate(self, page: dict, url: str) -> None:
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"],
            timeout=4,
            suppress_origin=True,
        )
        try:
            request_id = int(time.time() * 1000) % 1_000_000_000
            ws.send(json.dumps({
                "id": request_id,
                "method": "Page.navigate",
                "params": {"url": url},
            }))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    return
        finally:
            ws.close()

    def close_page(self, page_id: str) -> None:
        try:
            requests.get(f"{self.cdp_base}/json/close/{page_id}", timeout=2)
        except requests.RequestException:
            pass

    def coordinator_iframe_count(self, page: dict) -> int:
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=4, suppress_origin=True
        )
        try:
            request_id = int(time.time() * 1000) % 1_000_000_000
            expression = (
                "[...document.querySelectorAll('iframe')]"
                ".filter(f=>f.title.startsWith('ui://development-bridge/coordinator-x-v')&&f.title.endsWith('.html')).length"
            )
            ws.send(json.dumps({
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    return int(
                        message.get("result", {})
                        .get("result", {})
                        .get("value", 0)
                    )
        finally:
            ws.close()

    def safe_coordinator_iframe_count(self, page: dict) -> tuple[int | None, str | None]:
        try:
            return self.coordinator_iframe_count(page), None
        except TRANSIENT_CDP_ERRORS as exc:
            return None, str(exc)

    def rate_limit_detected(self, page: dict) -> bool:
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=4, suppress_origin=True
        )
        try:
            request_id = int(time.time() * 1000) % 1_000_000_000
            expression = r'''(()=>{const dialogs=[...document.querySelectorAll('[role="dialog"],[role="alertdialog"]')].filter(e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>180&&r.height>80&&s.visibility!=="hidden"&&s.display!=="none";});const needles=["слишком много запросов","вы отправляете запросы слишком часто","доступ к вашим диалогам временно ограничен","too many requests","sending requests too frequently","access to your conversations is temporarily restricted"];return dialogs.some(e=>{const t=(e.innerText||e.textContent||"").toLowerCase();return needles.some(n=>t.includes(n));});})()'''
            ws.send(json.dumps({"id": request_id, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}}))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    return bool(message.get("result", {}).get("result", {}).get("value", False))
        finally:
            ws.close()

    def activate_web_backoff(self) -> float:
        now = time.time()
        if now >= self.rate_limit_until:
            self.rate_limit_count += 1
            delay = min(300.0, 120.0 * (2 ** min(self.rate_limit_count - 1, 2)))
            self.rate_limit_until = now + delay
            atomic_json(self.cfg.web_backoff_file, {
                "version": 1,
                "reason": "chatgpt_rate_limit",
                "detected_at": utcnow(),
                "until": self.rate_limit_until,
                "attempt": self.rate_limit_count,
            })
        return max(0.0, self.rate_limit_until - now)

    def bridge_turn_state(self, page: dict) -> dict:
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=4, suppress_origin=True
        )
        try:
            request_id = int(time.time() * 1000) % 1_000_000_000
            expression = r'''(()=>{
              const generating=[...document.querySelectorAll('button')].some(b=>{
                const text=((b.getAttribute('aria-label')||'')+' '+(b.innerText||'')).toLowerCase();
                return text.includes('stop generating')||text.includes('stop streaming')||text.includes('остановить');
              });
              let turnId=0;
              let turnKey=null;
              for(const turn of document.querySelectorAll('[data-testid^="conversation-turn-"]')){
                const match=(turn.getAttribute('data-testid')||'').match(/^conversation-turn-(\d+)$/);
                if(!match) continue;
                const tool=turn.querySelector('[data-message-author-role="tool"]');
                const assistant=turn.querySelector('[data-message-author-role="assistant"]');
                const toolText=(tool?.innerText||tool?.textContent||'').trim();
                const assistantText=(assistant?.innerText||assistant?.textContent||'').trim();
                if(toolText.startsWith('⚡ Bridge · задача завершена') && assistantText){
                  turnId=Number(match[1]);
                  turnKey=turn.getAttribute('data-turn-id')||turn.getAttribute('data-turn-id-container')||match[0];
                }
              }
              return {turn_id:turnId,turn_key:turnKey,generating};
            })()'''
            ws.send(json.dumps({
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    value = (
                        message.get("result", {})
                        .get("result", {})
                        .get("value", {})
                    ) or {}
                    turn_key = value.get("turn_key")
                    return {
                        "turn_id": int(value.get("turn_id", 0) or 0),
                        "turn_key": str(turn_key) if turn_key else None,
                        "generating": bool(value.get("generating", False)),
                    }
        finally:
            ws.close()

    def safe_bridge_turn_state(self, page: dict) -> tuple[dict | None, str | None]:
        try:
            return self.bridge_turn_state(page), None
        except TRANSIENT_CDP_ERRORS as exc:
            return None, str(exc)

    def coordinator_local_status(self) -> dict:
        response = requests.get(
            self.cfg.coordinator_local_url + "status",
            params={"channel_id": self.channel_id},
            timeout=2,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def observe_model_turn_local(self, continuation_id: str) -> dict:
        response = requests.post(
            self.cfg.coordinator_local_url + "observed",
            params={
                "channel_id": self.channel_id,
                "continuation_id": continuation_id,
            },
            timeout=2,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def authorize_browser_preflight_local(self, continuation_id: str) -> dict:
        response = requests.post(
            self.cfg.coordinator_local_url + "preflight/authorize",
            params={
                "channel_id": self.channel_id,
                "continuation_id": continuation_id,
            },
            timeout=2,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def refresh_conversation_snapshot(self, page: dict, timeout: float = 30) -> dict:
        conversation_id = self.target_url.split("/c/", 1)[1].split("/", 1)[0]
        expected_path = f"/backend-api/conversations/{conversation_id}"
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=max(8.0, timeout), suppress_origin=True
        )
        try:
            request_base = int(time.time() * 1_000_000) % 900_000_000
            commands = (
                (request_base + 1, "Network.enable", {}),
                (request_base + 2, "Network.setCacheDisabled", {"cacheDisabled": True}),
                (request_base + 3, "Page.navigate", {"url": self.target_url}),
            )
            for request_id, method, params in commands:
                ws.send(json.dumps({"id": request_id, "method": method, "params": params}))

            deadline = time.monotonic() + timeout
            conversation_request_id = None
            loaded = False
            while time.monotonic() < deadline:
                event = json.loads(ws.recv())
                method = event.get("method")
                params = event.get("params", {})
                if method == "Network.responseReceived":
                    response = params.get("response", {})
                    response_url = str(response.get("url") or "")
                    if (
                        urlsplit(response_url).path == expected_path
                        and int(response.get("status", 0) or 0) == 200
                    ):
                        conversation_request_id = params.get("requestId")
                elif (
                    conversation_request_id
                    and method == "Network.loadingFinished"
                    and params.get("requestId") == conversation_request_id
                ):
                    loaded = True
                    break
            if not conversation_request_id or not loaded:
                return {"ok": False, "error": "conversation_snapshot_not_loaded"}

            body_request_id = request_base + 4
            ws.send(json.dumps({
                "id": body_request_id,
                "method": "Network.getResponseBody",
                "params": {"requestId": conversation_request_id},
            }))
            body_result = None
            body_deadline = time.monotonic() + min(10.0, timeout)
            while time.monotonic() < body_deadline:
                event = json.loads(ws.recv())
                if event.get("id") == body_request_id:
                    body_result = event.get("result", {})
                    break
            if not isinstance(body_result, dict) or not body_result.get("body"):
                return {"ok": False, "error": "conversation_snapshot_body_missing"}
            raw_body = str(body_result["body"])
            if body_result.get("base64Encoded"):
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            return self.parse_conversation_snapshot(json.loads(raw_body))
        finally:
            ws.close()

    @staticmethod
    def parse_conversation_snapshot(payload: object) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "conversation_snapshot_invalid"}
        current_node = payload.get("current_node")
        messages = payload.get("messages")
        if not isinstance(current_node, str) or not isinstance(messages, list):
            return {"ok": False, "error": "conversation_snapshot_invalid"}
        current_message = next(
            (item for item in messages if isinstance(item, dict) and item.get("id") == current_node),
            None,
        )
        if current_message is None:
            return {
                "ok": False,
                "error": "conversation_current_node_missing",
                "current_node": current_node,
            }
        author = current_message.get("author")
        return {
            "ok": True,
            "current_node": current_node,
            "current_role": author.get("role") if isinstance(author, dict) else None,
            "current_status": current_message.get("status"),
            "current_end_turn": current_message.get("end_turn"),
            "current_recipient": current_message.get("recipient"),
            "current_channel": current_message.get("channel"),
            "message_count": len(messages),
        }

    def conversation_leaf_state(self, page: dict) -> dict:
        expression = r'''(()=>{
          const generating=[...document.querySelectorAll('button')].some(b=>{
            const text=((b.getAttribute('aria-label')||'')+' '+(b.innerText||'')).toLowerCase();
            return text.includes('stop generating')||text.includes('stop streaming')||text.includes('остановить');
          });
          const turns=[...document.querySelectorAll('[data-testid^="conversation-turn-"]')];
          const last=turns.at(-1)||null;
          const assistant=last?.querySelector('[data-message-author-role="assistant"]')||null;
          const user=last?.querySelector('[data-message-author-role="user"]')||null;
          const tool=last?.querySelector('[data-message-author-role="tool"]')||null;
          const message=last?.querySelector('[data-message-id]')||null;
          const assistantText=(assistant?.innerText||assistant?.textContent||'').trim();
          return {
            document_ready:document.readyState,
            generating,
            turn_count:turns.length,
            last_key:last?.getAttribute('data-turn-id')||last?.getAttribute('data-turn-id-container')||last?.getAttribute('data-testid')||null,
            last_message_id:message?.getAttribute('data-message-id')||null,
            has_user:!!user,
            has_tool:!!tool,
            has_assistant:!!assistant,
            assistant_chars:assistantText.length,
            settled:document.readyState==='complete'&&!generating&&!!assistant&&assistantText.length>0
          };
        })()'''
        value = self.runtime_evaluate(page, expression)
        return value if isinstance(value, dict) else {}

    def wait_for_settled_conversation(
        self, page: dict, timeout: float = 30, *, expected_message_id: str | None = None
    ) -> dict:
        deadline = time.monotonic() + timeout
        last: dict = {}
        while time.monotonic() < deadline:
            try:
                last = self.conversation_leaf_state(page)
            except TRANSIENT_CDP_ERRORS as exc:
                last = {"settled": False, "error": str(exc)}
            current = (
                expected_message_id is None
                or last.get("last_message_id") == expected_message_id
            )
            last["current"] = current
            if last.get("settled") is True and current:
                return last
            time.sleep(0.75)
        return last

    def prepare_browser_preflight(self, page: dict, continuation_id: str) -> dict:
        fresh_page: dict | None = None
        keep_fresh_page = False
        try:
            fresh_page = self.create_blank_page()
            snapshot = self.refresh_conversation_snapshot(fresh_page, timeout=30)
            if not snapshot.get("ok"):
                return {
                    "authorized": False,
                    "error": snapshot.get("error") or "conversation_snapshot_failed",
                    "snapshot": snapshot,
                }
            if not (
                snapshot.get("current_role") == "assistant"
                and snapshot.get("current_status") == "finished_successfully"
                and snapshot.get("current_end_turn") is True
                and snapshot.get("current_recipient") == "all"
                and snapshot.get("current_channel") == "final"
            ):
                return {
                    "authorized": False,
                    "error": "conversation_server_leaf_not_final",
                    "snapshot": snapshot,
                }

            leaf = self.wait_for_settled_conversation(
                fresh_page, timeout=30, expected_message_id=str(snapshot["current_node"])
            )
            if leaf.get("settled") is not True:
                return {
                    "authorized": False,
                    "error": "conversation_leaf_not_settled",
                    "leaf": leaf,
                    "snapshot": snapshot,
                }
            if leaf.get("current") is not True:
                return {
                    "authorized": False,
                    "error": "conversation_leaf_not_current",
                    "leaf": leaf,
                    "snapshot": snapshot,
                }

            iframe_count, iframe_error = self.safe_coordinator_iframe_count(fresh_page)
            if iframe_count is None:
                return {
                    "authorized": False,
                    "error": iframe_error or "coordinator_iframe_probe_failed",
                    "leaf": leaf,
                    "snapshot": snapshot,
                }
            if iframe_count == 0:
                try:
                    recovered = self.recover_listener(fresh_page)
                except TRANSIENT_CDP_ERRORS as exc:
                    return {
                        "authorized": False,
                        "error": f"listener_recovery_failed: {exc}",
                        "leaf": leaf,
                        "snapshot": snapshot,
                    }
                if not recovered:
                    return {
                        "authorized": False,
                        "error": "coordinator_iframe_not_recovered",
                        "leaf": leaf,
                        "snapshot": snapshot,
                    }

            old_page_id = str(page.get("id") or "")
            fresh_page_id = str(fresh_page.get("id") or "")
            if old_page_id and fresh_page_id and old_page_id != fresh_page_id:
                self.close_page(old_page_id)
            keep_fresh_page = True

            poll_ok, poll_detail = self.wait_for_polling(self.channel_id, timeout=20)
            if not poll_ok:
                return {
                    "authorized": False,
                    "error": f"coordinator_polling_not_observed: {poll_detail}",
                    "leaf": leaf,
                    "snapshot": snapshot,
                    "fresh_page_id": fresh_page_id,
                }
            authorized = self.authorize_browser_preflight_local(continuation_id)
            return {
                **authorized,
                "leaf": leaf,
                "snapshot": snapshot,
                "polling_detail": poll_detail,
                "fresh_page_id": fresh_page_id,
            }
        finally:
            if fresh_page is not None and not keep_fresh_page:
                fresh_page_id = str(fresh_page.get("id") or "")
                old_page_id = str(page.get("id") or "")
                if fresh_page_id and fresh_page_id != old_page_id:
                    self.close_page(fresh_page_id)

    def sync_model_turn_observation(self, page: dict) -> dict | None:
        state, error = self.safe_bridge_turn_state(page)
        if state is None:
            raise RuntimeError(f"transient model-turn probe failed: {error}")
        latest = int(state.get("turn_id", 0) or 0)
        latest_key = state.get("turn_key")
        if not self.bridge_turn_baselined:
            self.last_bridge_turn_id = latest
            self.last_bridge_turn_key = latest_key
            self.bridge_turn_baselined = True
            return None
        if state.get("generating"):
            return None
        status = self.coordinator_local_status()
        if (
            status.get("transport_delivered") is True
            and isinstance(status.get("continuation_id"), str)
            and latest_key is not None
            and latest_key != self.last_bridge_turn_key
        ):
            observed = self.observe_model_turn_local(status["continuation_id"])
            if observed.get("observed") is True:
                self.model_turn_observation_count += 1
                self.last_bridge_turn_id = latest
                self.last_bridge_turn_key = latest_key
                return observed
        if latest_key != self.last_bridge_turn_key and not status.get("transport_delivered"):
            self.last_bridge_turn_id = latest
            self.last_bridge_turn_key = latest_key
        return None

    def recover_listener(self, page: dict) -> bool:
        """Load older virtualized turns until the coordinator MCP App iframe mounts."""
        deadline = time.monotonic() + self.cfg.listener_recovery_timeout
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=5, suppress_origin=True
        )
        request_id = 0
        last_height: int | None = None
        stable_top_cycles = 0

        def evaluate(expression: str):
            nonlocal request_id
            request_id += 1
            ws.send(json.dumps({
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    return (
                        message.get("result", {})
                        .get("result", {})
                        .get("value")
                    )

        try:
            while time.monotonic() < deadline and not self.stop:
                try:
                    coordinator_status = self.coordinator_local_status()
                except requests.RequestException:
                    coordinator_status = {}
                if coordinator_status.get("state") == "browser_preflight":
                    return False
                state = evaluate(r"""(()=>{
                  const frames=[...document.querySelectorAll('iframe')]
                    .filter(f=>f.title.startsWith('ui://development-bridge/coordinator-x-v')&&f.title.endsWith('.html'));
                  if(frames.length) return {frames:frames.length};
                  const roots=[...document.querySelectorAll('*')].filter(e=>{
                    const s=getComputedStyle(e);
                    return e.tagName!=='NAV' && s.overflowY==='auto' &&
                      e.scrollHeight>e.clientHeight+100 && e.clientHeight>500;
                  }).sort((a,b)=>b.scrollHeight-a.scrollHeight);
                  const e=roots[0];
                  if(!e) return {frames:0,error:'scroll-root-not-found'};
                  const before={top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight};
                  const step=Math.max(600, Math.floor(e.clientHeight*0.85));
                  e.scrollTop=Math.max(0,e.scrollTop-step);
                  return {frames:0,before,after:e.scrollTop};
                })()""")
                if not state:
                    time.sleep(0.75)
                    continue
                if state.get("frames", 0):
                    self.listener_recovery_count += 1
                    return True
                if state.get("error"):
                    time.sleep(1)
                    continue

                time.sleep(0.75)
                observed = evaluate(r"""(()=>{
                  const frames=[...document.querySelectorAll('iframe')]
                    .filter(f=>f.title.startsWith('ui://development-bridge/coordinator-x-v')&&f.title.endsWith('.html'));
                  const roots=[...document.querySelectorAll('*')].filter(e=>{
                    const s=getComputedStyle(e);
                    return e.tagName!=='NAV' && s.overflowY==='auto' &&
                      e.scrollHeight>e.clientHeight+100 && e.clientHeight>500;
                  }).sort((a,b)=>b.scrollHeight-a.scrollHeight);
                  const e=roots[0];
                  return {frames:frames.length,top:e?.scrollTop??null,height:e?.scrollHeight??null};
                })()""")
                if observed and observed.get("frames", 0):
                    self.listener_recovery_count += 1
                    return True
                if not observed:
                    continue
                top = observed.get("top")
                height = observed.get("height")
                if top == 0 and height == last_height:
                    stable_top_cycles += 1
                else:
                    stable_top_cycles = 0
                last_height = height
                # Repeated scroll-to-top triggers ChatGPT's lazy loading. If the
                # document stops growing for several cycles, there is no mount to recover.
                if stable_top_cycles >= 8:
                    return False
            return False
        finally:
            ws.close()

    def route_registry_snapshot(self) -> dict:
        try:
            data = json.loads(self.cfg.route_registry.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"route registry is unreadable: {exc}") from exc
        if data.get("version") != 1 or not isinstance(data.get("routes"), dict):
            raise RuntimeError("route registry format is invalid")
        return data

    def pending_rollover(self) -> dict | None:
        data = self.route_registry_snapshot()
        pending = (data.get("rollovers") or {}).get(self.route_id)
        return dict(pending) if isinstance(pending, dict) else None

    def active_rollover_record(self) -> dict | None:
        data = self.route_registry_snapshot()
        last = (data.get("last_rollover") or {}).get(self.route_id)
        if not isinstance(last, dict):
            return None
        if int(last.get("target_generation", -1)) != self.route_generation:
            return None
        if last.get("candidate_url") != self.target_url:
            return None
        return dict(last)

    def rollover_control(self, action: str, rollover: dict, **payload) -> dict:
        body = {"route_id": self.route_id, "token": rollover["token"], **payload}
        response = requests.post(
            self.cfg.coordinator_local_url + f"rollover/{action}",
            json=body,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("invalid rollover control response")
        return data

    def runtime_evaluate(
        self, page: dict, expression: str, *, await_promise: bool = False, timeout: float = 5
    ):
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True
        )
        try:
            request_id = int(time.time() * 1_000_000) % 1_000_000_000
            ws.send(json.dumps({
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": await_promise,
                },
            }))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") != request_id:
                    continue
                result = message.get("result", {})
                if result.get("exceptionDetails"):
                    raise RuntimeError("ChatGPT page evaluation failed")
                return result.get("result", {}).get("value")
        finally:
            ws.close()

    @staticmethod
    def project_id_from_url(url: str) -> str | None:
        path = urlsplit(canonical_chat_url(url)).path
        return next((part for part in path.split("/") if part.startswith("g-p-")), None)

    def dispatch_mouse_click(self, page: dict, x: float, y: float) -> None:
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=5, suppress_origin=True
        )
        try:
            request_id = int(time.time() * 1_000_000) % 1_000_000_000
            for event_type, buttons in (
                ("mouseMoved", 0),
                ("mousePressed", 1),
                ("mouseReleased", 0),
            ):
                request_id += 1
                ws.send(json.dumps({
                    "id": request_id,
                    "method": "Input.dispatchMouseEvent",
                    "params": {
                        "type": event_type,
                        "x": x,
                        "y": y,
                        "button": "left",
                        "buttons": buttons,
                        "clickCount": 1,
                        "pointerType": "mouse",
                    },
                }))
                while True:
                    message = json.loads(ws.recv())
                    if message.get("id") != request_id:
                        continue
                    if message.get("error"):
                        raise RuntimeError("ChatGPT branch mouse input failed")
                    break
        finally:
            ws.close()

    def materialize_branch_popup(
        self, page: dict, branch_url: str, source_url: str, *, timeout: float = 30
    ) -> tuple[dict, str]:
        """Materialize ChatGPT's transient /branch route into a stable server conversation."""
        source = canonical_chat_url(source_url)
        candidate_prefix = source.rsplit("/c/", 1)[0]
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=max(5, timeout), suppress_origin=True
        )
        request_id = int(time.time() * 1_000_000) % 1_000_000_000

        def send(method: str, params: dict | None = None) -> int:
            nonlocal request_id
            request_id += 1
            ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
            return request_id

        body = ""
        try:
            enable_id = send("Network.enable")
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == enable_id:
                    if message.get("error"):
                        raise RuntimeError("cannot enable CDP network observation for ChatGPT branch")
                    break

            navigate_id = send("Page.navigate", {"url": branch_url})
            branch_request_id: str | None = None
            branch_status: int | None = None
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                message = json.loads(ws.recv())
                if message.get("id") == navigate_id and message.get("error"):
                    raise RuntimeError("cannot navigate ChatGPT branch hand-off route")
                method = message.get("method")
                params = message.get("params", {})
                if method == "Network.requestWillBeSent":
                    request = params.get("request", {})
                    path = urlsplit(str(request.get("url") or "")).path
                    if path.endswith("/conversation/new_branch"):
                        branch_request_id = str(params.get("requestId") or "") or None
                elif (
                    method == "Network.responseReceived"
                    and branch_request_id is not None
                    and str(params.get("requestId")) == branch_request_id
                ):
                    branch_status = int(params.get("response", {}).get("status", 0) or 0)
                elif (
                    method == "Network.loadingFailed"
                    and branch_request_id is not None
                    and str(params.get("requestId")) == branch_request_id
                ):
                    detail = params.get("errorText") or "unknown network error"
                    raise RuntimeError(f"ChatGPT new_branch request failed: {detail}")
                elif (
                    method == "Network.loadingFinished"
                    and branch_request_id is not None
                    and str(params.get("requestId")) == branch_request_id
                ):
                    break
            else:
                raise RuntimeError("ChatGPT branch hand-off did not finish")

            if branch_request_id is None:
                raise RuntimeError("ChatGPT branch hand-off did not call new_branch")
            if branch_status != 200:
                raise RuntimeError(f"ChatGPT new_branch returned HTTP {branch_status or 'unknown'}")

            body_id = send("Network.getResponseBody", {"requestId": branch_request_id})
            while True:
                message = json.loads(ws.recv())
                if message.get("id") != body_id:
                    continue
                if message.get("error"):
                    raise RuntimeError("cannot read ChatGPT new_branch response")
                body = message.get("result", {}).get("body", "")
                break
        finally:
            ws.close()

        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("ChatGPT new_branch response is not valid JSON") from exc
        conversation = payload.get("conversation") if isinstance(payload, dict) else None
        conversation_id = (
            conversation.get("conversation_id") if isinstance(conversation, dict) else None
        )
        if (
            not isinstance(conversation_id, str)
            or not conversation_id
            or "/" in conversation_id
            or "?" in conversation_id
            or "#" in conversation_id
        ):
            raise RuntimeError("ChatGPT new_branch response did not include a stable conversation_id")

        candidate_url = canonical_chat_url(f"{candidate_prefix}/c/{conversation_id}")
        self.navigate(page, candidate_url)
        candidate_page = dict(page)
        candidate_page["url"] = candidate_url
        return candidate_page, candidate_url

    def branch_in_new_chat(self, page: dict, source_url: str) -> tuple[dict, str]:
        before_page_ids = {item.get("id") for item in self.pages()}
        open_menu = r'''(()=>{
          const visibleBranch=[...document.querySelectorAll('[role="menuitem"]')].find(e=>{
            const r=e.getBoundingClientRect(); return r.width>0&&r.height>0&&(e.innerText||e.textContent||'').trim()==='Branch in new chat';
          });
          if(visibleBranch)return {ok:true,menu_open:true};
          const turns=[...document.querySelectorAll('[data-testid^="conversation-turn-"]')];
          const turn=[...turns].reverse().find(t=>t.querySelector('[data-message-author-role="assistant"]'))||turns.at(-1);
          if(!turn)return {ok:false,error:'turn_missing'};
          const button=[...turn.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='More actions');
          if(!button)return {ok:false,error:'more_actions_missing'};
          button.scrollIntoView({block:'center'});
          button.click(); return {ok:true,menu_open:false};
        })()'''
        opened = self.runtime_evaluate(page, open_menu)
        if not isinstance(opened, dict) or not opened.get("ok"):
            raise RuntimeError(f"cannot open ChatGPT turn menu: {(opened or {}).get('error', 'unknown')}")
        time.sleep(0.35)
        branch_box = self.runtime_evaluate(page, r'''(()=>{
          const item=[...document.querySelectorAll('[role="menuitem"]')].find(e=>{
            const r=e.getBoundingClientRect();
            return r.width>0&&r.height>0&&(e.innerText||e.textContent||'').trim()==='Branch in new chat';
          });
          if(!item)return {ok:false,error:'branch_action_missing'};
          const r=item.getBoundingClientRect();
          return {ok:true,x:r.left+r.width/2,y:r.top+r.height/2};
        })()''')
        if not isinstance(branch_box, dict) or not branch_box.get("ok"):
            raise RuntimeError(
                f"cannot branch ChatGPT conversation: {(branch_box or {}).get('error', 'unknown')}"
            )
        self.dispatch_mouse_click(page, float(branch_box["x"]), float(branch_box["y"]))

        deadline = time.monotonic() + 5
        branch_page = None
        branch_url = None
        while time.monotonic() < deadline:
            for candidate in self.pages():
                if candidate.get("id") in before_page_ids:
                    continue
                parts = urlsplit(str(candidate.get("url") or ""))
                if parts.scheme == "https" and parts.netloc == "chatgpt.com" and parts.path.startswith("/branch/"):
                    branch_page = candidate
                    branch_url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
                    break
            if branch_page is not None:
                break
            time.sleep(0.1)
        if branch_page is None or branch_url is None:
            raise RuntimeError("ChatGPT Branch in new chat did not open its hand-off page")
        return self.materialize_branch_popup(branch_page, branch_url, source_url)

    def coordinator_app_targets(self, page: dict | None = None) -> list[dict]:
        response = requests.get(f"{self.cdp_base}/json/list", timeout=2)
        response.raise_for_status()
        page_id = str(page.get("id")) if isinstance(page, dict) and page.get("id") else None
        return [
            item for item in response.json()
            if item.get("type") == "iframe"
            and "web-sandbox.oaiusercontent.com" in item.get("url", "")
            and item.get("webSocketDebuggerUrl")
            and (page_id is None or str(item.get("parentId") or "") == page_id)
        ]

    def coordinator_app_control(self, page: dict, action: str, **payload) -> dict:
        nonce = token_urlsafe(12)
        message = {
            "type": "development-bridge/control-v1",
            "nonce": nonce,
            "action": action,
            **payload,
        }
        encoded = json.dumps(message, ensure_ascii=False)
        for target in self.coordinator_app_targets(page):
            ws = websocket.create_connection(
                target["webSocketDebuggerUrl"], timeout=5, suppress_origin=True
            )
            try:
                enable_id = int(time.time() * 1_000_000) % 1_000_000_000
                ws.send(json.dumps({"id": enable_id, "method": "Runtime.enable"}))
                contexts: list[int] = []
                while True:
                    event = json.loads(ws.recv())
                    if event.get("method") == "Runtime.executionContextCreated":
                        context = event.get("params", {}).get("context", {})
                        context_id = context.get("id")
                        if isinstance(context_id, int):
                            contexts.append(context_id)
                    if event.get("id") == enable_id:
                        break
                for context_id in contexts:
                    probe_id = (enable_id + context_id + 1) % 1_000_000_000
                    probe = (
                        "document.title==='Development Bridge Coordinator'"
                        "&&typeof window.__developmentBridgeControlV1==='function'"
                    )
                    ws.send(json.dumps({
                        "id": probe_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "contextId": context_id,
                            "expression": probe,
                            "returnByValue": True,
                        },
                    }))
                    while True:
                        event = json.loads(ws.recv())
                        if event.get("id") == probe_id:
                            capable = bool(
                                event.get("result", {}).get("result", {}).get("value", False)
                            )
                            break
                    if not capable:
                        continue
                    call_id = (probe_id + 1000) % 1_000_000_000
                    expression = (
                        f"window.__developmentBridgeControlV1({encoded})"
                    )
                    ws.send(json.dumps({
                        "id": call_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "contextId": context_id,
                            "expression": expression,
                            "returnByValue": True,
                            "awaitPromise": True,
                        },
                    }))
                    while True:
                        event = json.loads(ws.recv())
                        if event.get("id") != call_id:
                            continue
                        result = event.get("result", {})
                        if result.get("exceptionDetails"):
                            raise RuntimeError("MCP App control evaluation failed")
                        value = result.get("result", {}).get("value")
                        if isinstance(value, dict):
                            return value
                        break
            finally:
                ws.close()
        return {"ok": False, "error": "control_context_missing"}

    def ensure_control_channel(self, page: dict, channel_id: str) -> dict:
        ping = self.coordinator_app_control(page, "ping")
        if not ping.get("ok"):
            return ping
        if ping.get("channel_id") == channel_id:
            return ping
        return self.coordinator_app_control(page, "bind", channel_id=channel_id)

    def wait_for_control_channel(self, page: dict, channel_id: str, timeout: float = 30) -> dict:
        deadline = time.monotonic() + timeout
        last = {"ok": False, "error": "control_timeout"}
        while time.monotonic() < deadline:
            try:
                last = self.ensure_control_channel(page, channel_id)
            except TRANSIENT_CDP_ERRORS as exc:
                last = {"ok": False, "error": str(exc)}
            if last.get("ok") and last.get("channel_id") == channel_id:
                return last
            time.sleep(1)
        return last

    def wait_for_polling(self, channel_id: str, timeout: float = 35) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        detail = "not checked"
        while time.monotonic() < deadline:
            ok, detail = self.polling_ok(channel_id)
            if ok is True:
                return True, detail
            time.sleep(1)
        return False, detail

    def wait_for_rollover_preflight(self, page: dict, token: str, timeout: float = 75) -> dict:
        marker = f"ROLLOVER_READY {token}"
        encoded_marker = json.dumps(marker, ensure_ascii=False)
        expression = f'''(()=>{{
          const marker={encoded_marker};
          const generating=[...document.querySelectorAll('button')].some(b=>{{
            const text=((b.getAttribute('aria-label')||'')+' '+(b.innerText||'')).toLowerCase();
            return text.includes('stop generating')||text.includes('stop streaming')||text.includes('остановить');
          }});
          let matched=false, iframeCount=0;
          for(const turn of document.querySelectorAll('[data-testid^="conversation-turn-"]')){{
            const text=(turn.innerText||turn.textContent||'');
            if(!text.includes(marker))continue;
            const assistant=(turn.querySelector('[data-message-author-role="assistant"]')?.innerText||'').trim();
            const frames=[...turn.querySelectorAll('iframe')].filter(f=>
              f.title.startsWith('ui://development-bridge/coordinator-x-v')&&f.title.endsWith('.html')
            );
            iframeCount=Math.max(iframeCount,frames.length);
            if(assistant&&frames.length)matched=true;
          }}
          return {{ready:matched&&!generating,generating,iframe_count:iframeCount}};
        }})()'''
        deadline = time.monotonic() + timeout
        last = {"ready": False, "iframe_count": 0}
        while time.monotonic() < deadline:
            value = self.runtime_evaluate(page, expression)
            if isinstance(value, dict):
                last = value
                if value.get("ready") is True:
                    return value
            time.sleep(1)
        return last

    def restore_source_after_rollover(self, source_url: str) -> None:
        try:
            pages = self.pages()
            if not pages:
                return
            source = next((p for p in pages if is_target_url(p.get("url", ""), source_url)), None)
            if source is None:
                self.navigate(pages[0], source_url)
                time.sleep(4)
                pages = self.pages()
                source = next((p for p in pages if is_target_url(p.get("url", ""), source_url)), None)
            if source is not None:
                for item in pages:
                    if item["id"] != source["id"]:
                        self.close_page(item["id"])
        except Exception:
            pass

    def rollover_age_seconds(self, rollover: dict) -> float:
        try:
            created = datetime.fromisoformat(str(rollover["created_at"]))
            return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())
        except Exception:
            return 0.0

    def abort_pending_rollover(self, rollover: dict, reason: str) -> dict:
        self.rollover_abort_count += 1
        try:
            result = self.rollover_control("abort", rollover, reason=reason[:500])
        finally:
            self.restore_source_after_rollover(rollover["source_url"])
        return result

    def process_pending_rollover(self) -> dict | None:
        rollover = self.pending_rollover()
        if rollover is None:
            return None
        if int(rollover.get("source_generation", -1)) != self.route_generation:
            return self.abort_pending_rollover(rollover, "active route generation changed")
        source_url = canonical_chat_url(rollover["source_url"])
        target_channel = str(rollover["channel_id"])
        state = str(rollover.get("state") or "")
        try:
            candidate_page = None
            if state == "prepared":
                pages = self.pages()
                source_page = next(
                    (item for item in pages if is_target_url(item.get("url", ""), source_url)), None
                )
                if source_page is None:
                    if not pages:
                        return {"state": "waiting_source_page"}
                    self.navigate(pages[0], source_url)
                    time.sleep(4)
                    pages = self.pages()
                    source_page = next(
                        (item for item in pages if is_target_url(item.get("url", ""), source_url)), None
                    )
                if source_page is None:
                    raise RuntimeError("source conversation is unavailable")
                turn_state, error = self.safe_bridge_turn_state(source_page)
                if turn_state is None:
                    return {"state": "waiting_source_turn", "error": error}
                if turn_state.get("generating"):
                    return {"state": "waiting_source_turn"}
                source_control = self.coordinator_app_control(source_page, "ping")
                if not source_control.get("ok"):
                    iframe_count, iframe_error = self.safe_coordinator_iframe_count(source_page)
                    poll_ok, poll_detail = self.polling_ok()
                    legacy_source_verified = (
                        iframe_count is not None
                        and iframe_count > 0
                        and poll_ok is True
                    )
                    if not legacy_source_verified:
                        if self.rollover_age_seconds(rollover) > 120:
                            raise RuntimeError("fresh rollover MCP App is not control-capable")
                        return {
                            "state": "waiting_source_control",
                            "error": source_control.get("error") or iframe_error or poll_detail,
                        }
                candidate_page, candidate_url = self.branch_in_new_chat(source_page, source_url)
                rollover = self.rollover_control("candidate", rollover, url=candidate_url)
                state = "candidate"

            if state != "candidate":
                raise RuntimeError(f"unsupported rollover state: {state}")
            candidate_url = canonical_chat_url(rollover["candidate_url"])
            if candidate_page is None:
                pages = self.pages()
                candidate_page = next(
                    (item for item in pages if is_target_url(item.get("url", ""), candidate_url)), None
                )
                if candidate_page is None:
                    if not pages:
                        return {"state": "waiting_candidate_page"}
                    self.navigate(pages[0], candidate_url)
                    time.sleep(4)
                    pages = self.pages()
                    candidate_page = next(
                        (item for item in pages if is_target_url(item.get("url", ""), candidate_url)), None
                    )
            if candidate_page is None:
                raise RuntimeError("successor conversation is unavailable")

            control = self.wait_for_control_channel(candidate_page, target_channel, timeout=30)
            if not control.get("ok") or control.get("channel_id") != target_channel:
                raise RuntimeError(f"successor MCP App control failed: {control.get('error', 'unknown')}")
            poll_ok, poll_detail = self.wait_for_polling(target_channel, timeout=35)
            if not poll_ok:
                raise RuntimeError(f"successor X polling was not observed: {poll_detail}")

            preflight_operation = f"{rollover['token']}-preflight"
            preflight_message = (
                f"Development Bridge automatic rollover preflight. Do not continue project work. "
                f"Call coordinator_x_mount with channel_id={target_channel}. After that tool succeeds, "
                f"reply exactly: ROLLOVER_READY {rollover['token']}"
            )
            preflight_send = self.coordinator_app_control(
                candidate_page,
                "bootstrap",
                channel_id=target_channel,
                operation_id=preflight_operation,
                message=preflight_message,
            )
            if not preflight_send.get("ok"):
                raise RuntimeError(
                    f"successor preflight delivery failed: {preflight_send.get('error', 'unknown')}"
                )
            preflight = self.wait_for_rollover_preflight(
                candidate_page, rollover["token"], timeout=75
            )
            if not preflight.get("ready"):
                raise RuntimeError(
                    "successor did not create a native coordinator mount during preflight"
                )
            poll_ok, poll_detail = self.wait_for_polling(target_channel, timeout=20)
            if not poll_ok:
                raise RuntimeError(f"native successor X polling was not observed: {poll_detail}")

            committed = self.rollover_control("commit", rollover)
            self.rollover_count += 1
            return {"state": "committed", "route": committed, "polling_detail": poll_detail}
        except TRANSIENT_CDP_ERRORS as exc:
            if self.rollover_age_seconds(rollover) <= 180:
                return {"state": "waiting_transient", "error": str(exc)}
            self.abort_pending_rollover(rollover, f"transient rollover failure exceeded TTL: {exc}")
            return {"state": "aborted", "error": str(exc)}
        except Exception as exc:
            self.abort_pending_rollover(rollover, str(exc))
            return {"state": "aborted", "error": str(exc)}

    def ensure_active_rollover_binding(self, page: dict) -> dict | None:
        record = self.active_rollover_record()
        if record is None:
            return None
        return self.ensure_control_channel(page, self.channel_id)

    def complete_rollover_bootstrap(self, page: dict) -> dict | None:
        record = self.active_rollover_record()
        if record is None or record.get("bootstrap_sent") is True or record.get("state") == "complete":
            return None
        control = self.wait_for_control_channel(page, self.channel_id, timeout=15)
        if not control.get("ok") or control.get("channel_id") != self.channel_id:
            return {"state": "bootstrap_waiting", "error": control.get("error")}
        message = (
            f"Automatic physical-chat rollover completed for logical route {self.route_id} "
            f"generation {self.route_generation}. Before other work, call "
            f"coordinator_route_context_get with route_id={self.route_id} and use its canonical "
            "Route Context as the authoritative checkpoint. Then continue NEXT ORDER OF WORK."
        )
        bootstrap = self.coordinator_app_control(
            page,
            "bootstrap",
            channel_id=self.channel_id,
            operation_id=record["token"],
            message=message,
        )
        if not bootstrap.get("ok"):
            return {"state": "bootstrap_waiting", "error": bootstrap.get("error")}
        completed = self.rollover_control("complete", record)
        return {"state": "complete", "rollover": completed, "duplicate": bootstrap.get("duplicate", False)}

    def refresh_route_target(self) -> bool:
        try:
            data = json.loads(self.cfg.route_registry.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {"version": 1, "default_route": self.cfg.route_id, "requested_route": self.cfg.route_id, "routes": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"route registry is unreadable: {exc}") from exc
        if data.get("version") != 1 or not isinstance(data.get("routes"), dict):
            raise RuntimeError("route registry format is invalid")
        changed_file = False
        if self.cfg.route_id not in data["routes"]:
            parts = urlsplit(self.cfg.target_url)
            path = parts.path
            conversation_id = path.rsplit("/c/", 1)[1].split("/", 1)[0]
            project_id = next((part for part in path.split("/") if part.startswith("g-p-")), None)
            data["routes"][self.cfg.route_id] = {
                "title": self.cfg.route_id,
                "url": self.cfg.target_url,
                "project_id": project_id,
                "conversation_id": conversation_id,
                "channel_id": self.cfg.channel_id,
                "generation": 0,
                "updated_at": utcnow(),
            }
            changed_file = True
        requested = data.get("requested_route") or data.get("default_route") or self.cfg.route_id
        if requested not in data["routes"]:
            requested = self.cfg.route_id
            data["requested_route"] = requested
            changed_file = True
        route = data["routes"][requested]
        target = canonical_chat_url(route["url"])
        channel = str(route["channel_id"])
        generation = int(route.get("generation", 0))
        changed = (requested, target, channel, generation) != (self.route_id, self.target_url, self.channel_id, self.route_generation)
        self.route_id, self.target_url, self.channel_id, self.route_generation = requested, target, channel, generation
        if not data.get("default_route"):
            data["default_route"] = self.cfg.route_id
            changed_file = True
        if not data.get("requested_route"):
            data["requested_route"] = requested
            changed_file = True
        if changed_file:
            atomic_json(self.cfg.route_registry, data)
        return changed

    def discover_chats(self, page: dict) -> int:
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=5, suppress_origin=True)
        try:
            expression = r'''(()=>{const buttons=[...document.querySelectorAll('button')].filter(b=>(b.innerText||'').trim()==='Show more'&&b.getBoundingClientRect().left<460);if(buttons.length)buttons[0].click();const out=[];for(const a of document.querySelectorAll('a[href*="/c/"]')){const href=a.getAttribute('href')||'';const m=href.match(/\/c\/([^/?#]+)/);if(!m)continue;const pm=href.match(/\/(g-p-[^/]+)\/c\//);const aria=(a.getAttribute('aria-label')||'').trim();let project_title=null;const tag=', chat in project ';const idx=aria.indexOf(tag);if(idx>=0)project_title=aria.slice(idx+tag.length).trim();out.push({conversation_id:m[1],project_id:pm?pm[1]:null,title:(a.innerText||a.textContent||'').trim().slice(0,200),project_title,href});}return out.slice(0,500);})()'''
            request_id = int(time.time() * 1000) % 1_000_000_000
            ws.send(json.dumps({"id": request_id, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}}))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == request_id:
                    rows = message.get("result", {}).get("result", {}).get("value", []) or []
                    break
        finally:
            ws.close()
        try:
            registry = json.loads(self.cfg.chat_registry.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            registry = {"version": 1, "chats": {}}
        chats = registry.setdefault("chats", {})
        seen_at = utcnow()
        for row in rows:
            href = str(row.get("href") or "")
            if href.startswith("/"):
                url = "https://chatgpt.com" + href
            else:
                url = href
            try:
                url = canonical_chat_url(url)
            except ValueError:
                continue
            cid = str(row.get("conversation_id") or "")
            if not cid:
                continue
            chats[cid] = {"title": row.get("title") or cid, "project_title": row.get("project_title"), "project_id": row.get("project_id"), "conversation_id": cid, "url": url, "last_seen": seen_at}
        registry["updated_at"] = seen_at
        atomic_json(self.cfg.chat_registry, registry)
        self.last_discovery = time.monotonic()
        return len(rows)

    def reload_route_target(self) -> None:
        pages = self.pages()
        if not pages:
            return
        page = next(
            (item for item in pages if is_target_url(item.get("url", ""), self.target_url)),
            pages[0],
        )
        self.navigate(page, self.target_url)
        time.sleep(4)

    def enforce_target(self) -> tuple[bool, dict | None]:
        pages = self.pages()
        target = next(
            (page for page in pages if is_target_url(page.get("url", ""), self.target_url)),
            None,
        )
        if target is None:
            if not pages:
                return False, None
            self.navigate(pages[0], self.target_url)
            time.sleep(4)
            pages = self.pages()
            target = next(
                (page for page in pages if is_target_url(page.get("url", ""), self.target_url)),
                None,
            )
            if target is None:
                return False, None
            self.repair_count += 1

        for page in pages:
            if page["id"] != target["id"]:
                self.close_page(page["id"])
        return True, target

    def polling_ok(self, channel_id: str | None = None) -> tuple[bool | None, str]:
        command = [
            "journalctl",
            "-u", self.cfg.bridge_unit,
            "--since", f"{self.cfg.poll_window} seconds ago",
            "--no-pager",
            "-o", "cat",
        ]
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=4,
                check=False,
            )
        except Exception as exc:
            return None, f"journalctl failed: {exc}"
        if result.returncode != 0:
            return None, result.stderr.strip() or f"journalctl exit={result.returncode}"
        selected_channel = channel_id or self.channel_id
        needle = f"/mcp/x/coordinator/status?channel_id={selected_channel}"
        lines = [line for line in result.stdout.splitlines() if needle in line]
        if self.cfg.public_ip:
            lines = [line for line in lines if self.cfg.public_ip in line]
        return bool(lines), f"matches={len(lines)} in last {self.cfg.poll_window}s"

    def run(self) -> int:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        lock_handle = self.cfg.lock_file.open("a+")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another browser-host supervisor already owns the lock", file=sys.stderr)
            return 2

        def stop_handler(signum, frame):
            self.stop = True

        signal.signal(signal.SIGTERM, stop_handler)
        signal.signal(signal.SIGINT, stop_handler)

        try:
            self.ensure_debug_port_free()
            self.refresh_route_target()
            self.write_state(status="starting")
            self.start_xvfb()
            self.start_chrome()
            self.wait_cdp()
            poll_deadline = time.monotonic() + self.cfg.poll_grace
            last_repair_count = self.repair_count

            while not self.stop:
                if self.xvfb is None or self.xvfb.poll() is not None:
                    raise RuntimeError("Xvfb is not running")
                if self.chrome is None or self.chrome.poll() is not None:
                    raise RuntimeError("Chrome is not running")

                route_changed = self.refresh_route_target()
                if route_changed:
                    poll_deadline = time.monotonic() + self.cfg.poll_grace
                    self.last_bridge_turn_id = 0
                    self.last_bridge_turn_key = None
                    self.bridge_turn_baselined = False
                    pages = self.pages()
                    if not any(is_target_url(item.get("url", ""), self.target_url) for item in pages):
                        self.reload_route_target()

                rollover_result = self.process_pending_rollover()
                if rollover_result is not None:
                    self.write_state(status="rollover", rollover=rollover_result)
                    time.sleep(self.cfg.check_interval)
                    continue

                target_ok, page = self.enforce_target()
                if self.repair_count != last_repair_count:
                    poll_deadline = time.monotonic() + self.cfg.poll_grace
                    last_repair_count = self.repair_count

                title = (page or {}).get("title", "")
                current_url = (page or {}).get("url", "")
                challenge = (
                    "Just a moment" in title
                    or "/auth/login" in current_url
                    or "challenge" in current_url.lower()
                )
                poll_ok, poll_detail = self.polling_ok()

                if challenge:
                    if time.monotonic() >= poll_deadline:
                        self.write_state(
                            status="auth_required",
                            cdp_ok=True,
                            target_ok=target_ok,
                            polling_ok=poll_ok,
                            polling_detail=poll_detail,
                            current_url=current_url,
                            title=title,
                            note=(
                                "Normal manual login/security check is required; "
                                "no bypass is attempted."
                            ),
                        )
                        return 0
                    self.write_state(
                        status="starting",
                        cdp_ok=True,
                        target_ok=target_ok,
                        polling_ok=poll_ok,
                        polling_detail=poll_detail,
                        current_url=current_url,
                        title=title,
                    )
                    time.sleep(self.cfg.check_interval)
                    continue

                if not target_ok or page is None:
                    self.write_state(
                        status="degraded",
                        cdp_ok=True,
                        target_ok=False,
                        polling_ok=poll_ok,
                        polling_detail=poll_detail,
                        current_url=current_url,
                        title=title,
                    )
                    time.sleep(self.cfg.check_interval)
                    continue

                try:
                    rate_limited = self.rate_limit_detected(page)
                except Exception:
                    rate_limited = False
                if rate_limited:
                    backoff_seconds = self.activate_web_backoff()
                    self.write_state(
                        status="rate_limited",
                        cdp_ok=True,
                        target_ok=True,
                        polling_ok=poll_ok,
                        polling_detail=poll_detail,
                        current_url=current_url,
                        title=title,
                        web_backoff_seconds=round(backoff_seconds, 1),
                        rate_limit_count=self.rate_limit_count,
                    )
                    time.sleep(max(self.cfg.check_interval, min(15.0, backoff_seconds)))
                    continue

                # A pending X turn must get first chance to refresh the canonical chat.
                # Do this before generic iframe recovery: a heavy/stale transcript can make
                # the old page unresponsive, while prepare_browser_preflight() starts with a
                # canonical Page.navigate and then performs its own listener recovery.
                try:
                    early_status = self.coordinator_local_status()
                    early_continuation_id = early_status.get("continuation_id")
                    if (
                        early_status.get("state") == "browser_preflight"
                        and isinstance(early_continuation_id, str)
                        and early_continuation_id
                    ):
                        self.write_state(
                            status="preparing_web_turn", cdp_ok=True, target_ok=True,
                            coordinator_iframes=0, polling_ok=poll_ok,
                            polling_detail=poll_detail, current_url=current_url, title=title,
                            continuation_id=early_continuation_id,
                        )
                        prepared = self.prepare_browser_preflight(page, early_continuation_id)
                        self.write_state(
                            status="starting" if prepared.get("authorized") else "preparing_web_turn",
                            cdp_ok=True, target_ok=True, coordinator_iframes=0,
                            polling_ok=poll_ok, polling_detail=poll_detail,
                            current_url=current_url, title=title,
                            continuation_id=early_continuation_id, web_turn_preflight=prepared,
                        )
                        time.sleep(self.cfg.check_interval)
                        continue
                except TRANSIENT_CDP_ERRORS as exc:
                    self.write_state(
                        status="preparing_web_turn", cdp_ok=True, target_ok=True,
                        coordinator_iframes=0, polling_ok=poll_ok,
                        polling_detail=poll_detail, current_url=current_url, title=title,
                        error=f"transient early browser preflight failure: {exc}",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue
                except (RuntimeError, ValueError, requests.RequestException) as exc:
                    self.write_state(
                        status="preparing_web_turn", cdp_ok=True, target_ok=True,
                        coordinator_iframes=0, polling_ok=poll_ok,
                        polling_detail=poll_detail, current_url=current_url, title=title,
                        error=f"early browser preflight failure: {exc}",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue

                iframe_count, iframe_error = self.safe_coordinator_iframe_count(page)
                if iframe_count is None:
                    self.write_state(
                        status="degraded", cdp_ok=True, target_ok=True,
                        coordinator_iframes=0, polling_ok=poll_ok, polling_detail=poll_detail,
                        current_url=current_url, title=title,
                        error=f"transient coordinator iframe probe failed: {iframe_error}",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue
                if iframe_count == 0:
                    self.write_state(
                        status="recovering_listener",
                        cdp_ok=True,
                        target_ok=True,
                        coordinator_iframes=0,
                        polling_ok=False,
                        polling_detail=poll_detail,
                        current_url=current_url,
                        title=title,
                    )
                    try:
                        recovered = self.recover_listener(page)
                    except TRANSIENT_CDP_ERRORS as exc:
                        self.write_state(
                            status="degraded", cdp_ok=True, target_ok=True,
                            coordinator_iframes=0, polling_ok=poll_ok, polling_detail=poll_detail,
                            current_url=current_url, title=title,
                            error=f"transient coordinator listener recovery failed: {exc}",
                        )
                        time.sleep(self.cfg.check_interval)
                        continue
                    if not recovered:
                        # Keep the authenticated Chrome alive. A fresh tool card may have arrived in
                        # another client while this page was open; reload the same physical chat and
                        # retry instead of entering a Chrome/systemd restart loop.
                        self.listener_recovery_count += 1
                        self.reload_route_target()
                        poll_deadline = time.monotonic() + self.cfg.poll_grace
                        self.write_state(
                            status="recovering_listener", cdp_ok=True, target_ok=True,
                            coordinator_iframes=0, polling_ok=False, polling_detail=poll_detail,
                            current_url=current_url, title=title,
                            note="listener history recovery exhausted; reloading current chat in-process",
                        )
                        time.sleep(self.cfg.check_interval)
                        continue
                    # The iframe has mounted; give its X polling a fresh grace window.
                    poll_deadline = time.monotonic() + self.cfg.poll_grace
                    iframe_count, iframe_error = self.safe_coordinator_iframe_count(page)
                    if iframe_count is None:
                        self.write_state(
                            status="degraded", cdp_ok=True, target_ok=True,
                            coordinator_iframes=0, polling_ok=poll_ok, polling_detail=poll_detail,
                            current_url=current_url, title=title,
                            error=f"transient coordinator iframe probe failed: {iframe_error}",
                        )
                        time.sleep(self.cfg.check_interval)
                        continue
                    poll_ok, poll_detail = self.polling_ok()

                try:
                    coordinator_status = self.coordinator_local_status()
                    continuation_id = coordinator_status.get("continuation_id")
                    if (
                        coordinator_status.get("state") == "browser_preflight"
                        and isinstance(continuation_id, str)
                        and continuation_id
                    ):
                        self.write_state(
                            status="preparing_web_turn",
                            cdp_ok=True,
                            target_ok=True,
                            coordinator_iframes=iframe_count,
                            polling_ok=poll_ok,
                            polling_detail=poll_detail,
                            current_url=current_url,
                            title=title,
                            continuation_id=continuation_id,
                        )
                        prepared = self.prepare_browser_preflight(page, continuation_id)
                        self.write_state(
                            status="starting" if prepared.get("authorized") else "preparing_web_turn",
                            cdp_ok=True,
                            target_ok=True,
                            coordinator_iframes=iframe_count,
                            polling_ok=poll_ok,
                            polling_detail=poll_detail,
                            current_url=current_url,
                            title=title,
                            continuation_id=continuation_id,
                            web_turn_preflight=prepared,
                        )
                        time.sleep(self.cfg.check_interval)
                        continue
                except TRANSIENT_CDP_ERRORS as exc:
                    self.write_state(
                        status="preparing_web_turn", cdp_ok=True, target_ok=True,
                        coordinator_iframes=iframe_count, polling_ok=poll_ok,
                        polling_detail=poll_detail, current_url=current_url, title=title,
                        error=f"transient browser preflight failure: {exc}",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue
                except (RuntimeError, ValueError, requests.RequestException) as exc:
                    self.write_state(
                        status="preparing_web_turn", cdp_ok=True, target_ok=True,
                        coordinator_iframes=iframe_count, polling_ok=poll_ok,
                        polling_detail=poll_detail, current_url=current_url, title=title,
                        error=f"browser preflight failure: {exc}",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue

                try:
                    active_rollover = self.active_rollover_record()
                    if active_rollover is not None:
                        binding = self.ensure_active_rollover_binding(page)
                        if binding is not None and binding.get("ok"):
                            poll_deadline = time.monotonic() + self.cfg.poll_grace
                            poll_ok, poll_detail = self.polling_ok()
                        bootstrap_result = self.complete_rollover_bootstrap(page)
                        if bootstrap_result is not None:
                            poll_ok, poll_detail = self.polling_ok()
                except TRANSIENT_CDP_ERRORS:
                    pass
                except (RuntimeError, ValueError, requests.RequestException):
                    pass

                try:
                    self.sync_model_turn_observation(page)
                except TRANSIENT_CDP_ERRORS:
                    pass
                except (RuntimeError, ValueError):
                    pass

                if time.monotonic() - self.last_discovery >= self.cfg.discovery_interval:
                    try:
                        self.discovered_chats = self.discover_chats(page)
                    except Exception:
                        pass

                if poll_ok is False and time.monotonic() >= poll_deadline:
                    # Missing X polling is a listener-recovery condition, not a reason to destroy
                    # the authenticated browser process. Reload the same chat and keep retrying.
                    self.listener_recovery_count += 1
                    self.reload_route_target()
                    poll_deadline = time.monotonic() + self.cfg.poll_grace
                    self.write_state(
                        status="degraded", cdp_ok=True, target_ok=True,
                        coordinator_iframes=iframe_count, polling_ok=False,
                        polling_detail=poll_detail, current_url=current_url, title=title,
                        error=f"MCP X polling not observed for route={self.route_id}; reloading current chat",
                    )
                    time.sleep(self.cfg.check_interval)
                    continue

                self.write_state(
                    status="healthy" if poll_ok is True and iframe_count > 0 else "starting",
                    cdp_ok=True,
                    target_ok=True,
                    coordinator_iframes=iframe_count,
                    polling_ok=poll_ok,
                    polling_detail=poll_detail,
                    current_url=current_url,
                    title=title,
                )
                time.sleep(self.cfg.check_interval)

            self.write_state(status="stopping")
            return 0
        except Exception as exc:
            self.write_state(status="failed", error=str(exc))
            print(f"browser-host failed: {exc}", file=sys.stderr)
            return 1
        finally:
            terminate(self.chrome)
            terminate(self.xvfb)
            lock_handle.close()


def healthcheck(cfg: Config) -> int:
    try:
        state = json.loads(cfg.state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"healthy": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    updated = datetime.fromisoformat(state["updated_at"])
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    healthy = (
        state.get("status") == "healthy"
        and state.get("target_ok") is True
        and int(state.get("coordinator_iframes", 0)) > 0
        and state.get("polling_ok") is True
        and age <= max(20, cfg.check_interval * 4)
    )
    state["state_age_seconds"] = round(age, 1)
    state["healthy"] = healthy
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if healthy else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("supervise", "healthcheck"))
    args = parser.parse_args()
    try:
        cfg = load_config()
    except Exception as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    if args.command == "healthcheck":
        return healthcheck(cfg)
    return BrowserHost(cfg).run()


if __name__ == "__main__":
    raise SystemExit(main())

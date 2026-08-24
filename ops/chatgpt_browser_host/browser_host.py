#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import websocket


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
                ".filter(f=>f.title==='ui://development-bridge/coordinator-x-v1.html').length"
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
                state = evaluate(r"""(()=>{
                  const frames=[...document.querySelectorAll('iframe')]
                    .filter(f=>f.title==='ui://development-bridge/coordinator-x-v1.html');
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
                    .filter(f=>f.title==='ui://development-bridge/coordinator-x-v1.html');
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

    def polling_ok(self) -> tuple[bool | None, str]:
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
        needle = f"/mcp/x/coordinator/status?channel_id={self.channel_id}"
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

                iframe_count = self.coordinator_iframe_count(page)
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
                    if not self.recover_listener(page):
                        raise RuntimeError(
                            "coordinator MCP App iframe could not be recovered "
                            "from virtualized chat history"
                        )
                    # The iframe has mounted; give its X polling a fresh grace window.
                    poll_deadline = time.monotonic() + self.cfg.poll_grace
                    iframe_count = self.coordinator_iframe_count(page)
                    poll_ok, poll_detail = self.polling_ok()

                if time.monotonic() - self.last_discovery >= self.cfg.discovery_interval:
                    try:
                        self.discovered_chats = self.discover_chats(page)
                    except Exception:
                        pass

                if poll_ok is False and time.monotonic() >= poll_deadline:
                    raise RuntimeError(
                        f"MCP X polling not observed for route={self.route_id}: {poll_detail}"
                    )

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

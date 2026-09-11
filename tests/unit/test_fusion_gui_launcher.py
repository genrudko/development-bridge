from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_fallback_launcher_never_uses_slow_test_net_connection():
    text=(ROOT / "agents" / "START_FUSION_AGENT.ps1").read_text(encoding="utf-8-sig")
    assert "Test-NetConnection" not in text

def test_gui_bootstrap_is_consoleless_and_gui_uses_dpapi():
    bootstrap=(ROOT / "agents" / "START_FUSION_GUI.ps1").read_text(encoding="utf-8-sig")
    gui=(ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert "pythonw.exe" in bootstrap
    assert "2>$null" in bootstrap
    assert "CryptProtectData" in gui and "CryptUnprotectData" in gui
    assert "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN" in gui
    assert "Test-NetConnection" not in gui
    assert "Bridge heartbeat" in gui
    assert "Result delivery" in gui
    assert "Fusion MCP watchdog" in gui

def test_gui_timestamp_helper_prefixes_exactly_once():
    gui=(ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    namespace = {}
    start = gui.index("TIMESTAMPED_LINE =")
    end = gui.index("\n\n\nclass DATA_BLOB", start)
    exec("import re\nimport time\n" + gui[start:end], namespace)
    stamp = namespace["timestamp_log_line"]
    first = stamp("Connected: ready\n", now=0.123)
    assert first[2:] == ":00:00.123 Connected: ready"
    assert stamp(first, now=1.456) == first


def _eyes_runtime_module():
    from agents import fusion_eyes_runtime
    return fusion_eyes_runtime


def test_eyes_profile_builds_existing_proxy_and_relay_without_new_transport(tmp_path):
    runtime = _eyes_runtime_module()
    app_dir = tmp_path / "DevelopmentBridgeFusion"
    server = app_dir / "periscope" / "server"
    scripts = server / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    periscope_python = scripts / "python.exe"
    proxy = scripts / "mcp-proxy.exe"
    periscope_python.write_bytes(b"")
    proxy.write_bytes(b"")
    relay_python = tmp_path / "relay-python.exe"
    relay_python.write_bytes(b"")

    specs = runtime.build_eyes_process_specs(
        "secret-token",
        app_dir=app_dir,
        root=ROOT / "agents",
        relay_python=relay_python,
        environ={"BASE": "kept"},
    )

    assert specs is not None
    proxy_spec, relay_spec = specs
    assert proxy_spec["argv"] == [
        str(proxy), "--port", "18769", "--host", "127.0.0.1",
        "--pass-environment", "--", str(periscope_python), "-m", "periscope_mcp",
    ]
    assert proxy_spec["env"]["BASE"] == "kept"
    assert proxy_spec["env"]["PYTHONPATH"] == str(server)
    assert relay_spec["argv"] == [str(relay_python), str(ROOT / "agents" / "windows_fusion_agent.py")]
    assert relay_spec["env"]["DEVELOPMENT_BRIDGE_NODE_ID"] == "fusion-eyes"
    assert relay_spec["env"]["FUSION_MCP_URL"] == "http://127.0.0.1:18769/mcp"
    assert relay_spec["env"]["DEVELOPMENT_BRIDGE_FUSION_OUTBOX"] == str(app_dir / "eyes-outbox")
    assert relay_spec["env"]["DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN"] == "secret-token"


def test_eyes_profile_is_optional_when_periscope_runtime_is_missing(tmp_path):
    runtime = _eyes_runtime_module()
    specs = runtime.build_eyes_process_specs(
        "secret-token",
        app_dir=tmp_path / "DevelopmentBridgeFusion",
        root=ROOT / "agents",
        relay_python=tmp_path / "python.exe",
        environ={},
    )
    assert specs is None


def test_gui_owns_and_stops_optional_eyes_processes():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert "self.eyes_proxy_proc" in gui
    assert "self.eyes_relay_proc" in gui
    assert "self.eyes_connected" in gui
    assert "self._start_eyes_stack(token" in gui
    assert "self._stop_eyes_stack()" in gui
    assert "Fusion Eyes" in gui
    runtime = (ROOT / "agents" / "fusion_eyes_runtime.py").read_text(encoding="utf-8")
    assert "eyes-outbox" in runtime
    assert "mcp-proxy.exe" in runtime


def test_eyes_installer_pins_qualified_periscope_and_reapplies_lost_event_patch():
    installer = (ROOT / "agents" / "INSTALL_FUSION_EYES.ps1").read_text(encoding="utf-8-sig")
    patch = (ROOT / "agents" / "periscope-lost-event.patch").read_text(encoding="utf-8")

    assert "a676b94a9d54ed3cc2b1620df1f08b5ef34774a7" in installer
    assert "https://github.com/VXNTedits/fusion360-mcp-periscope.git" in installer
    assert 'mcp>=1.27,<2' in installer
    assert 'mcp-proxy==0.12.0' in installer
    assert "apply --reverse --check" in installer
    assert "apply --check" in installer
    assert "install.py" in installer
    assert "--sync" in installer
    assert "PERISCOPE install is dirty outside the managed patch" in installer
    assert "$ManagedDiff" in installer
    assert "$ExpectedPatch" in installer
    assert "Managed PERISCOPE patch differs from bundled patch" in installer

    assert "diff --git a/addin/Periscope/periscope_bridge/marshal.py" in patch
    assert "req.event.wait(min(0.25, remaining))" in patch
    assert "still_pending = request_id in self._pending" in patch
    assert "fireCustomEvent(EVENT_ID, request_id)" in patch


def test_gui_fails_closed_instead_of_reusing_unknown_eyes_port_listener():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert "eyes_proxy_external" not in gui
    assert '''            if tcp_open("127.0.0.1", EYES_PROXY_PORT):
                self.eyes_problem = "порт 18769 занят; Fusion Eyes не запущен"
                self._append_log("[eyes] " + self.eyes_problem)
                return
''' in gui


def test_gui_eyes_events_are_scoped_to_originating_relay_process():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert 'self.events.put(("eyes_connected", (proc, True)))' in gui
    assert 'self.events.put(("eyes_connected", (proc, False)))' in gui
    assert 'self.events.put(("eyes_stopped", (proc, proc.returncode)))' in gui
    assert 'event_proc, connected = value' in gui
    assert 'event_proc, _returncode = value' in gui
    assert gui.count('if event_proc is self.eyes_relay_proc:') >= 2


def test_gui_tears_down_owned_eyes_stack_when_either_relay_exits():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    eyes_start = gui.index('                elif kind == "eyes_stopped":')
    eyes_end = gui.index('                elif kind == "stopped":', eyes_start)
    eyes_block = gui[eyes_start:eyes_end]
    assert 'if event_proc is self.eyes_relay_proc:' in eyes_block
    assert 'self._stop_eyes_stack()' in eyes_block

    primary_start = gui.index('                elif kind == "stopped":', eyes_end)
    primary_end = gui.index('                self._refresh_relay_labels()', primary_start)
    primary_block = gui[primary_start:primary_end]
    assert 'self._stop_eyes_stack()' in primary_block


def test_gui_monitors_proxy_exit_and_tears_down_current_eyes_stack():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert 'target=self._eyes_proxy_watcher, args=(self.eyes_proxy_proc,)' in gui
    assert 'def _eyes_proxy_watcher(self, proc: subprocess.Popen[str]) -> None:' in gui
    assert 'self.events.put(("eyes_proxy_stopped", (proc, proc.returncode)))' in gui
    proxy_start = gui.index('                elif kind == "eyes_proxy_stopped":')
    proxy_end = gui.index('                elif kind == "eyes_stopped":', proxy_start)
    proxy_block = gui[proxy_start:proxy_end]
    assert 'event_proc, _returncode = value' in proxy_block
    assert 'if event_proc is self.eyes_proxy_proc:' in proxy_block
    assert 'self._stop_eyes_stack()' in proxy_block
    assert 'mcp-proxy завершился' in proxy_block

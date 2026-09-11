from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]


def _hands_runtime_module():
    from agents import fusion_hands_runtime
    return fusion_hands_runtime


def _hands_layout(tmp_path):
    app_dir = tmp_path / "DevelopmentBridgeFusion"
    sidecar = app_dir / "shimmer-sidecar"
    source = sidecar / f"extract-97a06e76c289420a721590ddcab334f5f3dc3178/self-host-fusion360-MCP-97a06e76c289420a721590ddcab334f5f3dc3178"
    executable = sidecar / "venv" / "Scripts" / "fusion-mcp.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    relay_python = tmp_path / "relay-python.exe"
    relay_python.write_bytes(b"")
    appdata = tmp_path / "Roaming"
    return app_dir, sidecar, source, executable, relay_python, {"APPDATA": str(appdata), "BASE": "kept"}


def test_hands_profile_pins_shimmer_sidecar_and_distinct_relay(tmp_path):
    runtime = _hands_runtime_module()
    app_dir, sidecar, _source, executable, relay_python, environ = _hands_layout(tmp_path)
    agent = ROOT / "agents" / "windows_fusion_agent.py"

    specs = runtime.build_hands_process_specs(
        "secret-token", app_dir=app_dir, root=ROOT / "agents",
        relay_python=relay_python, environ=environ,
    )

    assert specs is not None
    sidecar, relay = specs
    assert runtime.SHIMMER_UPSTREAM_SHA == "97a06e76c289420a721590ddcab334f5f3dc3178"
    assert runtime.HANDS_MCP_PORT == 18768
    assert runtime.SHIMMER_ADDIN_PORT == 9000
    assert sidecar["argv"] == [
        str(executable), "run", "--transport", "http", "--host", "127.0.0.1",
        "--port", "18768", "--addin-url", "http://127.0.0.1:9000",
    ]
    assert sidecar["cwd"] == str(app_dir / "shimmer-sidecar")
    assert sidecar["env"]["BASE"] == "kept"
    assert relay["argv"] == [str(relay_python), str(agent)]
    assert relay["env"]["DEVELOPMENT_BRIDGE_NODE_ID"] == "fusion-hands"
    assert relay["env"]["FUSION_MCP_URL"] == "http://127.0.0.1:18768/mcp"
    assert relay["env"]["DEVELOPMENT_BRIDGE_FUSION_OUTBOX"] == str(app_dir / "hands-outbox")
    assert relay["env"]["DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN"] == "secret-token"


def test_hands_profile_is_missing_when_runtime_or_token_is_missing(tmp_path):
    runtime = _hands_runtime_module()
    app_dir = tmp_path / "DevelopmentBridgeFusion"
    assert runtime.build_hands_process_specs(
        "secret", app_dir=app_dir, root=ROOT / "agents",
        relay_python=tmp_path / "python.exe", environ={"APPDATA": str(tmp_path / "Roaming")},
    ) is None


def test_hands_overlay_inspection_distinguishes_missing_unapplied_applied_and_mismatch(tmp_path):
    runtime = _hands_runtime_module()
    app_dir, sidecar, source, _executable, _relay, environ = _hands_layout(tmp_path)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    addin_source = b"addin overlay\n"
    server_source = b"server overlay\n"
    (overlay / "addin_bridge_cad.py").write_bytes(addin_source)
    (overlay / "server_bridge_cad.py").write_bytes(server_source)
    addin_pre = b"from . import (\n    api,\n    assembly,\n)\n"
    server_pre = (
        b"from fusion_mcp.tools import (\n        api,\n        assembly,\n)\n\n"
        b"def register_all(mcp, client):\n"
        b"    # Read-only generic-API helpers (introspect/docs) are always available.\n"
        b"    api.register(mcp, client)\n"
    )
    manifest = {
        "upstream_sha": runtime.SHIMMER_UPSTREAM_SHA,
        "targets": {
            "addin_ops_init": {"path": "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py", "sha256_before": hashlib.sha256(addin_pre).hexdigest()},
            "server_tools_init": {"path": "server/fusion_mcp/tools/__init__.py", "sha256_before": hashlib.sha256(server_pre).hexdigest()},
        },
    }
    (overlay / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert runtime.inspect_hands_overlay(tmp_path / "absent", environ=environ, overlay_dir=overlay).state == "missing"
    source_addin = source / manifest["targets"]["addin_ops_init"]["path"]
    source_server = source / manifest["targets"]["server_tools_init"]["path"]
    source_addin.parent.mkdir(parents=True)
    source_server.parent.mkdir(parents=True)
    source_addin.write_bytes(addin_pre)
    source_server.write_bytes(server_pre)
    addin = Path(environ["APPDATA"]) / "Autodesk/Autodesk Fusion 360/API/AddIns/Fusion360MCP/fusion_mcp_addin/ops/__init__.py"
    server = sidecar / "venv/Lib/site-packages/fusion_mcp/tools/__init__.py"
    addin.parent.mkdir(parents=True)
    server.parent.mkdir(parents=True)
    addin.write_bytes(addin_pre)
    server.write_bytes(server_pre)
    assert runtime.inspect_hands_overlay(app_dir, environ=environ, overlay_dir=overlay).state == "unapplied"

    addin.write_bytes(addin_pre.replace(b"    api,\n    assembly,\n", b"    api,\n    bridge_cad,\n    assembly,\n"))
    server.write_bytes(
        server_pre
        .replace(b"        api,\n        assembly,\n", b"        api,\n        bridge_cad,\n        assembly,\n")
        .replace(
            b"    # Read-only generic-API helpers (introspect/docs) are always available.\n",
            b"    bridge_cad.register(mcp, client)\n\n    # Read-only generic-API helpers (introspect/docs) are always available.\n",
        )
    )
    (addin.parent / "bridge_cad.py").write_bytes(addin_source)
    (server.parent / "bridge_cad.py").write_bytes(server_source)
    assert runtime.inspect_hands_overlay(app_dir, environ=environ, overlay_dir=overlay).state == "applied"
    (server.parent / "bridge_cad.py").write_bytes(b"tampered")
    assert runtime.inspect_hands_overlay(app_dir, environ=environ, overlay_dir=overlay).state == "mismatch"


def test_hands_overlay_apply_is_exact_idempotent_and_refuses_mismatch(tmp_path):
    runtime = _hands_runtime_module()
    app_dir, sidecar, source, _executable, _relay, environ = _hands_layout(tmp_path)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    addin_source = b"addin overlay\n"
    server_source = b"server overlay\n"
    (overlay / "addin_bridge_cad.py").write_bytes(addin_source)
    (overlay / "server_bridge_cad.py").write_bytes(server_source)
    addin_pre = b"from . import (\n    api,\n    assembly,\n)\n"
    server_pre = (
        b"from fusion_mcp.tools import (\n        api,\n        assembly,\n)\n\n"
        b"def register_all(mcp, client):\n"
        b"    # Read-only generic-API helpers (introspect/docs) are always available.\n"
        b"    api.register(mcp, client)\n"
    )
    manifest = {"upstream_sha": runtime.SHIMMER_UPSTREAM_SHA, "targets": {
        "addin_ops_init": {"path": "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py", "sha256_before": hashlib.sha256(addin_pre).hexdigest()},
        "server_tools_init": {"path": "server/fusion_mcp/tools/__init__.py", "sha256_before": hashlib.sha256(server_pre).hexdigest()},
    }}
    (overlay / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    source_addin = source / manifest["targets"]["addin_ops_init"]["path"]
    source_server = source / manifest["targets"]["server_tools_init"]["path"]
    source_addin.parent.mkdir(parents=True); source_server.parent.mkdir(parents=True)
    source_addin.write_bytes(addin_pre); source_server.write_bytes(server_pre)
    addin = Path(environ["APPDATA"]) / "Autodesk/Autodesk Fusion 360/API/AddIns/Fusion360MCP/fusion_mcp_addin/ops/__init__.py"
    server = sidecar / "venv/Lib/site-packages/fusion_mcp/tools/__init__.py"
    addin.parent.mkdir(parents=True)
    server.parent.mkdir(parents=True)
    addin.write_bytes(addin_pre)
    server.write_bytes(server_pre)
    first = runtime.ensure_hands_overlay(app_dir, environ=environ, overlay_dir=overlay)
    installed = [addin, addin.parent / "bridge_cad.py", server, server.parent / "bridge_cad.py"]
    snapshot = {str(path): path.read_bytes() for path in installed}
    second = runtime.ensure_hands_overlay(app_dir, environ=environ, overlay_dir=overlay)
    assert first.state == "applied"
    assert second.state == "applied"
    assert snapshot == {str(path): path.read_bytes() for path in installed}
    assert len(snapshot) == 4

    server.write_bytes(b"unknown")
    before = dict(snapshot)
    refused = runtime.ensure_hands_overlay(app_dir, environ=environ, overlay_dir=overlay)
    assert refused.state == "mismatch"
    assert server.read_bytes() == b"unknown"
    assert (addin.parent / "bridge_cad.py").read_bytes() == before[str(addin.parent / "bridge_cad.py")]


def test_restart_backoff_is_bounded_and_resets_after_recovery():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    namespace = {"time": __import__("time")}
    start = gui.index("class RestartBackoff:")
    end = gui.index("\n\nclass DATA_BLOB", start)
    exec(gui[start:end], namespace)
    backoff = namespace["RestartBackoff"](delays=(1.0, 2.0, 4.0))
    assert [backoff.fail(now=10.0), backoff.fail(now=10.0), backoff.fail(now=10.0), backoff.fail(now=10.0)] == [11.0, 12.0, 14.0, 14.0]
    assert not backoff.ready(now=13.9)
    assert backoff.ready(now=14.0)
    backoff.recovered()
    assert backoff.fail(now=20.0) == 21.0


def test_gui_is_one_auto_supervisor_with_explicit_provider_rows_and_owned_hands():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert "Reference — Autodesk MCP / fusion-workstation" in gui
    assert "Eyes — PERISCOPE / fusion-eyes" in gui
    assert "Hands — Shimmer / fusion-hands" in gui
    assert "self.hands_sidecar_proc" in gui and "self.hands_relay_proc" in gui
    assert "self.after(250, self._supervise)" in gui
    assert "self._start_hands_stack(token" in gui
    assert "self._stop_hands_stack()" in gui
    assert 'порт 18768 занят; Hands не запущен' in gui
    assert "hands_sidecar_deadline" in gui
    assert "_continue_hands_start" in gui
    assert "HANDS_SIDECAR_LOG" in gui and "HANDS_RELAY_LOG" in gui
    assert "START_FUSION_HANDS" not in gui
    assert "qualification is Bridge-owned/session-scoped" in gui
    assert "supported" not in gui


def test_hands_sidecar_start_is_not_blocked_by_addin_port_9000():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    start = gui.index("    def _start_hands_stack")
    end = gui.index("    def _continue_hands_start", start)
    block = gui[start:end]
    assert 'tcp_open("127.0.0.1", SHIMMER_ADDIN_PORT)' not in block
    assert 'self.hands_sidecar_proc = subprocess.Popen' in block
    assert 'self.hands_pending_relay = (relay_spec, creationflags)' in block


def test_provider_exit_handlers_are_independent_and_cleanup_only_owned_handles():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    primary = gui[gui.index('elif kind == "stopped"'):gui.index('self._refresh_relay_labels()', gui.index('elif kind == "stopped"'))]
    assert "_stop_eyes_stack" not in primary
    assert "_stop_hands_stack" not in primary
    assert 'elif kind == "hands_sidecar_stopped"' in gui
    assert 'elif kind == "hands_stopped"' in gui
    stop = gui[gui.index("def stop_relay"):gui.index("def forget_token")]
    assert "self._stop_eyes_stack()" in stop
    assert "self._stop_hands_stack()" in stop
    assert "self._terminate_owned_process(self.proc)" in stop
    assert "taskkill" not in stop


def test_reference_exit_event_is_scoped_to_the_popen_that_emitted_it():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert 'self.events.put(("stopped", (proc, proc.returncode)))' in gui
    block = gui[gui.index('elif kind == "stopped"'):gui.index('self._refresh_relay_labels()', gui.index('elif kind == "stopped"'))]
    assert "event_proc, _returncode = value" in block
    assert "if event_proc is self.proc:" in block


def test_unified_bootstrap_and_readme_describe_manual_two_launch_workflow_only():
    bootstrap = (ROOT / "agents" / "START_FUSION_GUI.ps1").read_text(encoding="utf-8-sig")
    readme = (ROOT / "agents" / "FUSION_GUI_README.txt").read_text(encoding="utf-8")
    assert "fusion_hands_runtime.py" in bootstrap
    assert "fusion_shimmer_overlay" in bootstrap
    assert "mcp==2.0.0" in bootstrap
    assert "pythonw.exe" in bootstrap and "2>$null" in bootstrap
    assert "Startup" not in bootstrap and "schtasks" not in bootstrap
    assert "Launch Autodesk Fusion 360 manually" in readme
    assert "launch START_FUSION_GUI.cmd manually" in readme
    assert "automatically supervises Reference, Eyes, and Hands" in readme
    assert "separate Hands launcher" in readme
    assert "DevelopmentBridgeFusion\\shimmer-sidecar" in readme
    assert "venv\\Scripts" in readme
    assert "venv\\Lib\\site-packages\\fusion_mcp" in readme
    assert "extract-<sha>" in readme
    assert ".development-bridge-upstream-sha" not in readme
    assert "click Start" not in readme
    assert "Windows Startup" not in readme

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
                self.backoffs["eyes"].fail()
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


def test_gui_tears_down_owned_eyes_stack_only_when_an_eyes_child_exits():
    gui = (ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    eyes_start = gui.index('                elif kind == "eyes_stopped":')
    eyes_end = gui.index('                elif kind == "stopped":', eyes_start)
    eyes_block = gui[eyes_start:eyes_end]
    assert 'if event_proc is self.eyes_relay_proc:' in eyes_block
    assert 'self._stop_eyes_stack()' in eyes_block

    primary_start = gui.index('                elif kind == "stopped":', eyes_end)
    primary_end = gui.index('                self._refresh_relay_labels()', primary_start)
    primary_block = gui[primary_start:primary_end]
    assert 'self._stop_eyes_stack()' not in primary_block


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

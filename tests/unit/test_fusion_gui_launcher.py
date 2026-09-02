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

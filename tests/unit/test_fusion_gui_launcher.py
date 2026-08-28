from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_fallback_launcher_never_uses_slow_test_net_connection():
    text=(ROOT / "agents" / "START_FUSION_AGENT.ps1").read_text(encoding="utf-8-sig")
    assert "Test-NetConnection" not in text

def test_gui_bootstrap_is_consoleless_and_gui_uses_dpapi():
    bootstrap=(ROOT / "agents" / "START_FUSION_GUI.ps1").read_text(encoding="utf-8-sig")
    gui=(ROOT / "agents" / "fusion_relay_gui.pyw").read_text(encoding="utf-8")
    assert "pythonw.exe" in bootstrap
    assert "CryptProtectData" in gui and "CryptUnprotectData" in gui
    assert "DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN" in gui
    assert "Test-NetConnection" not in gui
    assert "Bridge heartbeat" in gui
    assert "Fusion MCP watchdog" in gui

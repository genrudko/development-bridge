from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "browser-extension" / "bridge-binder"


def _text(name: str) -> str:
    return (EXT / name).read_text(encoding="utf-8")


def test_manifest_limits_required_host_scope_and_declares_dynamic_bridge_permission():
    manifest = json.loads(_text("manifest.json"))
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) >= {"storage", "tabs", "activeTab"}
    assert manifest["host_permissions"] == ["https://chatgpt.com/*"]
    assert manifest["optional_host_permissions"] == ["https://*/*"]
    assert manifest["action"]["default_popup"] == "popup.html"
    assert manifest["options_ui"]["page"] == "options.html"


def test_popup_requires_explicit_bind_click_and_uses_active_chatgpt_tab():
    js = _text("popup.js")
    assert 'addEventListener("click"' in js
    assert "tabs.query" in js
    assert 'hostname !== "chatgpt.com"' in js
    assert "route_id" in js and "generation" in js and "url" in js
    assert "/binder/pending" in js and "/binder/complete" in js
    assert "operation_id" not in js
    assert "bind_" not in js


def test_multiple_pending_routes_require_owner_selection():
    js = _text("popup.js")
    assert "pending.length === 1" in js
    assert "pending.length > 1" in js
    assert "selectedIndex = 0" in js


def test_extension_configuration_is_local_and_requests_only_configured_bridge_origin():
    options = _text("options.js")
    popup = _text("popup.js")
    assert "storage.local" in options
    assert "storage.local" in popup
    assert "permissions.request" in options
    assert "new URL" in options
    assert "origin" in options
    assert "routeControlBaseUrl" in options
    assert "binderToken" in options


def test_no_hard_coded_deployment_secret_or_bridge_host():
    combined = "\n".join(
        _text(name)
        for name in ("manifest.json", "popup.html", "popup.js", "options.html", "options.js", "README.md")
    )
    assert "mcp.vigilante.website" not in combined
    assert "test-browser-binder-secret" not in combined
    assert "DEVELOPMENT_BRIDGE_COORDINATOR_BROWSER_BINDER_TOKEN" not in combined
    assert "operation_id" not in combined

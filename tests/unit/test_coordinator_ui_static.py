from pathlib import Path


def test_coordinator_ui_uses_adaptive_leased_polling():
    html = (Path(__file__).parents[2] / "app/coordinator/x_ui.html").read_text(encoding="utf-8")
    assert "setInterval(poll, 1000)" not in html
    assert "pollDelayMs = 5000" in html
    assert "POLL_LEASE_TTL_MS = 7000" in html
    assert "development-bridge/poll-leader-v1/${channelId}" in html
    assert "schedulePoll(250)" in html


def test_coordinator_ui_prefers_chatgpt_followup_bridge_with_mcp_fallback():
    html = (Path(__file__).parents[2] / "app/coordinator/x_ui.html").read_text(encoding="utf-8")
    assert 'typeof window.openai?.sendFollowUpMessage === "function"' in html
    assert "window.openai.sendFollowUpMessage" in html
    assert "scrollToBottom: false" in html
    assert "app.sendMessage" in html
    assert "await sendChatMessage(message);" in html
    assert "await sendChatMessage(deliveredMessage);" in html

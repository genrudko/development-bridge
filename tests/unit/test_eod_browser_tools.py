from types import SimpleNamespace

import pytest
from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.settings import EodBrowserSettings
from app.tools import eod_browser as module
from app.tools.eod_browser import SAFE_BROWSER_TOOLS, eod_browser_tools


def container(enabled=True):
    return SimpleNamespace(
        settings=SimpleNamespace(eod_browser=EodBrowserSettings(enabled=enabled))
    )


def test_tools_are_absent_when_disabled():
    assert eod_browser_tools(container(False)) == ()


def test_call_schema_excludes_rce_and_upload_tools():
    tools = eod_browser_tools(container())
    call = next(item for item in tools if item.definition.name == "eod_browser_call")
    choices = set(call.definition.input_schema["properties"]["tool_name"]["enum"])
    assert choices == SAFE_BROWSER_TOOLS
    assert "browser_run_code_unsafe" not in choices
    assert "browser_file_upload" not in choices
    assert "browser_drop" not in choices


def test_remote_browser_endpoint_is_rejected():
    with pytest.raises(ValueError, match="localhost"):
        EodBrowserSettings(enabled=True, url="https://example.com/sse")


@pytest.mark.asyncio
async def test_navigation_is_bounded_to_eod_origin(monkeypatch):
    async def fake_call(url, tool_name, arguments):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="ok")],
            isError=False,
        )

    monkeypatch.setattr(module, "_call_upstream", fake_call)
    call = next(
        item
        for item in eod_browser_tools(container())
        if item.definition.name == "eod_browser_call"
    )
    with pytest.raises(BridgeError) as captured:
        await call.handler(
            None,
            SimpleNamespace(
                arguments={
                    "tool_name": "browser_navigate",
                    "arguments": {"url": "https://example.com/"},
                }
            ),
            SimpleNamespace(request_id="req-1"),
        )
    assert captured.value.code == ErrorCode.POLICY_VIOLATION

    result = await call.handler(
        None,
        SimpleNamespace(
            arguments={
                "tool_name": "browser_navigate",
                "arguments": {"url": "http://127.0.0.1:8766/accounts/login/"},
            }
        ),
        SimpleNamespace(request_id="req-2"),
    )
    assert result.is_error is False
    assert result.content[-1].text == "ok"

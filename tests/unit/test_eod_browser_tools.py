from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import types

from app.api.errors import BridgeError, ErrorCode
from app.settings import EodBrowserSettings
from app.tools import eod_browser as module
from app.tools.eod_browser import SAFE_BROWSER_TOOLS, eod_browser_tools


def container(enabled=True, output_dir=None):
    return SimpleNamespace(
        settings=SimpleNamespace(
            eod_browser=EodBrowserSettings(enabled=enabled, output_dir=output_dir)
        )
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
    async def fake_call(self, tool_name, arguments):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="ok")],
            isError=False,
        )

    monkeypatch.setattr(module._BrowserWorker, "call_tool", fake_call)
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


@pytest.mark.asyncio
async def test_worker_reuses_one_session_for_sequential_calls(monkeypatch):
    sessions = []
    transports = []

    class FakeTransport:
        async def __aenter__(self):
            transports.append(self)
            return object(), object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, read, write):
            self.calls = []
            sessions.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

        async def call_tool(self, name, arguments, read_timeout_seconds):
            self.calls.append((name, arguments, read_timeout_seconds))
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=name)],
                isError=False,
            )

    monkeypatch.setattr(module, "sse_client", lambda *args, **kwargs: FakeTransport())
    monkeypatch.setattr(module, "ClientSession", FakeSession)

    worker = module._BrowserWorker("http://127.0.0.1:8931/sse", launcher=None)
    first = await worker.call_tool("browser_navigate", {"url": "http://127.0.0.1:8766/"})
    second = await worker.call_tool("browser_snapshot", {})
    await worker.close()

    assert first.content[0].text == "browser_navigate"
    assert second.content[0].text == "browser_snapshot"
    assert len(transports) == 1
    assert len(sessions) == 1
    assert [item[0] for item in sessions[0].calls] == [
        "browser_navigate",
        "browser_snapshot",
    ]


def test_relative_browser_output_directory_is_rejected():
    with pytest.raises(ValueError, match="output_dir"):
        EodBrowserSettings(enabled=True, output_dir=Path("relative-output"))


@pytest.mark.asyncio
async def test_screenshot_is_inlined_from_bounded_output_directory(monkeypatch, tmp_path):
    screenshot = tmp_path / "proof.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nproof")

    async def fake_call(self, tool_name, arguments):
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text="### Result\n- [Screenshot of viewport](./proof.png)",
                )
            ],
            isError=False,
        )

    monkeypatch.setattr(module._BrowserWorker, "call_tool", fake_call)
    call = next(
        item
        for item in eod_browser_tools(container(output_dir=tmp_path))
        if item.definition.name == "eod_browser_call"
    )
    result = await call.handler(
        None,
        SimpleNamespace(
            arguments={
                "tool_name": "browser_take_screenshot",
                "arguments": {"filename": "proof.png"},
            }
        ),
        SimpleNamespace(request_id="req-image"),
    )

    images = [item for item in result.content if isinstance(item, types.ImageContent)]
    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    assert images[0].data


def test_screenshot_path_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / "escape.png"
    outside.write_bytes(b"not-used")
    result = types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text="### Result\n- [Screenshot of viewport](./../escape.png)",
            )
        ],
        isError=False,
    )
    with pytest.raises(BridgeError) as captured:
        module._inline_screenshot_content(tmp_path, result)
    assert captured.value.code == ErrorCode.POLICY_VIOLATION

import base64
from types import SimpleNamespace

import pytest
from mcp import types

from app.tools.visio import visio_tools


@pytest.mark.asyncio
async def test_visio_snapshot_returns_image_resource_link_without_inline_image():
    encoded = "iVBORw0KGgo="

    class Desktop:
        async def call(self, node_id, tool_name, arguments, journal):
            assert node_id == "visio-workstation"
            assert tool_name == "render_page_png"
            assert arguments == {"doc_name": "Doc.vsdx", "page": "Page-1"}
            assert journal is None
            return {"external_result": {"result_id": "result-1"}}

        def external_result(self, reference):
            assert reference == {"result_id": "result-1"}
            return (
                {
                    "content": [
                        {"type": "image", "data": encoded, "mimeType": "image/png"}
                    ],
                    "isError": False,
                },
                {
                    "size_bytes": 999999,
                    "sha256": "a" * 64,
                    "file_name": "visio-result.json",
                    "resources": [
                        {
                            "uri": "https://bridge.example/mcp/desktop-results/exports/image-token",
                            "file_name": "visio-page.png",
                            "mime_type": "image/png",
                            "size_bytes": 8,
                        }
                    ],
                },
            )

    tool = next(
        item
        for item in visio_tools(SimpleNamespace(desktop_nodes=Desktop()))
        if item.definition.name == "visio_snapshot"
    )
    result = await tool.handler(
        None,
        SimpleNamespace(
            arguments={
                "node_id": "visio-workstation",
                "doc_name": "Doc.vsdx",
                "page": "Page-1",
            }
        ),
        SimpleNamespace(request_id="request-1"),
    )

    assert not any(isinstance(block, types.ImageContent) for block in result.content)
    links = [block for block in result.content if isinstance(block, types.ResourceLink)]
    assert len(links) == 1
    assert str(links[0].uri).endswith("/image-token")
    assert links[0].mime_type == "image/png"
    assert encoded not in str(result.content)


@pytest.mark.asyncio
async def test_visio_result_view_returns_retained_image_as_image_content():
    png = b"\x89PNG\r\n\x1a\nvisio-page"
    uri = "https://bridge.example/mcp/desktop-results/exports/r1.result.capability"

    class Desktop:
        def external_image_resource(self, resource_uri):
            assert resource_uri == uri
            return png, {
                "uri": uri,
                "file_name": "visio-page.png",
                "mime_type": "image/png",
                "size_bytes": len(png),
                "sha256": "b" * 64,
            }

    tool = next(
        item
        for item in visio_tools(SimpleNamespace(desktop_nodes=Desktop()))
        if item.definition.name == "visio_result_view"
    )
    result = await tool.handler(
        None,
        SimpleNamespace(arguments={"resource_uri": uri}),
        SimpleNamespace(request_id="request-view-1"),
    )

    images = [block for block in result.content if isinstance(block, types.ImageContent)]
    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    assert base64.b64decode(images[0].data) == png
    assert "visio-page.png" in result.content[0].text

@pytest.mark.asyncio
async def test_visio_managed_update_sends_only_server_pinned_extension():
    calls = []

    class Desktop:
        async def call(self, node_id, tool_name, arguments, journal):
            calls.append((node_id, tool_name, arguments, journal))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": '{"managed_update":"PASS","version":"2026.10.03.51"}',
                    }
                ],
                "isError": False,
            }

    tool = next(
        item
        for item in visio_tools(SimpleNamespace(desktop_nodes=Desktop()))
        if item.definition.name == "visio_managed_update"
    )
    result = await tool.handler(
        None,
        SimpleNamespace(arguments={"node_id": "visio-workstation"}),
        SimpleNamespace(request_id="request-update-1"),
    )

    assert result.is_error is False
    assert len(calls) == 1
    node_id, tool_name, arguments, journal = calls[0]
    assert node_id == "visio-workstation"
    assert tool_name == "__openai_visio_managed_update"
    assert arguments["version"] == "2026.10.03.51"
    assert arguments["file_name"] == "visio_managed_extension.py"
    assert len(arguments["sha256"]) == 64
    assert arguments["content_b64"]
    assert journal["mutation"] is True


def test_managed_visio_extension_uses_public_mcp_types():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "from mcp import types" in source
    assert "mcp.server.mcpserver" not in source
    assert "types.ImageContent" in source


@pytest.mark.asyncio
async def test_visio_managed_update_embeds_console_source():
    calls = []

    class Desktop:
        async def call(self, node_id, tool_name, arguments, journal):
            calls.append((node_id, tool_name, arguments, journal))
            return {
                "content": [{"type": "text", "text": '{"managed_update":"PASS","version":"2026.10.03.51"}'}],
                "isError": False,
            }

    tool = next(
        item for item in visio_tools(SimpleNamespace(desktop_nodes=Desktop()))
        if item.definition.name == "visio_managed_update"
    )
    await tool.handler(
        None,
        SimpleNamespace(arguments={"node_id": "visio-workstation"}),
        SimpleNamespace(request_id="request-update-console"),
    )
    payload = base64.b64decode(calls[0][2]["content_b64"])
    assert b"__CONSOLE_SOURCE_B64__" not in payload
    assert b"CONSOLE_SOURCE_B64" in payload
    assert b"Visio Bridge Console" in base64.b64decode(
        payload.split(b'CONSOLE_SOURCE_B64 = "',1)[1].split(b'"',1)[0]
    )


def test_managed_visio_extension_has_transactional_exact_duplicate_tool():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def duplicate_shapes_exact(" in source
    assert "app.DoCmd(1024)" in source
    assert "duplicated = window.Selection" in source
    assert 'duplicated.Move(correction_dx, correction_dy, "mm")' in source
    assert "native_duplicate_offset_mm" in source
    assert "verified_final_offset_mm" in source
    assert "verification_tolerance_mm" in source
    assert 'glue_items_json: str = "[]"' in source
    assert 'new_cell_id: str = ""' in source
    assert 'shape.AddNamedRow(242, "EnergoLogicCellId", 0)' in source
    assert 'shape.AddSection(242)' in source
    assert 'identity_cell.FormulaU = f' in source
    assert '"identity_results": identity_results' in source
    assert '"new_cell_id": cell_id or None' in source
    assert "source_to_new_shape_ids" in source
    assert "GlueTo(target_cell)" in source
    assert "connects = shape.Connects" in source
    assert "Glue formula verification failed" in source
    assert "formula_verified" in source
    assert "post_commit_connects_verification_required" in source
    assert "acceptable_target_names" in source
    assert "Connections.{expected_row}.X" in source
    assert "app.DoCmd(1024)" in source
    assert "app.DoCmd(1017)" in source
    assert "preexisting_shape_ids" in source
    assert '"undo_strategy": "visCmdUFEditDuplicate"' in source
    assert '"single_user_undo_expected": True' in source
    assert "1..100 items" in source
    assert "+/-2000 mm" in source


def test_managed_visio_extension_has_bounded_single_undo_tool():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def undo_once(" in source
    assert "app.DoCmd(1017)" in source
    assert '"undo_command": "visCmdEditUndo"' in source
    assert "shape_count_before" in source
    assert "shape_count_after" in source


def test_managed_visio_extension_has_read_only_undo_status_tool():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def get_undo_status(" in source
    assert '"undo_enabled": bool(app.UndoEnabled)' in source
    assert '"undo_levels": int(app.Settings.UndoLevels)' in source
    assert '"document_undo_enabled": bool(page_obj.Document.UndoEnabled)' in source
    assert 'current_scope = int(app.CurrentScope)' in source
    assert '"undo_enabled_before": undo_enabled_before' in source


def test_managed_visio_extension_has_transactional_exact_move_tool():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def move_shapes_exact(" in source
    assert 'detach_items_json: str = "[]"' in source
    assert 'glue_items_json: str = "[]"' in source
    assert 'document.BeginUndoScope("EnergoLogic: Move Shapes Exact")' in source
    assert 'selected.Move(dx, dy, "mm")' in source
    assert 'x_cell.FormulaU = f"{before_x_mm:.12g} mm"' in source
    assert 'y_cell.FormulaU = f"{before_y_mm:.12g} mm"' in source
    assert "connection_formula_matches" in source
    assert "Detach verification failed" in source
    assert "Visio exact move verification failed" in source
    assert "Glue formula verification failed for moved shape" in source
    assert "document.EndUndoScope(scope_id, False)" in source


def test_managed_visio_extension_has_bounded_keyboard_undo_tool():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def keyboard_undo_once(" in source
    assert "GetAncestor(hwnd, GA_ROOT)" in source
    assert '"root_window_handle32": root_hwnd' in source
    assert "window.WindowHandle32" in source
    assert "SetForegroundWindow" in source
    assert "AttachThreadInput" in source
    assert "BringWindowToTop" in source
    assert "VK_CONTROL = 0x11" in source
    assert "VK_Z = 0x5A" in source
    assert '"keyboard_chord": "Ctrl+Z"' in source


def test_connection_point_reader_reports_page_coordinate_projection():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "shape.XYToPage(x_iu, y_iu)" in source
    assert '"connection_row": row_index + 1' in source
    assert '"page_x_mm"' in source
    assert '"page_y_mm"' in source
    assert '"page_transform_error"' in source


def test_managed_visio_extension_has_read_only_host_capabilities_probe():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()
    policy = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "tools"
        / "visio.py"
    ).read_text()

    assert "def get_extension_host_capabilities(" in source
    assert "app.VBAEnabled" in source
    assert "document.MacrosEnabled" in source
    assert "app.VBE" in source
    assert "app.COMAddIns" in source
    assert '"get_extension_host_capabilities"' in policy


def test_managed_visio_extension_has_bounded_qol_vba_host_probe():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def install_energologic_qol_vba_host(" in source
    assert "def run_energologic_qol_undo_probe(" in source
    assert 'module_name = "EnergoLogicQolHost"' in source
    assert 'Public Sub UndoProbeDuplicate40()' in source
    assert 'BeginUndoScope("EnergoLogic: Undo Probe Duplicate")' in source
    assert 'EndUndoScope scopeId, True' in source
    assert 'document.ExecuteLine("EnergoLogicQolHost.UndoProbeDuplicate40")' in source
    assert 'full_name.suffix.lower() != ".vsdm"' in source
    assert "AddFromString(vba_source)" in source


def test_managed_visio_extension_has_bounded_macros_ui_probe():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def keyboard_run_energologic_qol_undo_probe(" in source
    assert 'macro_name = "UndoProbeDuplicate40"' in source
    assert "chord(VK_MENU, VK_F8)" in source
    assert "ascii_text(macro_name)" in source
    assert "GetKeyState(VK_CAPITAL)" in source
    assert 'vk = ord(char.upper())' in source
    assert "VkKeyScanW" not in source
    assert '"launch_path": "Alt+F8 Macros dialog"' in source
    assert "EnumWindows" in source
    assert "EnumChildWindows" in source
    assert "GetDlgCtrlID" in source


def test_managed_visio_extension_has_shapesheet_action_ui_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def install_energologic_qol_action_probe(" in source
    assert "def keyboard_run_energologic_qol_action_probe(" in source
    assert "visSectionAction" in source or "section = 240" in source
    assert 'Actions.EnergoLogicUndoProbe.Action' in source
    assert 'CALLTHIS("EnergoLogicQolHost.UndoProbeDuplicate40FromShape",)' in source
    assert "chord(VK_SHIFT, VK_F10)" in source
    assert '%&J EnergoLogic Undo Probe' in source
    assert "press(VK_END)" in source
    assert "press(VK_RETURN)" in source
    assert "expected_count = before_count + 8" in source
    assert "for _ in range(60):" in source


def test_shapesheet_ui_probe_macro_has_no_nested_undo_scope():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / 'managed' / 'visio' / 'visio_managed_extension.py').read_text()
    start = source.index('Public Sub UndoProbeDuplicate40FromShape')
    end = source.index('End Sub', start)
    block = source[start:end]
    assert 'Application.DoCmd 1024' in block
    assert 'dup.Move 40#, 0#, "mm"' in block
    assert 'BeginUndoScope' not in block


def test_managed_visio_extension_has_mouse_shapesheet_action_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def mouse_run_energologic_qol_action_probe(" in source
    assert 'class_buf.value != "#32768"' in source
    assert "MN_GETHMENU = 0x01E1" in source
    assert "GetMenuStringW" in source
    assert "GetMenuItemRect" in source
    assert "EnumWindows(enum_popup, 0)" in source
    assert 'class_buf.value != "#32768"' in source
    assert "target_pid" in source
    assert "mouse_event(MOUSEEVENTF_LEFTDOWN" in source
    assert 'target_text = "J EnergoLogic Undo Probe"' in source


def test_managed_visio_extension_has_custom_vba_undo_unit_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert 'undo_class_name = "EnergoLogicUndoUnit"' in source
    assert "Implements Visio.IVBUndoUnit" in source
    assert "Private Sub IVBUndoUnit_Do(ByVal pMgr As Visio.IVBUndoManager)" in source
    assert "pMgr.Add Me" in source
    assert 'IVBUndoUnit_Description = "EnergoLogic: Duplicate Cell"' in source
    assert "Application.AddUndoUnit unit" in source
    assert "def run_energologic_qol_custom_undo_probe(" in source
    assert 'document.ExecuteLine("EnergoLogicQolHost.CustomUndoProbeDuplicate40")' in source


def test_managed_visio_extension_has_bounded_shapesheet_cell_trigger_probe():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "visio"
        / "visio_managed_extension.py"
    ).read_text()

    assert "def trigger_energologic_qol_action_probe(" in source
    assert 'cell_name = "Actions.EnergoLogicUndoProbe.Action"' in source
    assert "action_cell.Trigger()" in source
    assert '"launch_path": "ShapeSheet Cell.Trigger"' in source


def test_mouse_shapesheet_probe_focuses_drawing_window_and_reports_ui_windows():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "user32.SetFocus(hwnd)" in source
    assert "focused_child = int(user32.GetFocus())" in source
    assert "visible_windows=" in source


def test_keyboard_shapesheet_probe_targets_office_net_ui_menu():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert 'menu_class == "Net UI Tool Window"' in source
    assert '"menu_window_class": menu_class' in source
    assert "user32.SetFocus(hwnd)" in source


def test_keyboard_shapesheet_probe_runs_forced_bottom_action_with_end_enter():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert '%&J EnergoLogic Undo Probe' in source
    assert "VK_END = 0x23" in source
    assert "press(VK_END)" in source
    assert "press(VK_RETURN)" in source


def test_managed_visio_extension_has_uia_netui_action_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def uia_run_energologic_qol_action_probe(" in source
    assert 'GetModule("UIAutomationCore.dll")' in source
    assert "ElementFromHandle(menu_hwnd)" in source
    assert '"EnergoLogic Undo Probe" in row["name"]' in source
    assert "CurrentBoundingRectangle" in source

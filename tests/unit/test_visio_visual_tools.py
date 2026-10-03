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
                        "text": '{"managed_update":"PASS","version":"2026.10.03.63"}',
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
    assert arguments["version"] == "2026.10.03.63"
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
                "content": [{"type": "text", "text": '{"managed_update":"PASS","version":"2026.10.03.63"}'}],
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


def test_managed_visio_extension_has_read_only_vsto_build_capability_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    policy = (
        Path(__file__).resolve().parents[2]
        / "app" / "tools" / "visio.py"
    ).read_text()
    assert "def get_vsto_build_capabilities(" in source
    assert '"devenv.exe"' in source
    assert '"msbuild.exe"' in source
    assert '"vswhere"' in source
    assert '"office_targets"' in source
    assert '"get_vsto_build_capabilities"' in policy


def test_vsto_probe_searches_classic_com_interop_references():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert '"extensibility.dll"' in source
    assert '"office.dll"' in source
    assert '"microsoft.office.interop.visio.dll"' in source
    assert '"reference_candidates": sorted(set(reference_candidates))' in source


def test_managed_visio_extension_has_bounded_classic_com_addin_probe():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def install_energologic_classic_com_addin_probe(" in source
    assert "page_obj = visio._resolve_page(doc_name, parse_page(page))" in source
    assert "def uninstall_energologic_classic_com_addin_probe(" in source
    assert 'ProgId("EnergoLogic.VisioQolAddin")' in source
    assert 'Guid("7D679776-1D6B-4D0D-9123-E3E4FB21F806")' in source
    assert 'label=\'EnergoLogic\'' in source
    assert 'keytip=\'Z\'' in source
    assert 'keytip=\'D\'' in source
    assert "using Extensibility;" in source
    assert "using Microsoft.Office.Core;" in source
    assert "public sealed class VisioQolAddin : IDTExtensibility2, IRibbonExtensibility" in source
    assert "public void OnUndoProbeDuplicate40(IRibbonControl control)" in source
    assert 'app.BeginUndoScope("EnergoLogic: Duplicate Cell Probe")' in source
    assert 'app.DoCmd(1024)' in source
    assert 'duplicate.Move(40.0, 0.0, "mm")' in source
    assert 'visio_addin_key = "Software\\\\Microsoft\\\\Visio\\\\Addins\\\\" + progid' in source
    assert 'stale_office_key = "Software\\\\Microsoft\\\\Office\\\\Visio\\\\Addins\\\\" + progid' in source
    assert '"LoadBehavior", 0' in source
    assert "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}" in source
    assert "Implemented Categories" in source
    assert "winreg.HKEY_CURRENT_USER" in source
    assert "COMAddIns" in source
    assert "addins.Update()" in source
    assert "addin.Connect = True" in source


def test_managed_visio_extension_has_bounded_classic_com_addin_ribbon_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def keyboard_run_energologic_classic_com_addin_probe(" in source
    assert 'addins.Item("EnergoLogic.VisioQolAddin")' in source
    assert "VK_Z = 0x5A" in source
    assert "VK_D = 0x44" in source
    assert '"launch_path": "Office Ribbon KeyTips Alt-Z-D"' in source


def test_managed_visio_extension_has_read_only_classic_com_addin_status_probe():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    policy = (
        Path(__file__).resolve().parents[2]
        / "app" / "tools" / "visio.py"
    ).read_text()
    assert "def get_energologic_classic_com_addin_probe_status(" in source
    assert "pythoncom.CLSIDFromProgID(progid)" in source
    assert "win32com.client.Dispatch(progid)" in source
    assert "addins.Update()" in source
    assert "for index in range(1, int(addins.Count) + 1)" in source
    assert '"get_energologic_classic_com_addin_probe_status"' in policy


def test_classic_com_addin_uses_visio_specific_addins_registry_path():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert '"visio_addin": read_values(' in source
    assert '"stale_office_visio_addin": read_values(' in source
    assert '"visio_addin_registry_key": visio_addin_key' in source
    assert 'Software\\\\Microsoft\\\\Visio\\\\Addins' in source
    assert 'Software\\\\Microsoft\\\\Office\\\\Visio\\\\Addins' in source


def test_managed_visio_extension_has_bounded_crash_diagnostics():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    policy = (
        Path(__file__).resolve().parents[2]
        / "app" / "tools" / "visio.py"
    ).read_text()
    assert "def get_energologic_visio_crash_diagnostics(" in source
    assert "Get-CimInstance Win32_Process" in source
    assert "Get-WinEvent -FilterHashtable" in source
    assert "EnergoLogic\\.VisioQolAddin" in source
    assert '"get_energologic_visio_crash_diagnostics"' in policy


def test_vsto_probe_searches_visual_studio_interop_and_has_bounded_visio_recovery():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert '"microsoft.visualstudio.interop.dll"' in source
    assert "def launch_energologic_visio_qualification_copy(" in source
    assert 'KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm' in source
    assert 'Get-Process VISIO' in source
    assert 'VISIO.EXE' in source


def test_classic_com_addin_uses_real_microsoft_interop_and_separate_connect():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "Microsoft.VisualStudio.Interop.dll" in source
    assert "PowerPivot Excel Add-in" in source
    assert "OFFICE.dll" in source
    assert 'f"/reference:{extensibility_ref}"' in source
    assert 'f"/reference:{office_ref}"' in source
    assert "def connect_energologic_classic_com_addin_probe(" in source
    assert '"connect_attempted": False' in source
    assert '"load_behavior_remains": 0' in source
    assert "public enum ext_ConnectMode" not in source
    assert "public interface IDTExtensibility2" not in source
    assert "public interface IRibbonExtensibility" not in source

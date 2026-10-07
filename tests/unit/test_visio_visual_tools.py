import base64
import hashlib
import lzma
import re
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
        def tools(self, node_id):
            return {
                "tools": [
                    {"name": "stage_energologic_payload_chunk"}
                ]
            }

        async def call(self, node_id, tool_name, arguments, journal):
            calls.append((node_id, tool_name, arguments, journal))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": '{"managed_update":"PASS","version":"2026.10.06.213"}',
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
    assert len(calls) > 2

    node_id, tool_name, arguments, journal = calls[0]
    assert node_id == "visio-workstation"
    assert tool_name == "__openai_visio_managed_update"
    assert arguments["version"] == "2026.10.06.213"
    assert arguments["file_name"] == "visio_managed_extension.py"
    assert len(arguments["sha256"]) == 64
    assert arguments["content_b64"]
    assert len(arguments["content_b64"]) < 100_000
    assert journal["mutation"] is True

    stage_calls = calls[1:]
    assert all(call[1] == "stage_energologic_payload_chunk" for call in stage_calls)
    chunks = []
    expected_offset = 0
    expected_sha = None
    total_size = None
    for _, _, stage_args, stage_journal in stage_calls:
        assert stage_args["payload_name"] == "EnergoLogicVisioEditorAddin.cs"
        assert stage_args["offset"] == expected_offset
        raw = base64.b64decode(stage_args["content_b64"])
        assert 1 <= len(raw) <= 20 * 1024
        chunks.append(raw)
        expected_offset += len(raw)
        expected_sha = stage_args["sha256"]
        total_size = stage_args["total_size"]
        assert stage_journal["mutation"] is True

    reconstructed = b"".join(chunks)
    from pathlib import Path
    canonical = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_bytes()
    assert reconstructed == canonical
    assert total_size == len(canonical)
    assert expected_sha == hashlib.sha256(canonical).hexdigest()
    assert stage_calls[-1][2]["final"] is True
    assert all(call[2]["final"] is False for call in stage_calls[:-1])


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
        def tools(self, node_id):
            return {
                "tools": [
                    {"name": "stage_energologic_payload_chunk"}
                ]
            }

        async def call(self, node_id, tool_name, arguments, journal):
            calls.append((node_id, tool_name, arguments, journal))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": '{"managed_update":"PASS","version":"2026.10.06.213"}',
                    }
                ],
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

    loader = base64.b64decode(calls[0][2]["content_b64"])
    match = re.search(
        br'base64\.b64decode\(\"([A-Za-z0-9+/=]+)\"\)',
        loader,
    )
    assert match
    payload = lzma.decompress(base64.b64decode(match.group(1)))
    assert b"__CONSOLE_SOURCE_B64__" not in payload
    assert b"CONSOLE_SOURCE_B64" in payload
    console_b64 = payload.split(b'CONSOLE_SOURCE_B64 = "',1)[1].split(b'"',1)[0]
    assert b"Visio Bridge Console" in base64.b64decode(console_b64)
    assert b"def stage_energologic_payload_chunk(" in payload


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


def test_managed_visio_extension_has_full_energologic_editor_ui_installer():
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "def install_energologic_editor_ui(" in source
    assert "def get_energologic_editor_ui_status(" in source
    assert "def uninstall_energologic_editor_ui(" in source
    assert "EnergoLogic.VisioEditorAddin" in source
    assert "native RibbonX + drawing context menu + modeless WinForms parameter panel" in source
    assert '"LoadBehavior", 0' in source


def test_energologic_editor_v2_exposes_bounded_com_api():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'ProgId("EnergoLogic.VisioEditorAddinV364")' in cs
    assert 'AssemblyVersion("0.3.64.0")' in cs
    assert "public interface IEnergoLogicEditorApi" in cs
    assert "ClassInterface(ClassInterfaceType.AutoDual)" in cs
    assert "ApiDuplicateRight" in cs
    assert "ApiRepairGlueApply" in cs
    assert "ApiShowPanel" in cs
    assert "host.Object = this" in cs
    assert "def invoke_energologic_editor_api(" in ext
    assert 'addins.Item("EnergoLogic.VisioEditorAddinV364")' in ext
    assert '"duplicate_right": "ApiDuplicateRight"' in ext
    assert '"repair_glue_apply": "ApiRepairGlueApply"' in ext


def test_editor_api_wrapper_accepts_com_property_style_zero_arg_dispatch():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "def invoke_zero(name):" in source
    assert "return value() if callable(value) else value" in source
    assert 'invoke_zero("ApiVersion")' in source


def test_editor_acceptance_selection_and_api_evidence_are_bounded():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "def set_energologic_editor_acceptance_selection(" in source
    assert '"selection_only": True' in source
    assert '"shape_count_before": before_shape_count' in source
    assert '"shape_count_after": int(page_obj.Shapes.Count)' in source
    assert '"selected_shape_ids": selected' in source


def test_editor_api_can_set_exact_selection_in_same_com_call():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'shape_ids_json: str = ""' in source
    assert "window.DeselectAll()" in source
    assert "window.Select(page_obj.Shapes.ItemFromID(shape_id), 2)" in source
    assert "Visio selection mismatch before editor action" in source
    assert '"requested_shape_ids": requested_selection' in source


def test_editor_cell_discovery_surfaces_inner_reason():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "Причина: " in cs
    assert "last.Message" in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_uses_robust_com_cell_exists_conversion():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private bool CellExists(dynamic shape, string cellName)" in cs
    assert "Convert.ToInt32(raw, CultureInfo.InvariantCulture) != 0" in cs
    assert "(bool)shape.CellExistsU" not in cs
    assert "(bool)target.CellExistsU" not in cs
    assert "(bool)terminal.CellExistsU" not in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_has_no_unsafe_explicit_dynamic_bool_casts():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "(bool)" not in cs
    assert "Convert.ToInt32(sectionExistsRaw, CultureInfo.InvariantCulture) == 0" in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_uses_native_visio_connects_as_topology_source():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "dynamic connects = shape.Connects;" in cs
    assert "connect.FromCell.NameU" in cs
    assert "connect.ToCell.NameU" in cs
    assert "connect.ToSheet.ID" in cs
    assert 'private readonly Regex _connectionCellRegex' in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_formula_fallback_resolves_vtd_shape_names_not_only_sheet_ids():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert 'Groups["target"]' in cs
    assert "candidate.NameU" in cs
    assert "candidate.Name" in cs
    assert 'Regex.Match(targetRef, @"^Sheet\\.(\\d+)$"' in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v28_repair_glue_understands_incoming_native_connects():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert "private HashSet<string> BuildConnectedEndpointIndex(" in cs
    assert "source.ID" in cs
    assert "connect.ToSheet.ID" in cs
    assert "connect.ToCell.NameU" in cs
    assert "connectedEndpoints.Contains(EndpointKey((int)shape.ID, endpoint))" in cs
    assert "connectedEndpoints.Contains(EndpointKey(id, ep))" in cs
    assert "ApiRepairGluePreview() { return RepairGlue(true, false); }" in cs
    assert "ApiRepairGlueApply() { return RepairGlue(false, false); }" in cs
    assert 'RepairGlue(false, true)' in cs


def test_editor_builds_native_glue_index_once_per_diagnostic_command():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    # Repair Glue, Scheme Doctor and Visual Diagnostics each build one native
    # endpoint index for their own command invocation.
    assert cs.count("BuildConnectedEndpointIndex(page)") == 3
    assert "EndpointHasAnyGlue" not in cs
    assert "connected.Add(EndpointKey(sourceId, sourceEndpoint))" in cs
    assert "connected.Add(EndpointKey(endpointOwnerId, targetEndpoint))" in cs

def test_editor_v30_uses_current_source_shape_for_native_connect_index():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert "glue = TryGetGlueTarget(source, sourceEndpoint)" in cs
    assert "connected.Add(EndpointKey(sourceId, sourceEndpoint))" in cs
    assert "ambiguity = String.Join" in cs
    assert "автоматическое восстановление запрещено:" in cs


def test_editor_v31_reuses_proven_glue_target_parser_for_connectivity_index():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert "GlueTarget glue = null;" in cs
    assert "glue = TryGetGlueTarget(source, sourceEndpoint)" in cs
    assert "page.Shapes.ItemFromID(glue.TargetId)" in cs
    assert "connected.Add(EndpointKey(endpointOwnerId, targetEndpoint))" in cs


def test_editor_v32_product_bundle_has_safe_base_copy_coordinates_nudge_and_renumber():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    ext = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "visio_managed_extension.py"
    ).read_text()
    assert "sourceSelection.Duplicate()" in cs
    base_start = cs.index("internal string BasePointTransform")
    base_end = cs.index("internal string Coordinates", base_start)
    assert "app.DoCmd(1024)" not in cs[base_start:base_end]
    assert "internal string Coordinates()" in cs
    assert 'ButtonWide("Показать координаты выделения"' in cs
    assert 'Button("← 1 мм"' in cs
    assert 'Button("1 мм →"' in cs
    assert 'Button("↓ 1 мм"' in cs
    assert 'Button("↑ 1 мм"' in cs
    assert "internal string RenumberCell(string newDesignation)" in cs
    assert "DiscoverCellFromSelection(page)" in cs
    assert "уже используется фигурой" in cs
    assert "Identity сохранена" in cs
    assert "ApiRenumberCell" in cs
    assert '"coordinates": "ApiCoordinates"' in ext
    assert '"nudge_left": "ApiNudgeLeft"' in ext
    assert 'key == "renumber_cell"' in ext


def test_editor_v33_distribute_pitch_avoids_dynamic_tuple_binder():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "List<CellMoveState> plan" in cs
    assert "new CellMoveState" in cs
    assert "Tuple.Create(cells[i], target)" not in cs
    assert "Tuple<CellInfo, dynamic>" not in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v356_move_plans_glue_but_does_not_mutate_inside_addin_callback():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    move = cs[cs.index("internal string MoveCell(int direction)"):cs.index("internal string SelectCell()")]
    assert "InternalGlue = CaptureInternalGlue(page, cell.MemberIds)" in move
    assert "ScheduleTopologyCompletion(" in move
    assert "new List<CellMoveState> { state }" in move
    assert "successPrefix" in move
    assert "BeginUserUndoScope(" not in move
    assert "DetachEndpoint(" not in move
    assert "Selection.Move(" not in move
    assert "scopeTransferred" not in move

def test_editor_v35_verifies_glue_against_formula_when_connects_lag():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private GlueTarget TryGetGlueTargetFromFormula" in cs
    assert "GlueTarget formulaTarget = TryGetGlueTargetFromFormula(shape, endpoint)" in cs
    assert "formulaTarget.TargetId == targetId && formulaTarget.Row == row" in cs
    assert "source {0} {1}; expected {2}/{3}" in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v36_settles_visio_before_restoring_glue():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void SettleVisioAfterGeometryChange()" in cs
    assert "System.Windows.Forms.Application.DoEvents()" in cs
    assert "System.Threading.Thread.Sleep(25)" in cs
    assert cs.count("SettleVisioAfterGeometryChange();") >= 5
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v356_move_undo_scope_is_owned_by_external_helper_process():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    helper = (root / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    move = cs[cs.index("internal string MoveCell(int direction)"):cs.index("internal string SelectCell()")]
    assert "BeginUserUndoScope(" not in move
    schedule = cs[cs.index("private string ScheduleTopologyCompletion("):cs.index("internal string CompletePendingTopology()")]
    assert "_pendingHelperOwnsUndoScope = true" in schedule
    assert "StartExternalMoveTransaction(" in schedule
    assert 'app.BeginUndoScope(scopeName)' in helper
    assert 'app.EndUndoScope(transactionScope, true)' in helper
    assert 'transactionApp.EndUndoScope(transactionScope, false)' in helper

def test_editor_v38_schedules_post_return_topology_completion():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiOperationStatus();" in cs
    assert "public string ApiOperationStatus()" in cs
    assert "private string ScheduleTopologyCompletion" in cs
    assert "_pendingStates = new List<CellMoveState>(states)" in cs
    assert '"pending"' in cs
    assert '"success"' in cs
    assert '"failed_needs_attention"' in cs
    assert "VerifyMovedCellsComplete" in cs
    assert "public void SetStatus(string value)" in cs
    assert '"operation_status": "ApiOperationStatus"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v38_installer_migrates_legacy_versions_and_disconnect_cleans_ui():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "_toggleButton.Click -= _toggleHandler" in cs
    assert "_form.Dispose()" in cs
    assert "_bar.Delete()" in cs
    for version in range(31, 38):
        assert f"EnergoLogic.VisioEditorAddinV{version}" in ext
    assert 'stale_bar = app.CommandBars.Item("EnergoLogic")' in ext
    assert '"migration": "all legacy editor registrations -> v3.64"' in ext


def test_editor_v39_normalizes_non_bus_child_glue_into_cell_graph():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "IsNumberedBusTerminal(page, graphTargetId)" in cs
    assert "graphTargetId = parentId" in cs
    assert "IsNumberedBusTerminal(page, target.TargetId)" in cs
    assert "private bool IsNumberedBusTerminal" in cs
    assert "incoming Glue (for example RU SN -> transformer child)" in cs


def test_editor_v39_initializes_bus_parent_before_dynamic_out_call():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "int parentId = 0;" in cs


def test_editor_v310_maps_nested_descendants_to_top_level_owner():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "AddDescendantOwners(top, (int)top.ID, map)" in cs
    assert "private void AddDescendantOwners" in cs
    assert "map[childId] = topLevelOwnerId" in cs
    assert "AddDescendantOwners(child, topLevelOwnerId, map)" in cs


def test_editor_v311_retries_glue_until_visio_vtd_stabilizes():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void GlueEndpointWithRetry" in cs
    assert "attempt <= 6" in cs
    assert "Thread.Sleep(25)" in cs
    assert "VerifyGlue(shape, endpoint, targetId, row)" in cs
    assert "Glue не стабилизировался после 6 event-isolated попыток" in cs
    assert "GlueEndpointWithRetry(source, edge.Endpoint, target, edge.Row)" in cs


def test_editor_v356_helper_owned_move_has_no_post_commit_visio_readback():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private string FinalizePendingTopologyOperation")]
    helper_branch = complete[complete.index("if (helperOwnsUndoScope)"):complete.index("// Legacy async-scope path")]
    assert "ResolveLivePage(" not in helper_branch
    assert "SelectIds(" not in helper_branch
    assert "VerifyInternalGlue(" not in helper_branch
    assert "один native Undo/Redo unit" in helper_branch

def test_editor_v313_uses_explicit_second_phase_for_topology_completion():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiCompletePendingTopology();" in cs
    assert "public string ApiCompletePendingTopology()" in cs
    assert "internal string CompletePendingTopology()" in cs
    assert "_pendingStates = new List<CellMoveState>(states)" in cs
    assert "RunDistributePitch()" in cs
    assert "StartTopologyCompletionTimer()" in cs
    assert "_addin.CompletePendingTopology()" in cs
    assert "Interval = 350" in cs
    assert '"complete_pending_topology": "ApiCompletePendingTopology"' in ext
    schedule = cs[cs.index("private string ScheduleTopologyCompletion"):cs.index("private void VerifyMovedCellsComplete")]
    assert "BeginInvoke((MethodInvoker)delegate" not in schedule


def test_editor_v314_normalizes_half_glued_endpoint_before_native_glue():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void NormalizeEndpointPairForGlue" in cs
    assert "NormalizeEndpointPairForGlue(shape, endpoint);" in cs
    assert "SetMm(shape, xName, x);" in cs
    assert "SetMm(shape, yName, y);" in cs
    glue_retry = cs[cs.index("private void GlueEndpointWithRetry"):cs.index("private void VerifyGlue")]
    assert glue_retry.index("VerifyGlue(shape, endpoint, targetId, row);") < glue_retry.index("System.Windows.Forms.Application.DoEvents();")
    assert "attempt <= 6" in glue_retry
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v315_suppresses_visio_events_only_around_native_glue_retry():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    glue_retry = cs[cs.index("private void GlueEndpointWithRetry"):cs.index("private void VerifyGlue")]
    assert "previousEventsEnabled = Convert.ToInt32(App.EventsEnabled" in glue_retry
    assert "App.EventsEnabled = 0;" in glue_retry
    assert "finally" in glue_retry
    assert "App.EventsEnabled = previousEventsEnabled;" in glue_retry
    assert glue_retry.index("App.EventsEnabled = 0;") < glue_retry.index("GlueEndpoint(shape, endpoint, target, row);")
    assert "6 event-isolated попыток" in glue_retry
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v356_move_transaction_plan_runs_in_external_helper_boundary():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    helper = (root / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    start = cs[cs.index("private void StartExternalMoveTransaction"):cs.index("private void StartExternalTopologyRestore")]
    assert '"SCOPE\\t"' in start
    assert '"MOVE\\t{0}\\t{1}\\t{2:R}\\t{3:R}\\t{4}\\t{5}"' in start
    assert '"EDGE\\t{0}\\t{1}\\t{2}\\t{3}"' in start
    assert '"SELECT\\t"' in start
    assert "Process.Start(info)" in start
    assert "class MoveStep" in helper
    assert "ApplyMoveStep(" in helper
    assert "glueOwnedEndpoints, geometryExpectations" in helper
    assert "Selection.Move(step.DxMm, step.DyMm, \"mm\")" in helper

def test_editor_v317_external_plan_is_complete_and_not_inprocess_prefiltered():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private void StartExternalExpectedGlueRestore")
    end = cs.index("private string QuoteProcessArgument", start)
    block = cs[start:end]
    assert "TryGetGlueTarget(source, edge.Endpoint)" not in block
    assert "Dictionary<string, GlueEdgeInfo> unique" in block
    assert '"EDGE\\t{0}\\t{1}\\t{2}\\t{3}"' in block
    assert "Topology plan contains conflicting targets" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs

def test_editor_v318_restores_bus_anchor_before_internal_edges():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private void StartExternalTopologyRestore")
    end = cs.index("private void StartExternalExpectedGlueRestore", start)
    block = cs[start:end]
    anchor = block.index("expected.Add(new GlueEdgeInfo")
    internal = block.index("foreach (GlueEdgeInfo edge in state.InternalGlue)")
    assert anchor < internal
    assert "TargetId = state.TargetTerminalId" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs

def test_editor_v319_binds_and_resolves_explicit_cell_identity():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiBindCellIdentity();" in cs
    assert "public string ApiBindCellIdentity() { return BindCellIdentity(); }" in cs
    assert "internal string BindCellIdentity()" in cs
    assert "private string GetCellIdentity(dynamic shape)" in cs
    assert "private CellInfo DiscoverCellByIdentity(" in cs
    discover = cs[cs.index("private CellInfo DiscoverCell(dynamic page, int selectedId)"):cs.index("private CellInfo DiscoverCellByIdentity")]
    assert "GetCellIdentity(page.Shapes.ItemFromID(selectedId))" in discover
    assert "DiscoverCellByIdentity(page, selectedId, explicitCellId, childParent, top)" in discover
    bind = cs[cs.index("internal string BindCellIdentity()"):cs.index("internal string ExactOffset")]
    assert "SetCellIdentity(page.Shapes.ItemFromID(id), cellId)" in bind
    assert "conflicting" not in bind.lower() or "конфликтующие EnergoLogicCellId" in bind
    assert '"bind_cell_identity": "ApiBindCellIdentity"' in ext
    assert 'ButtonWide("Закрепить состав ячейки"' in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v319_identity_membership_is_not_geometry_derived():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private CellInfo DiscoverCellByIdentity")
    end = cs.index("private bool IsNumberedBusTerminal", start)
    block = cs[start:end]
    assert "GetCellIdentity(page.Shapes.ItemFromID(id))" in block
    assert "members.Add(id)" in block
    assert "distance < half" not in block
    assert "anchors.Count != 1" in block
    assert "CoreIds = core.OrderBy" in block
    assert "MemberIds = members" in block


def test_editor_v320_replaces_equipment_from_sample_fail_closed():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiCaptureReplacementSample();" in cs
    assert "string ApiReplaceEquipmentFromSample();" in cs
    assert "internal string CaptureReplacementSample()" in cs
    assert "internal string ReplaceEquipmentFromSample()" in cs
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue")]
    assert "GetCellIdentity(target)" in replace
    assert "EnsureReplaceTargetSafe(page, cell, oldId)" in replace
    assert "CaptureInternalGlue(page, cell.MemberIds)" in replace
    assert "BuildReplacementExpectedGlue(" in replace
    assert "ScheduleStableTopologyCompletion(page, pending, scope)" in replace
    assert "scopeTransferred = true" in replace
    assert "if (!scopeTransferred)" in replace
    assert "app.EndUndoScope(scope, false)" in replace
    assert '"capture_replacement_sample": "ApiCaptureReplacementSample"' in ext
    assert '"replace_equipment_from_sample": "ApiReplaceEquipmentFromSample"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs

def test_editor_v320_has_visio_2010_replacement_fallback():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private bool SupportsNativeReplaceShape()" in cs
    assert "return major >= 15;" in cs
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private bool SupportsNativeReplaceShape")]
    assert "bool useNativeReplaceShape = false;" in replace
    assert "target.ReplaceShape(_replacementMaster, 1)" in replace
    assert "page.Drop(_replacementMaster, oldX / 25.4, oldY / 25.4)" in replace
    assert 'backend = "drop/rewire compatibility"' in replace
    topo = cs[cs.index("private int RestoreReplacementTopology"):cs.index("private void VerifyReplacementTopology")]
    assert topo.index("oldId == cell.AnchorId") < topo.index("foreach (GlueEdgeInfo edge in internalGlue)")
    assert 'Button("Запомнить образец"' in cs
    assert 'Button("Заменить по образцу"' in cs


def test_editor_v321_defers_replacement_topology_until_after_callback():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue")]
    assert "BuildReplacementExpectedGlue(" in replace
    assert "ScheduleStableTopologyCompletion(page, pending, scope)" in replace
    assert "RestoreReplacementTopology(" not in replace
    assert "VerifyReplacementTopology(" not in replace
    assert "ReplacementCompletionState pending" in replace
    assert 'ApiVersion() { return "0.3.64"; }' in cs




def test_editor_v321_generic_external_glue_completion_supports_replacement():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private void StartExternalTopologyRestore")]
    assert "_pendingReplacement" in complete
    assert "StartExternalExpectedGlueRestore(" in complete
    assert "replacement.ExpectedGlue" in complete
    restore = cs[cs.index("private void StartExternalTopologyRestore"):cs.index("private string QuoteProcessArgument")]
    assert "StartExternalExpectedGlueRestore(documentName, pageNameU, expected, token)" in restore
    assert "TryGetGlueTarget(source, edge.Endpoint)" not in restore
    assert "Dictionary<string, GlueEdgeInfo> unique" in restore

def test_topology_helper_accepts_zero_edge_noop_plan():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    assert "Topology plan has no edges" not in helper
    assert '"PASS\\t" +' in helper
    assert "repaired.ToString" in helper
    assert "verified.ToString" in helper

def test_editor_v322_requires_consecutive_clean_replacement_topology_cycles():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private void StartExternalTopologyRestore")]
    assert "ParseTopologyHelperRepairCount(helperResult)" in complete
    assert "_pendingTopologyCycles++" in complete
    assert "_pendingStablePasses++" in complete
    assert "_pendingStablePasses = 0" in complete
    assert "stablePasses < 2" in complete
    assert "completedCycles >= 6" in complete
    assert '"state=stabilizing; token="' in complete
    assert "топология стабилизирована" in complete
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v322_ui_keeps_polling_while_stabilizing():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    timer = cs[cs.index("private void StartTopologyCompletionTimer()"):cs.index("private void RunPitchMeasure()", cs.index("private void StartTopologyCompletionTimer()"))]
    assert 'result.StartsWith("state=external_restoring"' in timer
    assert 'result.StartsWith("state=stabilizing"' in timer
    assert "StartTopologyCompletionTimer();" in timer


def test_editor_v356_finalizer_does_not_touch_visio_after_helper_owned_commit():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    finalizer = cs[cs.index("private string FinalizePendingTopologyOperation"):cs.index("private void AbortPendingTopologyOperation")]
    assert "if (!helperOwnsUndoScope)" in finalizer
    assert "App.EndUndoScope(scopeId, success)" in finalizer  # legacy Replace/Insert only
    assert "Helper-owned success must not touch Visio here" in finalizer
    assert "_form.SetStatus(finalMessage)" not in finalizer

def test_editor_v323_ui_timer_owns_topology_status_rendering():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    timer = cs[cs.index("private void StartTopologyCompletionTimer()"):cs.index("private void RunPitchMeasure()", cs.index("private void StartTopologyCompletionTimer()"))]
    assert "string result = _addin.CompletePendingTopology();" in timer
    assert "_status.Text = result;" in timer


def test_editor_v324_external_helper_owns_glue_truth():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    helper = (root / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    plan = cs[cs.index("private void StartExternalExpectedGlueRestore"):cs.index("private int ParseTopologyHelperRepairCount")]
    assert "TryGetGlueTarget(" not in plan
    assert "Dictionary<string, GlueEdgeInfo> unique" in plan
    assert 'lines.Add(String.Format(' in plan
    assert "private static bool IsGlueCorrect(dynamic page, Edge edge)" in helper
    assert ".FormulaU" in helper
    assert "FormulaReferencesTarget" in helper
    assert "if (!IsGlueCorrect(page, edge))" in helper
    assert "GlueAndVerify(page, edge);" in helper
    assert '"PASS\\t" +' in helper
    assert "repaired.ToString" in helper
    assert "verified.ToString" in helper
    assert 'ApiVersion() { return "0.3.64"; }' in cs



def test_editor_v356_keeps_replacement_on_explicit_legacy_path_until_master_transaction_migration():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private string FinalizePendingTopologyOperation")]
    legacy = complete[complete.index("// Legacy async-scope path"):]
    assert "if (replacement != null)" in legacy
    assert "replacement.ExpectedGlue.Count" in legacy
    assert "VerifyGlue(" not in legacy
    assert "legacy async UndoScope" in legacy

def test_editor_v325_helper_rejects_half_glue_by_formula_pair():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    assert "private static bool FormulaReferencesTarget(" in helper
    assert 'string xName = edge.Endpoint == "begin" ? "BeginX" : "EndX";' in helper
    assert 'string yName = edge.Endpoint == "begin" ? "BeginY" : "EndY";' in helper
    assert 'FormulaReferencesTarget(xFormula, target, edge.Row, "X")' in helper
    assert 'FormulaReferencesTarget(yFormula, target, edge.Row, "Y")' in helper
    assert "half-Glue state" in helper
    assert "External GlueTo formula verification failed" in helper


def test_editor_v325_external_helper_does_not_depend_on_connects_for_immediate_verification():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    verifier = helper[helper.index("private static bool IsGlueCorrect"):helper.index("private static void GlueAndVerify")]
    assert "source.Connects" not in verifier
    assert ".FormulaU" in verifier


def test_editor_v326_helper_has_bounded_stability_window():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    assert "using System.Threading;" in helper
    assert "const int requiredCleanRounds = 8;" in helper
    assert "const int maxRounds = 20;" in helper
    assert "const int pollMilliseconds = 250;" in helper
    assert "if (repairedThisRound == 0 && geometryRepairedThisRound == 0)" in helper
    assert "cleanRounds++" in helper
    assert "cleanRounds = 0" in helper
    assert "Thread.Sleep(pollMilliseconds);" in helper
    assert "External topology did not stabilize" in helper
    assert "rounds.ToString" in helper
    assert "cleanRounds.ToString" in helper


def test_editor_v326_replacement_does_not_touch_visio_after_helper_pass():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private void StartExternalTopologyRestore")]
    branch_start = complete.index("if (replacement != null)")
    branch_end = complete.index("else\n                {", branch_start)
    branch = complete[branch_start:branch_end]
    for forbidden in ("ResolveLivePage(", "Shapes.ItemFromID", "GetMm(", "GetCellIdentity(", "DiscoverCell(", "SelectIds("):
        assert forbidden not in branch
    assert "verifiedGlue = replacement.ExpectedGlue.Count;" in branch
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v327_defaults_to_drop_rewire_on_modern_visio():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private bool SupportsNativeReplaceShape")]
    assert "bool useNativeReplaceShape = false;" in replace
    assert "if (useNativeReplaceShape && SupportsNativeReplaceShape())" in replace
    assert 'backend = "drop/rewire compatibility";' in replace
    assert "if (!useNativeReplaceShape)" in replace
    assert "target.Delete();" in replace
    assert "delayed dependency rewrite" in replace
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v328_bind_identity_no_longer_mutates_electrical_shapes():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    bind = cs[cs.index("internal string BindCellIdentity()"):cs.index("internal string CaptureReplacementSample()")]
    assert "SetCellIdentity(page.Shapes.ItemFromID(id), cellId)" in bind
    assert "CaptureInternalGlue" not in bind
    assert "BuildReplacementExpectedGlue" not in bind
    assert "ScheduleStableTopologyCompletion" not in bind
    setter = cs[cs.index("private void SetCellIdentity(dynamic shape, string cellId)"):cs.index("internal sealed class EditorForm")]
    assert "page.PageSheet" in setter
    assert "pageSheet.AddNamedRow" in setter
    assert "shape.AddNamedRow" not in setter

def test_editor_v328_stable_scheduler_is_reserved_for_topology_mutations():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue")]
    bind = cs[cs.index("internal string BindCellIdentity()"):cs.index("internal string CaptureReplacementSample()")]
    assert "ScheduleStableTopologyCompletion(page, pending, scope)" in replace
    assert "ScheduleStableTopologyCompletion" not in bind

def test_editor_v329_preserves_one_dimensional_endpoint_geometry():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    replace = cs[cs.index("internal string ReplaceEquipmentFromSample()"):cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue")]
    assert 'HasEndpoint(target, "begin")' in replace
    assert 'HasEndpoint(target, "end")' in replace
    assert 'oldBeginX = GetMm(target, "BeginX")' in replace
    assert 'oldBeginY = GetMm(target, "BeginY")' in replace
    assert 'oldEndX = GetMm(target, "EndX")' in replace
    assert 'oldEndY = GetMm(target, "EndY")' in replace
    assert 'SetMm(replacement, "BeginX", oldBeginX)' in replace
    assert 'SetMm(replacement, "BeginY", oldBeginY)' in replace
    assert 'SetMm(replacement, "EndX", oldEndX)' in replace
    assert 'SetMm(replacement, "EndY", oldEndY)' in replace
    assert "engineering length оборудования" in replace
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v330_cell_identity_is_pagesheet_backed():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    get_start = cs.index("private string GetCellIdentity(dynamic shape)")
    set_start = cs.index("private void SetCellIdentity(dynamic shape, string cellId)")
    block = cs[get_start:set_start]
    setter = cs[set_start:cs.index("internal sealed class EditorForm", set_start)]
    assert "shape.ContainingPage" in block
    assert "page.PageSheet" in block
    assert "CellIdentityPageCellName" in block
    assert "User.EnergoLogicCellId" in block  # legacy read fallback only
    assert "shape.ContainingPage" in setter
    assert "page.PageSheet" in setter
    assert "pageSheet.AddNamedRow" in setter
    assert 'shape.AddNamedRow' not in setter
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v330_bind_identity_does_not_schedule_topology_repair():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string BindCellIdentity()")
    end = cs.index("internal string CaptureReplacementSample()", start)
    block = cs[start:end]
    assert "SetCellIdentity(page.Shapes.ItemFromID(id), cellId)" in block
    assert "ScheduleStableTopologyCompletion" not in block
    assert "CaptureInternalGlue" not in block
    assert "BuildReplacementExpectedGlue" not in block


def test_editor_v330_pagesheet_string_escaping_is_valid_csharp():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert '.Replace("\\\"\\\"", "\\\"")' in cs
    assert 'FormulaU = "\\\"" + (cellId ?? "").Replace("\\\"", "\\\"\\\"") + "\\\"";' in cs


def test_editor_current_build_has_unique_com_class_guid():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert '[Guid("8B7F2A13-1F51-47F4-9D1A-A7E0F364C001")]' in cs
    assert 'ProgId("EnergoLogic.VisioEditorAddinV364")' in cs
    assert 'clsid = "{8B7F2A13-1F51-47F4-9D1A-A7E0F364C001}"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs

def test_editor_v332_glues_replacement_bus_anchor_in_process():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string ReplaceEquipmentFromSample()")
    end = cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue", start)
    block = cs[start:end]
    anchor = block.index("if (targetWasAnchor)")
    glue = block.index("GlueEndpoint(", anchor)
    delete = block.index("target.Delete()", anchor)
    assert anchor < glue < delete
    assert "page.Shapes.ItemFromID(cell.BusTerminalId)" in block[anchor:delete]
    assert "VerifyGlue(" in block[anchor:delete]
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v332_has_unique_com_class_guid():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert '[Guid("8B7F2A13-1F51-47F4-9D1A-A7E0F364C001")]' in cs
    assert 'ProgId("EnergoLogic.VisioEditorAddinV364")' in cs
    assert 'clsid = "{8B7F2A13-1F51-47F4-9D1A-A7E0F364C001}"' in ext


def test_editor_insert_equipment_api_is_exposed_in_ui_and_managed_bridge():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiInsertEquipmentIntoConnectionFromSample();" in cs
    assert "public string ApiInsertEquipmentIntoConnectionFromSample()" in cs
    assert "internal string InsertEquipmentIntoConnectionFromSample()" in cs
    assert '"insert_equipment_into_connection_from_sample": "ApiInsertEquipmentIntoConnectionFromSample"' in ext
    assert 'ButtonWide("Вставить образец в связь"' in cs
    assert "RunInsertEquipment()" in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs

def test_editor_v334_splits_connection_around_natural_length_equipment():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string InsertEquipmentIntoConnectionFromSample()")
    end = cs.index("private List<GlueEdgeInfo> BuildReplacementExpectedGlue", start)
    block = cs[start:end]
    assert "_replacementInsertSourceEndpoint" in block
    assert "_replacementInsertReceiveRow" in block
    assert "nativeLength + 2.0 * minLeadMm > connectionLength" in block
    assert 'SetMm(inserted, "BeginX", insertBeginX)' in block
    assert 'SetMm(inserted, "EndY", insertEndY)' in block
    assert 'DetachEndpoint(connection, "begin")' in block
    assert 'DetachEndpoint(connection, "end")' in block
    assert "connection.Delete()" not in block
    assert block.count("GlueEndpoint(") >= 6
    assert 'connection,\n                        "begin"' in block
    assert 'connection,\n                        "end"' in block
    assert "ExpectedMemberCount = cell.MemberIds.Count + 1" in block
    assert "FindConnectionPointRowAtEndpoint" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v334_capture_sample_builds_vtd_insert_port_profile():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string CaptureReplacementSample()")
    end = cs.index("internal string ReplaceEquipmentFromSample()", start)
    block = cs[start:end]
    assert 'TryGetGlueTarget(shape, "begin")' in block
    assert 'TryGetGlueTarget(shape, "end")' in block
    assert "(begin == null) != (end == null)" in block
    assert "FindConnectionPointRowAtEndpoint" in block
    assert "Профиль вставки" in block


def test_editor_v335_bus_editing_uses_native_vtd_shape_data():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "internal string ExtendBusRight()" in cs
    assert "internal string TrimBusRight()" in cs
    assert 'CellExists(selected, "Prop.tp")' in cs
    assert 'CellExists(selected, "Prop.rt")' in cs
    assert '"INDEX(" + (count - 1).ToString' in cs
    assert "GetBusTerminalBySlot(page, busId, current + 1)" in cs
    assert "EnsureTerminalFree(page, lastTerminalId" in cs
    assert '"extend_bus_right": "ApiExtendBusRight"' in ext
    assert '"trim_bus_right": "ApiTrimBusRight"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v335_dynamic_bus_slots_use_vtd_user_nt_ut():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private int GetSlot(dynamic terminal)")
    end = cs.index("private void EnsureTerminalFree", start)
    block = cs[start:end]
    assert 'CellExists(terminal, "User.nt")' in block
    assert 'CellExists(terminal, "User.ut")' in block
    assert "if (!hidden)" in block
    assert "return nt + 1" in block


def test_editor_v335_reconnect_and_visual_diagnostics_are_fail_closed():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "internal string ReconnectEndpoint(string endpoint)" in cs
    reconnect = cs[cs.index("internal string ReconnectEndpoint"):cs.index("internal string VisualDiagnostics")]
    assert "distance <= 1.0" in reconnect
    assert "Переподключение неоднозначно" in reconnect
    assert "GlueEndpointWithRetry" in reconnect
    assert "VerifyGlue" in reconnect
    visual = cs[cs.index("internal string VisualDiagnostics"):cs.index("private dynamic ResolveSelectedBus")]
    assert "problemIds" in visual
    assert "SelectIds(page, problemIds" in visual
    assert "Prop.tp" in visual and "Prop.rt" in visual
    assert '"visual_diagnostics": "ApiVisualDiagnostics"' in ext
    assert '"reconnect_begin": "ApiReconnectBegin"' in ext
    assert '"reconnect_end": "ApiReconnectEnd"' in ext


def test_editor_v335_diagnostic_strings_are_csharp_escaped():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert 'SafeText(bus).Replace("\\r", " ").Replace("\\n", " ").Trim()' in cs
    assert 'result += "\\r\\nСтруктура: "' in cs
    assert '". Проблемные элементы верхнего уровня выделены.\\r\\n" +' in cs
    assert 'String.Join("\\r\\n", messages.Take(12).ToArray())' in cs


def test_editor_v336_normalizes_incoming_child_glue_to_top_level_endpoint():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private HashSet<string> BuildConnectedEndpointIndex(dynamic page)")
    end = cs.index("private List<ConnectionPointInfo> GetAllConnectionPoints", start)
    block = cs[start:end]
    assert "Dictionary<int, int> childParent = BuildChildParentMap(page);" in block
    assert "endpointOwnerId = ownerId" in block
    assert "dynamic endpointOwner = page.Shapes.ItemFromID(endpointOwnerId)" in block
    assert "connected.Add(EndpointKey(endpointOwnerId, targetEndpoint))" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v336_repair_and_diagnostics_ignore_own_group_children():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    repair = cs[cs.index("internal string RepairGlue"):cs.index("internal string Doctor")]
    doctor = cs[cs.index("internal string Doctor"):cs.index("internal string BusDiagnostics")]
    visual = cs[cs.index("internal string VisualDiagnostics"):cs.index("private dynamic ResolveSelectedBus")]
    reconnect = cs[cs.index("internal string ReconnectEndpoint"):cs.index("internal string VisualDiagnostics")]
    assert "repairChildParent" in repair and "pointOwner == ids[0]" in repair
    assert "doctorChildParent" in doctor and "owner == id" in doctor
    assert "visualChildParent" in visual and "owner == id" in visual
    assert "owner == sourceId" in reconnect


def test_editor_v337_resolves_both_vtd_connection_row_name_forms():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private bool TryGetConnectionPointPageCoordinates")
    end = cs.index("private List<ConnectionPointInfo> GetAllConnectionPoints", start)
    block = cs[start:end]
    assert '"Connections.X" + rowText' in block
    assert '"Connections." + rowText + ".X"' in block
    assert "shape.XYToPage(localX, localY, out pageX, out pageY)" in block
    index = cs[cs.index("private HashSet<string> BuildConnectedEndpointIndex"):start]
    assert "TryGetConnectionPointPageCoordinates" in index
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v337_connection_point_scan_deduplicates_aliases():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private List<ConnectionPointInfo> GetAllConnectionPoints")
    end = cs.index("private double GetMm", start)
    block = cs[start:end]
    assert "HashSet<string> physical" in block
    assert "TryGetConnectionPointPageCoordinates(shape, row" in block
    assert "if (!physical.Add(key)) continue;" in block


def test_editor_v338_exposes_native_ribbon_and_context_menu():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "IRibbonExtensibility" in cs
    assert "public string GetCustomUI(string RibbonID)" in cs
    assert 'id=""tabEnergoLogic"" label=""EnergoLogic"" keytip=""EL""' in cs
    assert "public void OnRibbonLoad(IRibbonUI ribbonUI)" in cs
    assert "OnRibbonDuplicateRight" in cs
    assert "OnRibbonReconnectEnd" in cs
    assert "OnRibbonPitch40" in cs
    assert "InstallContextMenu()" in cs
    assert "msoBarTypePopup" in cs
    assert 'root.Tag = "EnergoLogic.Context.Root"' in cs
    assert "root.CommandBar" in cs
    assert "ApiUiStatus()" in cs
    assert '"ui_status": "ApiUiStatus"' in ext
    assert 'native RibbonX + drawing context menu + modeless WinForms parameter panel' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v338_ribbon_commands_use_shared_async_aware_command_runner():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void PublishUserCommand(Func<string> action)" in cs
    assert "form.AcceptExternalResult(result)" in cs
    assert "internal void AcceptExternalResult(string result)" in cs
    assert 'result.StartsWith("⏳", StringComparison.Ordinal)' in cs
    assert "StartTopologyCompletionTimer();" in cs


def test_editor_v338_connection_point_enumeration_uses_real_section_row_count():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private int GetConnectionPointRowCount(dynamic shape)" in cs
    assert "const short visSectionConnectionPts = 7;" in cs
    assert "shape.RowCount(visSectionConnectionPts)" in cs
    assert "row <= 32" not in cs


def test_editor_v338_does_not_force_parameter_panel_on_connection():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    block = cs[cs.index("public void OnConnection"):cs.index("public void OnDisconnection")]
    assert "ShowPanel();" not in block
    assert "InstallContextMenu();" in block
    assert "_bar.Visible = false;" in cs


def test_editor_v339_installs_submenu_into_existing_visio_drawing_popups():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private void InstallContextMenu()")
    end = cs.index("internal string UiStatus()", start)
    block = cs[start:end]
    assert "bars.Add(" not in block
    assert "msoBarTypePopup" in block
    assert 'String.Equals(context, "9"' in block
    assert 'String.Equals(context, "75"' in block
    assert "host.Controls.Add(" in block
    assert "msoControlPopup" in block
    assert 'root.Tag = "EnergoLogic.Context.Root"' in block
    assert "root.CommandBar" in block
    assert "RemoveExistingEnergoLogicContextRoot(host)" in block
    assert "_contextRoots.Add(root)" in block
    assert "_contextHostNames.Add(hostName)" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v339_disconnect_deletes_only_energologic_context_roots():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    block = cs[cs.index("public void OnDisconnection"):cs.index("public void OnAddInsUpdate")]
    assert "foreach (CommandBarPopup root in _contextRoots)" in block
    assert "_contextRoots.Clear()" in block
    assert "_contextHostNames.Clear()" in block
    assert "_contextBar" not in block


def test_editor_v340_context_submenu_uses_static_commandbar_type():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "CommandBar menu = root.CommandBar;" in cs
    assert "private CommandBarButton AddContextButton(\n            CommandBar menu," in cs
    assert "dynamic menu = root.CommandBar" not in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v341_uses_live_qualified_visio_popup_context_ids():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private void InstallContextMenu()")
    end = cs.index("private void RemoveExistingEnergoLogicContextRoot", start)
    block = cs[start:end]
    assert 'String.Equals(context, "9"' in block
    assert 'String.Equals(context, "75"' in block
    assert 'String.Equals(context, "2"' not in block
    assert "Drawing Object Selected" in block
    assert "Drawing Page Selected" in block
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v345_restores_live_proven_diagnostic_connectivity_algorithm():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private HashSet<string> BuildConnectedEndpointIndex(dynamic page)")
    end = cs.index("private int GetConnectionPointRowCount", start)
    block = cs[start:end]
    assert "Dictionary<int, int> childParent = BuildChildParentMap(page);" in block
    assert 'foreach (string sourceEndpoint in new[] { "begin", "end" })' in block
    assert "glue = TryGetGlueTarget(source, sourceEndpoint)" in block
    assert "connected.Add(EndpointKey(sourceId, sourceEndpoint))" in block
    assert "TryGetConnectionPointPageCoordinates(" in block
    assert "connected.Add(EndpointKey(endpointOwnerId, targetEndpoint))" in block
    assert "inspect(source.Shapes.Item(child))" in block
    visual = cs[cs.index("internal string VisualDiagnostics()"):cs.index("private dynamic ResolveSelectedBus")]
    assert "BuildConnectedEndpointIndex(page)" in visual
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v345_keeps_ribbon_and_qualified_context_menu():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "IRibbonExtensibility" in cs
    assert 'id=""tabEnergoLogic"" label=""EnergoLogic"" keytip=""EL""' in cs
    assert 'String.Equals(context, "9"' in cs
    assert 'String.Equals(context, "75"' in cs
    assert "_bar.Visible = false;" in cs


def test_editor_v346_ribbon_is_russian_and_uses_builtin_office_icons():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("public string GetCustomUI(string RibbonID)")
    end = cs.index("public void OnRibbonLoad", start)
    ribbon = cs[start:end]
    assert 'label=""Восстановить соединение""' in ribbon
    assert 'label=""Переподключить начало""' in ribbon
    assert 'label=""Переподключить конец""' in ribbon
    assert 'label=""Проверка связей""' in ribbon
    assert 'label=""Repair Glue""' not in ribbon
    assert 'label=""Reconnect Begin""' not in ribbon
    assert 'label=""Reconnect End""' not in ribbon
    assert 'label=""Scheme Doctor""' not in ribbon
    assert ribbon.count('imageMso=""') >= 20
    assert 'imageMso=""Copy""' in ribbon
    assert 'imageMso=""Paste""' in ribbon
    assert 'imageMso=""RefreshAll""' in ribbon
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v346_context_and_panel_have_no_english_command_labels():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert '"Переподключить начало"' in cs
    assert '"Переподключить конец"' in cs
    assert '"Восстановить соединение…"' in cs
    assert 'ButtonWide("Переподключить начало"' in cs
    assert 'ButtonWide("Переподключить конец"' in cs
    assert 'ButtonWide("Восстановить соединение…"' in cs
    assert 'ButtonWide("Найти потерянное соединение"' in cs


def test_editor_v346_installer_discovers_and_removes_all_legacy_editor_addins():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'current_progid = "EnergoLogic.VisioEditorAddinV364"' in ext
    assert 'editor_progid_prefix = "EnergoLogic.VisioEditorAddinV"' in ext
    assert 'candidate.startswith(editor_progid_prefix)' in ext
    assert 'legacy_progids.add(candidate)' in ext
    assert 'r"Software\\Classes"' in ext
    assert 'legacy_item.Connect = False' in ext
    assert 'workspace.glob("energologic_visio_editor_addin_v*")' in ext
    assert '"removed_build_dirs": removed_build_dirs' in ext
    assert '"editor_addins_after": editor_addins_after' in ext
    assert '"single_editor_addin": (' in ext
    assert '"migration": "all legacy editor registrations -> v3.64"' in ext


def test_editor_v346_uninstall_removes_all_energologic_editor_versions():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    start = ext.index("def uninstall_energologic_editor_ui()")
    block = ext[start:]
    assert 'prefix = "EnergoLogic.VisioEditorAddinV"' in block
    assert "discovered.add(candidate)" in block
    assert '"removed_progids": removed' in block


def test_editor_v347_ribbon_has_context_help_for_every_control():
    from pathlib import Path
    import re
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("public string GetCustomUI(string RibbonID)")
    end = cs.index("public void OnRibbonLoad", start)
    ribbon = cs[start:end]
    controls = re.findall(r"<(?:button|menu)\b[^>]+>", ribbon)
    assert len(controls) >= 30
    missing = [
        control
        for control in controls
        if 'screentip=""' not in control or 'supertip=""' not in control
    ]
    assert missing == []
    assert 'label=""Справка""' in ribbon
    assert 'onAction=""OnRibbonHelp""' in ribbon


def test_editor_v347_diagnostics_show_explicit_result_dialogs():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void PublishDiagnosticCommand(string title, Func<string> action)" in cs
    assert "MessageBox.Show(" in cs
    assert 'OnRibbonDoctor(IRibbonControl control) { PublishDiagnosticCommand("проверка связей"' in cs
    assert 'OnRibbonBusDiagnostics(IRibbonControl control) { PublishDiagnosticCommand("диагностика шины"' in cs
    assert 'OnRibbonVisualDiagnostics(IRibbonControl control) { PublishDiagnosticCommand("визуальная диагностика"' in cs


def test_editor_v347_has_full_help_and_transient_feedback():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "internal sealed class StatusToastForm : Form" in cs
    assert "internal sealed class HelpForm : Form" in cs
    assert "private string BuildHelpText()" in cs
    assert "ENERGOLOGIC — СПРАВКА ПО КОМАНДАМ" in cs
    assert "ОБОЗНАЧЕНИЯ РЕЗУЛЬТАТА" in cs
    assert "ShowTransientStatus(result)" in cs
    assert "_addin.NotifyAsyncResult(result);" in cs


def test_editor_v347_exposes_interactive_base_point_copy_move():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiStartBaseCopyInteractive();" in cs
    assert "string ApiStartBaseMoveInteractive();" in cs
    assert "internal string StartInteractiveBasePoint(bool copy)" in cs
    assert "eventList.AddAdvise(" in cs
    assert "(short)709" in cs
    assert "public object VisEventProc(" in cs
    assert "mouse.x" in cs and "mouse.y" in cs
    assert "* 25.4" in cs
    assert "button == 2" in cs
    assert "BasePointTransform(" in cs
    assert 'label=""Копировать с базовой точкой""' in cs
    assert 'label=""Переместить по базовой точке""' in cs
    assert '"start_base_copy_interactive": "ApiStartBaseCopyInteractive"' in ext
    assert '"interaction_status": "ApiInteractionStatus"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v347_help_documents_every_ribbon_group():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private string BuildHelpText()")
    end = cs.index("private void InstallContextMenu()", start)
    help_block = cs[start:end]
    for heading in (
        "ЯЧЕЙКА",
        "ОБОРУДОВАНИЕ",
        "БАЗОВАЯ ТОЧКА",
        "СОЕДИНЕНИЯ И ШИНА",
        "ГЕОМЕТРИЯ",
        "ПРОВЕРКА",
        "ТОЧНЫЕ ПАРАМЕТРЫ",
    ):
        assert heading in help_block


def test_editor_v348_context_menu_is_split_by_object_vs_page():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("private void InstallContextMenu()")
    end = cs.index("private void RemoveExistingEnergoLogicContextRoot", start)
    block = cs[start:end]
    assert 'String.Equals(context, "9"' in block
    assert 'String.Equals(context, "75"' in block
    assert '"Копировать с базовой точкой"' in block
    assert '"Переместить по базовой точке"' in block
    assert '"Вставить по базовой точке"' in block
    object_start = block.index('String.Equals(context, "9"')
    page_start = block.index('else if (String.Equals(', object_start)
    object_branch = block[object_start:page_start]
    page_branch = block[page_start:]
    assert '"ReconnectBegin"' in object_branch
    assert '"BusDiagnostics"' in object_branch
    assert '"BasePaste"' not in object_branch
    assert '"BasePaste"' in page_branch
    assert '"Doctor"' in page_branch
    assert '"Panel"' in page_branch


def test_editor_v348_has_reusable_base_point_clipboard():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private bool _baseClipboardReady = false;" in cs
    assert "internal string StartBaseCopyCapture()" in cs
    assert "internal string StartBasePasteInteractive()" in cs
    assert "internal string BaseClipboardStatus()" in cs
    assert "internal string ClearBaseClipboard(bool report)" in cs
    assert '_interactiveBaseMode = "capture_copy_base"' in cs
    assert '_interactiveBaseMode = "paste_target"' in cs
    assert "_baseClipboardReady = true;" in cs
    assert "ValidateBaseClipboardShapes(page)" in cs
    assert "Буфер сохранён — можно вставить ещё одну копию." in cs
    assert "UpdateContextPasteButtons();" in cs
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v348_ribbon_exposes_split_copy_and_paste_base_point_commands():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("public string GetCustomUI(string RibbonID)")
    end = cs.index("public void OnRibbonLoad", start)
    ribbon = cs[start:end]
    assert 'label=""Копировать с базовой точкой""' in ribbon
    assert 'onAction=""OnRibbonBaseCopyCapture""' in ribbon
    assert 'label=""Вставить по базовой точке""' in ribbon
    assert 'onAction=""OnRibbonBasePaste""' in ribbon
    assert "Буфер можно вставлять многократно" in ribbon
    assert "Буфер остаётся доступным для следующих вставок" in ribbon


def test_editor_v348_managed_api_exposes_base_clipboard_actions():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert '"start_base_copy_capture": "ApiStartBaseCopyCapture"' in ext
    assert '"start_base_paste_interactive": "ApiStartBasePasteInteractive"' in ext
    assert '"clear_base_clipboard": "ApiClearBaseClipboard"' in ext
    assert '"base_clipboard_status": "ApiBaseClipboardStatus"' in ext
    assert "string ApiStartBaseCopyCapture();" in cs
    assert "string ApiStartBasePasteInteractive();" in cs


def test_editor_v349_selected_copy_is_not_cell_copy():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiDuplicateSelectedLeft();" in cs
    assert "string ApiDuplicateSelectedRight();" in cs
    assert "string ApiDuplicateSelected();" in cs
    assert "internal string DuplicateSelectedByPitch(int direction)" in cs
    assert "internal string DuplicateSelectedNative()" in cs
    assert "private string DuplicateSelectedCore(" in cs
    assert "DetachExternalGlueFromSelection(page, newIds)" in cs
    assert "ClearCellIdentity(shape);" in cs
    assert '"Копировать выбранное ←"' in cs
    assert '"Копировать выбранное →"' in cs
    assert '"Дублировать выбранное"' in cs
    assert '"duplicate_selected_left": "ApiDuplicateSelectedLeft"' in ext
    assert 'ApiVersion() { return "0.3.64"; }' in cs


def test_editor_v349_generic_copy_allows_source_external_glue_but_drops_it_on_copy():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string BasePointTransform")
    end = cs.index("internal string Coordinates()", start)
    block = cs[start:end]
    assert "if (!copy) EnsureNoExternalGlue(page, ids);" in block
    assert "CountExternalGlue(page, ids)" in block
    assert "DetachExternalGlueFromSelection(page, newIds)" in block
    assert "Внешние связи исходника не перенесены" in block


def test_editor_v349_adds_safe_small_geometry_utilities():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "internal string DistributeSelection(string axis)" in cs
    assert "internal string MeasureSelectionDistance()" in cs
    assert "internal string SnapSelectionToGrid(double gridMm)" in cs
    assert 'label=""Распределить X""' in cs
    assert 'label=""Распределить Y""' in cs
    assert 'label=""Расстояние""' in cs
    assert 'label=""На сетку 5 мм""' in cs
    assert 'label=""Сдвиг 1 мм ←""' in cs
    assert 'label=""Сдвиг 1 мм →""' in cs


def test_editor_v349_align_xy_remains_topology_guarded():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string Align(string axis)")
    end = cs.index("internal string DistributeSelection", start)
    block = cs[start:end]
    assert "EnsureNoExternalGlue(page, ids);" in block
    assert "RestoreInternalGlue(page, internalGlue);" in block
    assert "VerifyInternalGlue(page, internalGlue);" in block


def test_editor_v349_exact_offset_remains_external_glue_guarded():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    start = cs.index("internal string ExactOffset")
    end = cs.index("internal string StartBaseCopyCapture", start)
    block = cs[start:end]
    assert "EnsureNoExternalGlue(page, ids);" in block
    assert "if (!copy)" not in block
    assert "sourceExternalGlue" not in block


def test_editor_v349_compiles_identity_clear_and_distribution_without_dynamic_linq():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert 'shape.CellsU("User.EnergoLogicCellId").FormulaU = "\\"\\"";' in cs
    start = cs.index("internal string DistributeSelection(string axis)")
    end = cs.index("internal string MeasureSelectionDistance()", start)
    block = cs[start:end]
    assert "List<Tuple<int, double>> ordered = new List<Tuple<int, double>>();" in block
    assert "double coordinate = GetMm(" in block
    assert "ordered.Add(Tuple.Create(id, coordinate));" in block
    assert ".Select(id => Tuple.Create(" not in block


def test_managed_extension_builds_offline_portable_kit():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'def build_energologic_portable_kit(' in ext
    assert 'EnergoLogic-Visio-Editor-Kit-' in ext
    assert 'EnergoLogicVisioEditorAddin.cs' in ext
    assert 'EnergoLogicTopologyRestoreHelper.cs' in ext
    assert '"MANIFEST.json"' in ext
    assert '"zip_sha256"' in ext
    assert '"third_party_vtd_included": False' in ext
    assert '"\\\\programdata\\\\" in source_lower' in ext
    assert '"\\\\vtd\\\\" in source_lower' in ext
    assert '"Мои фигуры"' in ext
    assert '"ГОСТ"' in ext


def test_portable_kit_installer_is_offline_per_user_and_manifest_verified():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    kit = root / "managed" / "visio" / "portable_kit"
    install = (kit / "Install-EnergoLogic.ps1").read_text()
    start = (kit / "Start-EnergoLogic-Visio.ps1").read_text()
    readme = (kit / "README-RU.txt").read_text()
    collect = (kit / "Collect-Stencils.ps1").read_text()
    assert 'MANIFEST.json' in install
    assert 'Get-FileHash' in install
    assert 'RegistryHive]::CurrentUser' in install
    assert 'LOCALAPPDATA' in install
    assert 'LoadBehavior' in install and ' 0' in install
    assert 'COMAddIns.Item($ProgId)' in start
    assert 'Documents.OpenEx($file.FullName, 6)' in start
    assert 'ChatGPT, MCP, Python, Visual Studio и Интернет не нужны' in readme
    assert 'ProgramData' in readme and 'НЕ копируются' in readme
    assert 'Join-Path $documents "Мои фигуры"' in collect
    assert 'Join-Path $myShapes "ГОСТ"' in collect
    assert 'ProgramData' in collect and 'VTD' in collect



def test_portable_builder_uses_only_top_level_personal_stencils():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    start = ext.index("def build_energologic_portable_kit(")
    end = ext.index("@mcp.tool()", start + 20)
    block = ext[start:end]
    assert "stencil_root.iterdir()" in block
    assert 'stencil_root.rglob("*")' not in block
    assert '"powershell.exe"' in block
    assert '"-CompileOnly"' in block
    assert '"portable_compile_validation": "PASS"' in block


def test_portable_kit_has_no_openai_or_user_specific_runtime_paths():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    kit = root / "managed" / "visio" / "portable_kit"
    combined = "\n".join(
        f.read_text()
        for f in kit.iterdir()
        if f.is_file() and f.suffix.lower() in {".ps1", ".cmd", ".txt"}
    )
    assert "OpenAI\\VisioMCP" not in combined
    assert "C:\\Users\\Gennadiy" not in combined
    assert "OneDrive\\Documents\\Мои фигуры" not in combined


def test_portable_powershell_scripts_have_utf8_bom():
    from pathlib import Path
    kit = Path(__file__).resolve().parents[2] / "managed" / "visio" / "portable_kit"
    scripts = list(kit.glob("*.ps1"))
    assert scripts
    for script in scripts:
        assert script.read_bytes().startswith(b"\xef\xbb\xbf"), script.name


def test_editor_v356_distribute_pitch_delegates_entire_mutation_to_helper_owned_scope():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    distribute = cs[cs.index("internal string DistributePitch(double pitch)"):cs.index("internal string RepairGlue", cs.index("internal string DistributePitch(double pitch)"))]
    assert "ScheduleTopologyCompletion(" in distribute
    assert '"EnergoLogic: Распределить ячейки"' in distribute
    assert "BeginUserUndoScope(" not in distribute
    assert "DetachEndpoint(" not in distribute
    assert "Selection.Move(" not in distribute
    assert "scopeTransferred" not in distribute

def test_editor_v356_finalizes_helper_owned_transaction_without_cross_owner_scope_close():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    finalizer = cs[cs.index("private string FinalizePendingTopologyOperation"):cs.index("private void AbortPendingTopologyOperation")]
    assert "bool helperOwnsUndoScope" in finalizer
    assert "if (!helperOwnsUndoScope)" in finalizer
    assert "App.EndUndoScope(scopeId, success)" in finalizer
    assert 'finalState = "success"' in finalizer
    assert 'finalState = "failed_rolled_back"' in finalizer
    assert 'finalState = "failed_needs_attention"' in finalizer
    assert "rollbackConfirmed" in finalizer
    assert "_pendingHelperOwnsUndoScope = false" in finalizer

def test_editor_v351_disconnect_aborts_pending_topology_scope_fail_closed():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    disconnect = cs[
        cs.index("public void OnDisconnection"):
        cs.index("public void OnAddInsUpdate")
    ]
    assert "AbortPendingTopologyOperation()" in disconnect

    abort = cs[
        cs.index("private void AbortPendingTopologyOperation"):
        cs.index("private void StartExternalTopologyRestore")
    ]
    assert "_pendingUndoScopeId = 0" in abort
    assert "_pendingTopologyHelperProcess.Kill()" in abort
    assert "App.EndUndoScope(scopeId, false)" in abort


def test_editor_v351_installer_reports_only_connected_current_addin_as_single():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'current_progid = "EnergoLogic.VisioEditorAddinV364"' in ext
    assert 'len([item for item in editor_addins_after if item["connected"]]) == 1' in ext
    assert 'item["progid"] == progid and item["connected"]' in ext
    assert '"migration": "all legacy editor registrations -> v3.64"' in ext


def test_editor_v351_blocks_new_energologic_transactions_while_async_scope_is_pending():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    gate = cs[
        cs.index("private int BeginUserUndoScope"):
        cs.index("private void InstallToggleButton")
    ]
    assert "lock (_asyncSync)" in gate
    assert "if (_asyncPending)" in gate
    assert "Предыдущая составная операция EnergoLogic ещё завершается" in gate
    assert "App.BeginUndoScope(name)" in gate
    assert cs.count("BeginUndoScope(") == 1
    assert cs.count("BeginUserUndoScope(") >= 15  # Move/Distribute use helper-owned scopes


def test_editor_v351_generic_panel_run_starts_async_topology_timer_for_pending_results():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    run = cs[cs.index("private void Run(Func<string> action)"):cs.index("private void RunBindCellIdentity") ]
    assert "string result = action();" in run
    assert "AcceptExternalResult(result);" in run
    assert "_status.Text = action();" not in run
    accept = cs[cs.index("internal void AcceptExternalResult"):cs.index("private void Run(Func<string> action)")]
    assert 'result.StartsWith("⏳", StringComparison.Ordinal)' in accept
    assert "StartTopologyCompletionTimer();" in accept








def test_editor_v356_helper_transaction_result_is_fail_closed_and_rollback_aware():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    helper = (root / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    complete = cs[cs.index("internal string CompletePendingTopology()"):cs.index("private string FinalizePendingTopologyOperation")]
    assert 'ERROR_ROLLED_BACK' in complete and 'rollbackConfirmed' in complete
    assert "rollbackConfirmed" in complete
    assert 'helperResult.StartsWith("PASS"' in complete
    assert '"failed_needs_attention"' in cs
    assert '"ERROR_ROLLED_BACK\\t"' in helper
    assert "transactionApp.EndUndoScope(transactionScope, false)" in helper


def test_editor_v356_helper_move_transaction_verifies_every_member_delta_and_expected_glue():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    helper = (root / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    apply = helper[helper.index("private static void ApplyMoveStep"):helper.index("[STAThread]")]
    assert "Dictionary<int, double[]> before" in apply
    assert "actualDx" in apply and "actualDy" in apply
    assert "Move verification failed for shape" in apply
    assert "DetachEndpoint(anchor, step.Endpoint)" in apply
    assert "preparedSelection.Move(step.DxMm, step.DyMm, \"mm\")" in apply
    assert "SelectIds(app, page, step.MemberIds)" not in apply
    assert "app.ActiveWindow.Selection.Move" not in apply
    assert "preparedSelection.Move(step.DxMm, step.DyMm, \"mm\")" in apply
    assert "GlueAndVerify(page, edge)" in helper
    assert "requiredCleanRounds = 8" in helper


def test_topology_helper_v357_stabilizes_after_final_selection_before_commit():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    stability_loop = helper.index("for (rounds = 1; rounds <= maxRounds; rounds++)")
    commit = helper.index("app.EndUndoScope(transactionScope, true)")
    selection = helper.index("SelectIds(app, page, finalSelection);", commit)
    assert stability_loop < commit < selection
    assert "no window selection changes are allowed while the compound" in helper
    assert helper.index("page.CreateSelection(0, 0x100)") < helper.index("app.BeginUndoScope(scopeName)")


def test_topology_helper_v358_enforces_post_move_geometry_during_vtd_stabilization():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    assert "internal sealed class GeometryExpectation" in helper
    assert "CapturePostMoveGeometry(" in helper
    assert "HashSet<string> glueOwnedEndpoints" in helper
    assert 'glueOwnedEndpoints.Contains(EndpointKey(id, "begin"))' in helper
    assert 'glueOwnedEndpoints.Contains(EndpointKey(id, "end"))' in helper
    assert 'AddGeometryExpectation(shape, id, "BeginX", expectations)' in helper
    assert 'AddGeometryExpectation(shape, id, "EndX", expectations)' in helper
    assert 'AddGeometryExpectation(shape, id, "PinX", expectations)' in helper
    assert "RepairExpectedGeometry(" in helper
    assert "VerifyExpectedGeometry(" in helper
    assert "geometryRepairedThisRound == 0" in helper
    assert "geometryRepaired.ToString(CultureInfo.InvariantCulture)" in helper
    loop = helper.index("for (rounds = 1; rounds <= maxRounds; rounds++)")
    commit = helper.index("app.EndUndoScope(transactionScope, true)")
    selection = helper.index("SelectIds(app, page, finalSelection);", commit)
    assert loop < commit < selection


def test_topology_helper_v359_commit_precedes_any_optional_selection_restore():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    loop = helper.index("for (rounds = 1; rounds <= maxRounds; rounds++)")
    commit = helper.index("app.EndUndoScope(transactionScope, true)")
    guarded_selection = helper.index("if (moves.Count == 0 && finalSelection.Count > 0)", commit)
    selection = helper.index("SelectIds(app, page, finalSelection);", guarded_selection)
    assert loop < commit < guarded_selection < selection
    assert "short-lived external COM owner must make no" in helper


def test_topology_helper_v360_move_commits_after_one_verified_pass_without_sleep():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text()
    verify = helper.index("VerifyExpectedGeometry(")
    move_fast = helper.index("if (moves.Count > 0)", verify)
    sleep = helper.index("Thread.Sleep(pollMilliseconds);", move_fast)
    commit = helper.index("app.EndUndoScope(transactionScope, true)", move_fast)
    assert move_fast < sleep < commit
    fast_block = helper[move_fast:sleep]
    assert "cleanRounds = 1;" in fast_block
    assert "break;" in fast_block
    assert "MOVE commits immediately after one complete verified repair pass" in helper
    assert "Topology-only/replacement work still needs" in helper


def test_topology_helper_v361_uses_sta_and_no_post_commit_visio_calls_for_moves():
    from pathlib import Path
    helper = Path("managed/visio/energologic_topology_restore_helper.cs").read_text(encoding="utf-8")
    assert "[STAThread]" in helper
    assert "POST_COMMIT_VISIO_CALLS_SKIPPED" in helper
    commit = helper.index('app.EndUndoScope(transactionScope, true)')
    guarded_selection = helper.index('if (moves.Count == 0 && finalSelection.Count > 0)')
    assert commit < guarded_selection
    tail = helper[commit:guarded_selection]
    assert 'SelectIds(app, page, finalSelection)' not in tail
    assert 'Trace(tracePath, "SCOPE_COMMIT_END")' in helper
    assert 'Trace(tracePath, "RESULT_WRITTEN PASS")' in helper


def test_v361_uses_unique_com_clsid_and_build_directory():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text(encoding="utf-8")
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    assert '[Guid("8B7F2A13-1F51-47F4-9D1A-A7E0F364C001")]' in cs
    assert 'clsid = "{8B7F2A13-1F51-47F4-9D1A-A7E0F364C001}"' in ext
    assert 'energologic_visio_editor_addin_v364' in ext
    assert 'EnergoLogic.VisioEditorAddinV360": "{8B7F2A13-1F51-47F4-9D1A-A7E0F360C001}"' in ext


def test_topology_helper_prepares_offscreen_selections_before_undo_scope():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text(encoding="utf-8")
    prepare = helper.index("page.CreateSelection(0, 0x100)")
    scope = helper.index("app.BeginUndoScope(scopeName)")
    assert prepare < scope
    apply_start = helper.index("private static void ApplyMoveStep(")
    apply_end = helper.index("[STAThread]", apply_start)
    apply = helper[apply_start:apply_end]
    assert "preparedSelection.Move(step.DxMm, step.DyMm, \"mm\")" in apply
    assert "SelectIds(app, page, step.MemberIds)" not in apply
    assert "app.ActiveWindow.Selection.Move" not in apply
    assert "MOVE_SELECTIONS_PREPARED" in helper


def test_topology_helper_compound_scope_is_application_bound():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text(encoding="utf-8")
    main = helper[helper.index("private static int Main(string[] args)"):]
    assert "app.BeginUndoScope(scopeName)" in main
    assert "app.EndUndoScope(transactionScope, true)" in main
    assert "transactionApp = app;" in main
    assert "SCOPE_BEGIN owner=application" in main


def test_topology_helper_auto_detaches_only_double_ended_managed_sources():
    from pathlib import Path
    helper = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_topology_restore_helper.cs").read_text(encoding="utf-8")
    assert "managedEndpointsBySource" in helper
    assert 'item.Value.Contains("begin")' in helper
    assert 'item.Value.Contains("end")' in helper
    assert "movedMemberIds.Contains(item.Key)" in helper
    assert "moveAnchorEndpoints.Contains(key)" in helper
    assert "AUTO_DETACH_DOUBLE_ENDED" in helper
    assert "EXPLICIT_DETACHES_APPLIED" in helper


def test_editor_api_hot_path_does_not_refresh_com_addins():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    start = source.index("    def invoke_energologic_editor_api(")
    end = source.index("    @mcp.tool()", start + 10)
    body = source[start:end]
    assert "addins = app.COMAddIns" in body
    assert "addins.Update()" not in body
    assert 'addins.Item("EnergoLogic.VisioEditorAddinV364")' in body


def test_editor_api_hot_path_does_not_reactivate_same_page():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    start = source.index("    def invoke_energologic_editor_api(")
    end = source.index("    @mcp.tool()", start + 10)
    body = source[start:end]
    assert "active_name != target_name or active_doc != target_doc" in body
    assert "window.Page = page_obj" in body
    prefix = body[:body.index("if active_name != target_name or active_doc != target_doc") ]
    assert "app.ActiveWindow.Page = page_obj" not in prefix




def test_v362_migrates_v361_registration():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    assert '"EnergoLogic.VisioEditorAddinV361": "{8B7F2A13-1F51-47F4-9D1A-A7E0F361C001}"' in ext


def test_v364_compilation_embeds_office_interop_and_is_anycpu():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text(encoding="utf-8")
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    installer = (root / "managed" / "visio" / "portable_kit" / "Install-EnergoLogic.ps1").read_text(encoding="utf-8-sig")
    assert '"/platform:anycpu"' in ext
    assert 'f"/link:{office_ref}"' in ext
    assert 'extensibility_ref' not in ext[ext.index("def install_energologic_editor_ui"):ext.index("def get_energologic_editor_ui_status")]
    assert 'namespace Extensibility' in cs
    assert 'B65AD801-ABAF-11D0-BB8B-00A0C90F2744' in cs
    assert '289E9AF1-4973-11D1-AE81-00A0C90F26F4' in cs
    assert '289E9AF2-4973-11D1-AE81-00A0C90F26F4' in cs
    assert 'csc.exe' not in installer
    assert '$OfficeRef' not in installer
    assert '$ExtensibilityRef' not in installer
    assert '$PrebuiltDllPath' in installer
    assert 'runtime PIA dependency' in installer


def test_v364_migrates_v362_registration():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    assert '"EnergoLogic.VisioEditorAddinV362": "{8B7F2A13-1F51-47F4-9D1A-A7E0F362C001}"' in ext


def test_managed_v364_registration_covers_both_registry_views():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    body = ext[ext.index("def install_energologic_editor_ui"):ext.index("def get_energologic_editor_ui_status")]
    assert "winreg.KEY_WOW64_64KEY" in body
    assert "winreg.KEY_WOW64_32KEY" in body
    assert "for view in registry_views" in body
    assert "discover_editor_progids" in body
    assert "delete_tree_view" in body


def test_local_idtextensibility2_matches_office_com_marshaling_contract():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text(encoding="utf-8")
    assert '[DispId(1)]' in cs and '[DispId(5)]' in cs
    assert 'MarshalAs(UnmanagedType.IDispatch)' in cs
    assert 'MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)' in cs
    assert 'MethodImplOptions.InternalCall' in cs
    assert 'MethodCodeType.Runtime' in cs


def test_v364_migrates_failed_v363_registration():
    from pathlib import Path
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    assert '"EnergoLogic.VisioEditorAddinV363": "{8B7F2A13-1F51-47F4-9D1A-A7E0F363C001}"' in ext


def test_portable_v364_installer_uses_prebuilt_binaries_without_target_compiler_or_pia():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    installer = (root / "managed" / "visio" / "portable_kit" / "Install-EnergoLogic.ps1").read_text(encoding="utf-8-sig")
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text(encoding="utf-8")
    assert '$PrebuiltDllPath' in installer and '$PrebuiltHelperPath' in installer
    assert 'Copy-Item -LiteralPath $PrebuiltDllPath' in installer
    assert 'Copy-Item -LiteralPath $PrebuiltHelperPath' in installer
    assert 'csc.exe' not in installer
    assert '$OfficeRef' not in installer
    assert 'OfficeCandidates' not in installer
    assert 'runtime PIA dependency' in installer
    builder = ext[ext.index("def build_energologic_portable_kit"):ext.index("def render_page_png") ]
    assert 'portable_dll = bin_dir / "EnergoLogic.VisioEditorAddinV364.dll"' in builder
    assert '"/platform:anycpu"' in builder
    assert 'f"/link:{office_ref}"' in builder
    assert 'RUNTIME_PIA_DEPENDENCY=NONE' in builder

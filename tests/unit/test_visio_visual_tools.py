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
                        "text": '{"managed_update":"PASS","version":"2026.10.03.109"}',
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
    assert arguments["version"] == "2026.10.03.109"
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
                "content": [{"type": "text", "text": '{"managed_update":"PASS","version":"2026.10.03.109"}'}],
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
    assert "modeless WinForms panel + Visio CommandBar toggle" in source
    assert '"LoadBehavior", 0' in source


def test_energologic_editor_v2_exposes_bounded_com_api():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    cs = (root / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (root / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert 'ProgId("EnergoLogic.VisioEditorAddinV311")' in cs
    assert 'AssemblyVersion("0.3.11.0")' in cs
    assert "public interface IEnergoLogicEditorApi" in cs
    assert "ClassInterface(ClassInterfaceType.AutoDual)" in cs
    assert "ApiDuplicateRight" in cs
    assert "ApiRepairGlueApply" in cs
    assert "ApiShowPanel" in cs
    assert "host.Object = this" in cs
    assert "def invoke_energologic_editor_api(" in ext
    assert 'addins.Item("EnergoLogic.VisioEditorAddinV311")' in ext
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
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_uses_robust_com_cell_exists_conversion():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private bool CellExists(dynamic shape, string cellName)" in cs
    assert "Convert.ToInt32(raw, CultureInfo.InvariantCulture) != 0" in cs
    assert "(bool)shape.CellExistsU" not in cs
    assert "(bool)target.CellExistsU" not in cs
    assert "(bool)terminal.CellExistsU" not in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_has_no_unsafe_explicit_dynamic_bool_casts():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "(bool)" not in cs
    assert "Convert.ToInt32(sectionExistsRaw, CultureInfo.InvariantCulture) == 0" in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_uses_native_visio_connects_as_topology_source():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "dynamic connects = shape.Connects;" in cs
    assert "connect.FromCell.NameU" in cs
    assert "connect.ToCell.NameU" in cs
    assert "connect.ToSheet.ID" in cs
    assert 'private readonly Regex _connectionCellRegex' in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_formula_fallback_resolves_vtd_shape_names_not_only_sheet_ids():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert 'Groups["target"]' in cs
    assert "candidate.NameU" in cs
    assert "candidate.Name" in cs
    assert 'Regex.Match(targetRef, @"^Sheet\\.(\\d+)$"' in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


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


def test_editor_v29_builds_native_glue_index_once_per_repair_or_doctor_command():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert cs.count("BuildConnectedEndpointIndex(page)") == 2
    assert "EndpointHasAnyGlue" not in cs
    assert "connected.Add(EndpointKey(sourceId, sourceEndpoint))" in cs
    assert "connected.Add(EndpointKey(glue.TargetId, targetEndpoint))" in cs


def test_editor_v30_uses_current_source_shape_for_native_connect_index():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert "glue = TryGetGlueTarget(source, sourceEndpoint)" in cs
    assert "connected.Add(EndpointKey(sourceId, sourceEndpoint))" in cs
    assert "ambiguity = String.Join" in cs
    assert "автоматический ремонт запрещён:" in cs


def test_editor_v31_reuses_proven_glue_target_parser_for_connectivity_index():
    from pathlib import Path
    cs = (
        Path(__file__).resolve().parents[2]
        / "managed" / "visio" / "energologic_visio_editor_addin.cs"
    ).read_text()
    assert "GlueTarget glue = null;" in cs
    assert "glue = TryGetGlueTarget(source, sourceEndpoint)" in cs
    assert "page.Shapes.ItemFromID(glue.TargetId)" in cs
    assert "connected.Add(EndpointKey(glue.TargetId, targetEndpoint))" in cs


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
    assert "уже используется shape" in cs
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
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_v34_restores_and_verifies_internal_glue_after_moves():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "internal sealed class GlueEdgeInfo" in cs
    assert "private List<GlueEdgeInfo> CaptureInternalGlue" in cs
    assert "private int RestoreInternalGlue" in cs
    assert "private void VerifyInternalGlue" in cs
    assert "InternalGlue = CaptureInternalGlue(page, cell.MemberIds)" in cs
    assert "RestoreCellTopologyAfterMove(page, state)" in cs
    assert "RestoreInternalGlue(page, state.InternalGlue)" in cs
    assert "VerifyInternalGlue(page, state.InternalGlue)" in cs
    assert "RestoreInternalGlue(page, internalGlue)" in cs
    assert "Visio потерял внутренние Glue при копировании ячейки" in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_v35_verifies_glue_against_formula_when_connects_lag():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private GlueTarget TryGetGlueTargetFromFormula" in cs
    assert "GlueTarget formulaTarget = TryGetGlueTargetFromFormula(shape, endpoint)" in cs
    assert "formulaTarget.TargetId == targetId && formulaTarget.Row == row" in cs
    assert "source {0} {1}; expected {2}/{3}" in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_v36_settles_visio_before_restoring_glue():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "private void SettleVisioAfterGeometryChange()" in cs
    assert "System.Windows.Forms.Application.DoEvents()" in cs
    assert "System.Threading.Thread.Sleep(25)" in cs
    assert cs.count("SettleVisioAfterGeometryChange();") >= 5
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_v37_restores_topology_after_geometry_scope_and_compensates():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    assert "internal sealed class CellMoveState" in cs
    assert "EnergoLogic: Геометрия распределения ячеек" in cs
    assert "app.EndUndoScope(scope, geometryCommit);" in cs
    assert "private int RestoreCellTopologyAfterMove" in cs
    assert "private string CompensateCellMoves" in cs
    assert "Исходная геометрия и Glue восстановлены." in cs
    assert 'App.ActiveWindow.Selection.Move(-state.Dx, -state.Dy, "mm")' in cs
    assert "RestoreCellTopologyAfterMove(page, state)" in cs
    assert 'ApiVersion() { return "0.3.11"; }' in cs


def test_editor_v38_schedules_post_return_topology_completion():
    from pathlib import Path
    cs = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "energologic_visio_editor_addin.cs").read_text()
    ext = (Path(__file__).resolve().parents[2] / "managed" / "visio" / "visio_managed_extension.py").read_text()
    assert "string ApiOperationStatus();" in cs
    assert "public string ApiOperationStatus()" in cs
    assert "private string ScheduleTopologyCompletion" in cs
    assert "_form.BeginInvoke((MethodInvoker)delegate" in cs
    assert '"pending"' in cs
    assert '"success"' in cs
    assert '"failed_rolled_back"' in cs
    assert "VerifyMovedCellsComplete" in cs
    assert "public void SetStatus(string value)" in cs
    assert '"operation_status": "ApiOperationStatus"' in ext
    assert 'ApiVersion() { return "0.3.11"; }' in cs


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
    assert '"migration": "v3.1-v3.10 -> v3.11"' in ext


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
    assert "Thread.Sleep(50)" in cs
    assert "VerifyGlue(shape, endpoint, targetId, row)" in cs
    assert "Glue не стабилизировался после 6 проверенных попыток" in cs
    assert "GlueEndpointWithRetry(source, edge.Endpoint, target, edge.Row)" in cs

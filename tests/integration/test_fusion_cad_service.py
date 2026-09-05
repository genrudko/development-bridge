from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.capabilities import CapabilityMatrix
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CadResult, CapabilityRecord
from app.fusion_cad.service import FusionCadService
from app.settings import DesktopNodeSettings


@pytest.fixture
def mock_desktop_service() -> DesktopNodeService:
    service = MagicMock(spec=DesktopNodeService)
    service.call = AsyncMock()
    service.submit = AsyncMock()
    service.store_external_result = MagicMock()
    return service


@pytest.mark.asyncio
async def test_service_executes_capabilities_read_and_persists_matrix(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)

    records = [
        CapabilityRecord(name="design.access", state="supported", implementation="adsk.fusion.Design"),
        CapabilityRecord(name="view.pick", state="degraded", implementation="native-preselect", limitations=("Visual pick requires live feasibility proof",)),
        CapabilityRecord(name="export.dxf", state="unavailable", limitations=("DXF export contract semantics not supported on this runtime; capability-gated until P2",)),
    ]
    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Runtime capabilities probed",
                "data": {
                    "application": "Autodesk Fusion",
                    "fusion_version": "2.0.18000",
                    "relay_version": "1.0.0",
                    "platform": "Windows",
                    "probe_facts": {"has_app": True},
                },
                "capabilities": [r.model_dump(mode="json") for r in records],
            }),
        }],
        "isError": False,
    })

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"},
        group="read",
    )
    assert isinstance(result, CadResult)
    assert result.status == "succeeded"
    assert result.capabilities is not None
    assert len(result.capabilities) == 3

    # Assert service saved probed matrix for desk-1
    saved_matrix = cad_service.get_node_capabilities("desk-1")
    assert saved_matrix is not None
    assert saved_matrix.identity is not None
    assert saved_matrix.identity.fusion_version == "2.0.18000"
    assert saved_matrix.identity.local_tool == "fusion_mcp_execute"
    assert saved_matrix.identity.probe_details.get("has_app") is True
    assert saved_matrix.get("view.pick").state == "degraded"
    assert saved_matrix.get("export.dxf").state == "unavailable"


@pytest.mark.asyncio
async def test_falsify_finding_1_unprobed_node_fails_closed_before_script_dispatch(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)

    # Node has never been probed
    assert cad_service.get_node_capabilities("desk-unprobed") is None

    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-unprobed", "operation": "entity", "ref": "ent_1"},
            group="read",
        )

    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert isinstance(exc_info.value, FusionCadError)
    assert "unprobed" in exc_info.value.message
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0


@pytest.mark.asyncio
async def test_falsify_finding_1_read_capabilities_stays_ungated_on_unprobed_node(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)

    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Runtime capabilities probed",
                "capabilities": [
                    {"name": "design.access", "state": "supported"},
                ],
            }),
        }],
        "isError": False,
    })

    # read:capabilities must NOT be gated and can probe unprobed node
    result = await cad_service.execute(
        {"node_id": "desk-new", "operation": "capabilities"},
        group="read",
    )
    assert isinstance(result, CadResult)
    assert mock_desktop_service.call.call_count == 1
    assert cad_service.get_node_capabilities("desk-new") is not None


@pytest.mark.asyncio
async def test_falsify_finding_1_no_cross_node_leakage(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)

    # Configure matrix ONLY for desk-1
    cad_service.set_node_capabilities("desk-1", CapabilityMatrix.from_records([
        CapabilityRecord(name="entity.token_resolver", state="supported"),
    ]))

    # desk-2 has NOT been probed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-2", "operation": "entity", "ref": "ent_1"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "desk-2" in exc_info.value.details.get("node_id")


@pytest.mark.asyncio
async def test_falsify_finding_1_cache_invalidation_fails_closed(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)

    cad_service.set_node_capabilities("desk-1", CapabilityMatrix.from_records([
        CapabilityRecord(name="entity.token_resolver", state="supported"),
    ]))
    assert cad_service.get_node_capabilities("desk-1") is not None

    # Invalidate cache for desk-1
    cad_service.invalidate_node_capabilities("desk-1")
    assert cad_service.get_node_capabilities("desk-1") is None

    # Gated operation now fails closed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "entity", "ref": "ent_1"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE


def test_falsify_finding_1_no_default_supported_fabrication():
    # Assert CapabilityMatrix has no default_supported fabrication method
    assert not hasattr(CapabilityMatrix, "default_supported")


@pytest.mark.asyncio
async def test_falsify_finding_4_degraded_capability_blocks_without_generic_bypass(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)

    degraded_matrix = CapabilityMatrix.from_records([
        CapabilityRecord(
            name="view.pick",
            state="degraded",
            implementation="viewport-raycast",
            limitations=("Visual pick requires live feasibility proof",),
        )
    ])
    cad_service.set_node_capabilities("desk-1", degraded_matrix)

    # 1. Calling execute fails closed with CAPABILITY_DEGRADED
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "pick", "view_ref": "view_1234", "x": 0.5, "y": 0.5},
            group="view",
        )

    assert exc_info.value.code == ErrorCode.CAPABILITY_DEGRADED
    assert isinstance(exc_info.value, FusionCadError)
    assert exc_info.value.retryable is False
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0

    # 2. execute has NO allow_degraded parameter (inspect signature)
    import inspect
    sig = inspect.signature(cad_service.execute)
    assert "allow_degraded" not in sig.parameters

    # 3. Payload with {"allow_degraded": True} is rejected by strict schema (extra="forbid")
    with pytest.raises(BridgeError) as exc_schema:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "pick",
                "view_ref": "view_1234",
                "x": 0.5,
                "y": 0.5,
                "allow_degraded": True,
            },
            group="view",
        )
    assert exc_schema.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize("group, operation, payload, required_cap", [
    ("inspect", "describe", {"node_id": "desk-1", "operation": "describe", "target": "ent_1"}, "inspect.measure"),
    ("inspect", "distance", {"node_id": "desk-1", "operation": "distance", "target_a": "ent_1", "target_b": "ent_2"}, "inspect.measure"),
    ("view", "camera_set", {"node_id": "desk-1", "operation": "camera_set", "fov": 45.0}, "view.camera"),
    ("view", "pick", {"node_id": "desk-1", "operation": "pick", "view_ref": "view_1", "x": 0.5, "y": 0.5}, "view.pick"),
    ("metadata", "set", {"node_id": "desk-1", "operation": "set", "target": "ent_1", "name": "k", "value": "v"}, "metadata.attributes"),
    ("style", "text_create", {"node_id": "desk-1", "operation": "text_create", "text": "t", "height_mm": 5.0, "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}}}, "style.sketch_text"),
    ("style", "show", {"node_id": "desk-1", "operation": "show", "target": "ent_1"}, "design.access"),
    ("read", "entity", {"node_id": "desk-1", "operation": "entity", "ref": "ent_1"}, "entity.token_resolver"),
    ("read", "feature_tree", {"node_id": "desk-1", "operation": "feature_tree"}, "timeline.access"),
    ("read", "sketch", {"node_id": "desk-1", "operation": "sketch", "ref": "ent_1"}, "sketch.access"),
    ("validate", "run", {"node_id": "desk-1", "operation": "run"}, "design.access"),
    ("transaction", "begin", {"node_id": "desk-1", "operation": "begin"}, "transaction.preview_replay"),
    ("transaction", "preview", {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1"}, "transaction.preview_replay"),
])
@pytest.mark.asyncio
async def test_falsify_all_p0_domains_capability_gating(
    mock_desktop_service: DesktopNodeService,
    group: str,
    operation: str,
    payload: dict,
    required_cap: str,
):
    cad_service = FusionCadService(mock_desktop_service)

    # Configure matrix where this specific capability is unavailable
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name=required_cap, state="unavailable", limitations=(f"{required_cap} is unavailable",))
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(payload, group=group)

    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert isinstance(exc_info.value, FusionCadError)
    assert exc_info.value.retryable is False
    assert exc_info.value.details.get("capability") == required_cap

    # ZERO dispatch calls
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0


@pytest.fixture
def real_desktop_service(tmp_path) -> DesktopNodeService:
    settings = DesktopNodeSettings.model_validate({
        "token": "test-token",
        "journal_path": str(tmp_path / "journal.jsonl"),
        "call_timeout_seconds": 1.0,
    })
    return DesktopNodeService(settings)


@pytest.mark.asyncio
async def test_falsify_same_node_reconnect_invalidates_capabilities_real_service(real_desktop_service: DesktopNodeService):
    # 1. Register desk-1
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    assert real_desktop_service.get_session_generation("desk-1") == 1

    cad_service = FusionCadService(real_desktop_service)

    # 2. Set capability matrix for desk-1
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="design.access", state="supported", implementation="adsk.fusion.Design"),
        CapabilityRecord(name="entity.token_resolver", state="supported", implementation="adsk.fusion.Design.findEntityByToken"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)
    assert cad_service.get_node_capabilities("desk-1") is not None

    # 3. Same-node reconnect: register() is called again for desk-1
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    assert real_desktop_service.get_session_generation("desk-1") == 2

    # 4. Cached capabilities must be invalidated immediately
    assert cad_service.get_node_capabilities("desk-1") is None

    # 5. Gated operation fails closed with CAPABILITY_UNAVAILABLE
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "unprobed" in exc_info.value.message

    # 6. read:capabilities stays ungated even after reconnect
    real_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Runtime capabilities probed",
                "capabilities": [
                    {"name": "design.access", "state": "supported", "implementation": "adsk.fusion.Design"},
                ],
            }),
        }],
        "isError": False,
    })
    res = await cad_service.execute({"node_id": "desk-1", "operation": "capabilities"}, group="read")
    assert isinstance(res, CadResult)

    # Now re-probed capabilities are cached with generation 2
    assert cad_service.get_node_capabilities("desk-1") is not None
    assert cad_service.get_node_capabilities("desk-1").get("design.access").state == "supported"


@pytest.mark.asyncio
async def test_falsify_tool_change_invalidates_capabilities_real_service(real_desktop_service: DesktopNodeService):
    # 1. Register desk-1
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    cad_service = FusionCadService(real_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)
    assert cad_service.get_node_capabilities("desk-1") is not None

    # 2. Node changes tools via heartbeat
    await real_desktop_service.heartbeat(
        "desk-1",
        tools=[{"name": "fusion_mcp_execute"}, {"name": "other_tool"}],
    )
    assert real_desktop_service.get_session_generation("desk-1") == 2

    # 3. Cache invalidated
    assert cad_service.get_node_capabilities("desk-1") is None

    # 4. Gated operation fails closed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_falsify_runtime_change_invalidates_capabilities_real_service(real_desktop_service: DesktopNodeService):
    # 1. Register desk-1 with fusion_available=True
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    cad_service = FusionCadService(real_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)
    assert cad_service.get_node_capabilities("desk-1") is not None

    # 2. Node reports fusion_available=False via heartbeat
    await real_desktop_service.heartbeat("desk-1", fusion_available=False)
    assert real_desktop_service.get_session_generation("desk-1") == 2

    # 3. Cache invalidated
    assert cad_service.get_node_capabilities("desk-1") is None

    # 4. Gated operation fails closed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_falsify_cross_node_isolation_during_reconnect_real_service(real_desktop_service: DesktopNodeService):
    # 1. Register desk-1 and desk-2
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    await real_desktop_service.register("desk-2", [{"name": "fusion_mcp_execute"}], True)

    cad_service = FusionCadService(real_desktop_service)
    matrix1 = CapabilityMatrix.from_records([CapabilityRecord(name="design.access", state="supported")])
    matrix2 = CapabilityMatrix.from_records([CapabilityRecord(name="design.access", state="supported")])
    cad_service.set_node_capabilities("desk-1", matrix1)
    cad_service.set_node_capabilities("desk-2", matrix2)

    assert cad_service.get_node_capabilities("desk-1") is not None
    assert cad_service.get_node_capabilities("desk-2") is not None

    # 2. desk-1 reconnects
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)

    # 3. desk-1 cache is invalidated; desk-2 remains VALID
    assert cad_service.get_node_capabilities("desk-1") is None
    assert cad_service.get_node_capabilities("desk-2") is not None

    # 4. desk-1 gated operation fails closed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE

    # 5. desk-2 gated operation proceeds to dispatch
    real_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Executed model_snapshot",
                "data": {"components": []},
            }),
        }],
        "isError": False,
    })
    res2 = await cad_service.execute(
        {"node_id": "desk-2", "operation": "model_snapshot"},
        group="read",
    )
    assert isinstance(res2, CadResult)
    assert res2.status == "succeeded"


@pytest.mark.asyncio
async def test_falsify_in_flight_capability_probe_race_re_registration(real_desktop_service: DesktopNodeService):
    """Proves that if a node re-registers while read:capabilities is in-flight,
    the old probe result is discarded, capabilities remain unprobed, and subsequent
    gated operations fail closed with CAPABILITY_UNAVAILABLE.
    """
    # 1. Register desk-1 (generation 1)
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    assert real_desktop_service.get_session_generation("desk-1") == 1

    cad_service = FusionCadService(real_desktop_service)

    # 2. Simulate in-flight race: during the probe dispatch call, desk-1 re-registers
    orig_call = real_desktop_service.call

    async def call_with_race(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        # Trigger re-registration mid-probe -> bumps session_generation to 2
        await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
        assert real_desktop_service.get_session_generation("desk-1") == 2
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Probed during race",
                    "capabilities": [
                        {"name": "design.access", "state": "supported", "implementation": "adsk.fusion.Design"},
                    ],
                }),
            }],
            "isError": False,
        }

    real_desktop_service.call = call_with_race  # type: ignore[assignment]

    # 3. Dispatch read:capabilities
    res = await cad_service.execute({"node_id": "desk-1", "operation": "capabilities"}, group="read")
    assert isinstance(res, CadResult)

    # 4. Old in-flight probe result must be DISCARDED and NOT cached
    assert cad_service.get_node_capabilities("desk-1") is None

    # 5. Subsequent gated operation must FAIL closed because capability state is unprobed
    real_desktop_service.call = orig_call
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "unprobed" in exc_info.value.message

    # 6. Re-probing after the race succeeds and caches for generation 2
    real_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Probed clean",
                "capabilities": [
                    {"name": "design.access", "state": "supported", "implementation": "adsk.fusion.Design"},
                ],
            }),
        }],
        "isError": False,
    })
    await cad_service.execute({"node_id": "desk-1", "operation": "capabilities"}, group="read")
    assert cad_service.get_node_capabilities("desk-1") is not None
    assert cad_service.get_node_capabilities("desk-1").get("design.access").state == "supported"


@pytest.mark.asyncio
async def test_falsify_in_flight_capability_probe_race_cross_node_isolation(real_desktop_service: DesktopNodeService):
    """Proves in-flight race on desk-1 leaves desk-1 unprobed without affecting desk-2."""
    await real_desktop_service.register("desk-1", [{"name": "fusion_mcp_execute"}], True)
    await real_desktop_service.register("desk-2", [{"name": "fusion_mcp_execute"}], True)

    cad_service = FusionCadService(real_desktop_service)
    # desk-2 has valid cached capabilities
    matrix2 = CapabilityMatrix.from_records([CapabilityRecord(name="design.access", state="supported")])
    cad_service.set_node_capabilities("desk-2", matrix2)
    assert cad_service.get_node_capabilities("desk-2") is not None

    # In-flight race occurs on desk-1
    async def call_race_desk1(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        if node_id == "desk-1":
            # Tool change on desk-1 -> bumps generation
            await real_desktop_service.heartbeat("desk-1", tools=[{"name": "fusion_mcp_execute"}, {"name": "aux"}])
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Probed during race",
                    "capabilities": [
                        {"name": "design.access", "state": "supported", "implementation": "adsk.fusion.Design"},
                    ],
                }),
            }],
            "isError": False,
        }

    real_desktop_service.call = call_race_desk1  # type: ignore[assignment]
    await cad_service.execute({"node_id": "desk-1", "operation": "capabilities"}, group="read")

    # desk-1 discarded, desk-2 unaffected
    assert cad_service.get_node_capabilities("desk-1") is None
    assert cad_service.get_node_capabilities("desk-2") is not None


# =========================================================================
# Task 4: Model revision tracking, Bridge precheck, and Fusion-side guard
# =========================================================================


@pytest.mark.asyncio
async def test_service_assert_fresh_for_mutation_interface(mock_desktop_service: DesktopNodeService):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.revision_tracker.observe("doc_1", "hash-v1")

    # 1. Matching expected_revision via dict payload succeeds
    rec1 = cad_service.assert_fresh_for_mutation(
        {"document_ref": "doc_1", "expected_revision": "rev_1"}
    )
    assert rec1.revision == "rev_1"

    # 2. Matching expected_revision via explicit arguments succeeds
    rec2 = cad_service.assert_fresh_for_mutation(document_ref="doc_1", expected_revision="rev_1")
    assert rec2.revision == "rev_1"

    # 3. Advance revision via external change
    cad_service.revision_tracker.observe("doc_1", "hash-v2")
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

    # 4. Stale expected_revision raises REVISION_CONFLICT
    with pytest.raises(FusionCadError) as exc_stale:
        cad_service.assert_fresh_for_mutation(
            {"document_ref": "doc_1", "expected_revision": "rev_1"}
        )
    assert exc_stale.value.code == ErrorCode.REVISION_CONFLICT
    assert exc_stale.value.details.get("expected_revision") == "rev_1"
    assert exc_stale.value.details.get("current_revision") == "rev_2"

    # 5. Missing expected_revision raises REVISION_CONFLICT
    with pytest.raises(FusionCadError) as exc_none:
        cad_service.assert_fresh_for_mutation(
            {"document_ref": "doc_1"}
        )
    assert exc_none.value.code == ErrorCode.REVISION_CONFLICT


@pytest.mark.asyncio
async def test_falsify_stale_expected_revision_blocks_at_bridge_precheck(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    # Observe doc_1 at rev_1 and advance to rev_2
    cad_service.revision_tracker.observe("doc_1", "hash-v1")
    cad_service.revision_tracker.observe("doc_1", "hash-v2")

    # Mutation request with stale rev_1
    stale_request = {
        "node_id": "desk-1",
        "operation": "set",
        "target": "ent_1",
        "name": "status",
        "value": "active",
        "expected_revision": "rev_1",
    }

    # Bridge precheck blocks before calling executor / desktop node
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(stale_request, group="metadata")

    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert isinstance(exc_info.value, FusionCadError)
    assert exc_info.value.details.get("expected_revision") == "rev_1"
    assert exc_info.value.details.get("current_revision") == "rev_2"
    # Proves desktop node call was never dispatched (fail fast)
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0


import sys
import types


class AdskFakeContext:
    """Sets up a realistic fake Autodesk Fusion runtime in sys.modules for rendered script execution."""

    def __init__(self, doc_ref="doc_1", initial_volume=100.0):
        self.doc_ref = doc_ref
        self.volume = initial_volume
        self.mutated = False
        self.tx_committed = False
        self.tx_previewed = False
        self.attributes = []

    def __enter__(self):
        ctx = self
        adsk = types.ModuleType("adsk")
        adsk_core = types.ModuleType("adsk.core")
        adsk_fusion = types.ModuleType("adsk.fusion")

        class FakePoint:
            def __init__(self, x=0.0, y=0.0, z=0.0):
                self.x = float(x)
                self.y = float(y)
                self.z = float(z)

        class FakeBoundingBox:
            def __init__(self, min_pt, max_pt):
                self.minPoint = min_pt
                self.maxPoint = max_pt

        class FakeCollection:
            def __init__(self, items=None):
                self._items = list(items or [])

            @property
            def count(self):
                return len(self._items)

            def item(self, idx):
                return self._items[idx]

            def add(self, *args, **kwargs):
                pass

        class FakeAttributes:
            def __init__(self, ctx):
                self._ctx = ctx

            @property
            def count(self):
                return len(self._ctx.attributes)

            def item(self, idx):
                return self._ctx.attributes[idx]

            def add(self, group_name, name, value):
                class Attr:
                    def __init__(self, g, n, v):
                        self.groupName = g
                        self.name = n
                        self.value = v
                self._ctx.attributes.append(Attr(group_name, name, value))

        class FakeBody:
            def __init__(self, ctx):
                self._ctx = ctx
                self.name = "Body1"
                self.isSolid = True
                self.isVisible = True
                self.isLightBulbOn = True
                self.area = 50.0
                self.faces = FakeCollection([object() for _ in range(6)])
                self.edges = FakeCollection([object() for _ in range(12)])
                self.boundingBox = FakeBoundingBox(FakePoint(0, 0, 0), FakePoint(10, 10, 10))

            @property
            def volume(self):
                return float(self._ctx.volume)

        class FakeConstraint:
            def __init__(self, obj_type="HorizontalConstraint", is_deletable=True):
                self.objectType = obj_type
                self.isDeletable = is_deletable

        class FakeDimension:
            def __init__(self, name="d1", val=10.0, expr="10 mm"):
                class Param:
                    def __init__(self, n, v, e):
                        self.name = n
                        self.value = v
                        self.expression = e
                self.name = name
                self.value = val
                self.parameter = Param(name, val, expr)

        class FakeSketch:
            def __init__(self):
                self.name = "Sketch1"
                self.isVisible = True
                self.isLightBulbOn = True
                self.profiles = FakeCollection([object()])
                self.sketchCurves = FakeCollection([object(), object(), object(), object()])
                self.geometricConstraints = FakeCollection([FakeConstraint()])
                self.sketchDimensions = FakeCollection([FakeDimension()])

        class FakeComponent:
            def __init__(self, ctx):
                self._ctx = ctx
                self.name = "Root"
                self.id = "comp_root"
                self.bRepBodies = FakeCollection([FakeBody(ctx)])
                self.sketches = FakeCollection([FakeSketch()])
                self.allOccurrences = FakeCollection([])

        class FakeTimelineItem:
            def __init__(self):
                self.index = 0
                self.entityToken = "feat_extrude_1"
                self.name = "Extrude1"
                self.isSuppressed = False
                self.isValid = True
                self.isRolledBack = False
                self.healthStatus = "ok"

        class FakeParameter:
            def __init__(self):
                self.name = "length"
                self.expression = "100 mm"
                self.value = 100.0
                self.unit = "mm"
                self.isFavorite = False

        class FakeDesign:
            def __init__(self, ctx):
                self._ctx = ctx
                self.rootComponent = FakeComponent(ctx)
                self.allComponents = FakeCollection([self.rootComponent])
                self.timeline = FakeCollection([FakeTimelineItem()])
                self.allParameters = FakeCollection([FakeParameter()])

        class FakeDocument:
            def __init__(self, ctx):
                self._ctx = ctx
                self.dataId = ctx.doc_ref
                self.name = "TestDoc"
                self.isModified = False
                self.savedVersion = 1
                self.attributes = FakeAttributes(ctx)
                self._design = FakeDesign(ctx)

                class Products:
                    def __init__(self, design):
                        self._design = design

                    def itemByClass(self, cls_name):
                        if "Design" in cls_name:
                            return self._design
                        return None

                self.products = Products(self._design)

        class FakeApplication:
            def __init__(self, ctx):
                self._doc = FakeDocument(ctx)

            @property
            def activeDocument(self):
                return self._doc

            @classmethod
            def get(cls):
                return cls._instance

        FakeApplication._instance = FakeApplication(ctx)
        adsk_core.Application = FakeApplication
        adsk.core = adsk_core
        adsk.fusion = adsk_fusion

        self._saved_modules = {
            "adsk": sys.modules.get("adsk"),
            "adsk.core": sys.modules.get("adsk.core"),
            "adsk.fusion": sys.modules.get("adsk.fusion"),
        }
        sys.modules["adsk"] = adsk
        sys.modules["adsk.core"] = adsk_core
        sys.modules["adsk.fusion"] = adsk_fusion
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for mod, val in self._saved_modules.items():
            if val is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = val


@pytest.mark.asyncio
async def test_falsify_rendered_script_standalone_mutation_stale_blocks_fresh_applies(
    mock_desktop_service: DesktopNodeService,
):
    """Exercises rendered production mutate script against adsk fake: stale baseline blocks, fresh applies."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records([
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="revision.external_change_detection", state="supported"),
        ])
        cad_service.set_node_capabilities("desk-1", matrix)

        # Execute rendered script directly inside desktop node submit/call
        async def run_rendered_production_script(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_mutation_primitive": lambda payload: setattr(fake_adsk, "mutated", True),
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

        # 1. Initial snapshot read: exercises production read script and seeds Bridge tracker with baseline
        snap_res = await cad_service.execute({"node_id": "desk-1", "operation": "model_snapshot"}, group="read")
        assert isinstance(snap_res, CadResult)
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"
        initial_fp = cad_service.revision_tracker.current("doc_1").fingerprint

        # 2. External change occurs in Fusion (body geometry mutated)
        fake_adsk.volume = 200.0

        # 3. Attempt standalone mutation with stale expected_revision="rev_1"
        # Bridge precheck passes (Bridge still recorded rev_1), but authoritative Fusion-side guard in rendered script catches it!
        with pytest.raises(BridgeError) as exc_guard:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": "ent_1",
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                },
                group="metadata",
            )

        assert exc_guard.value.code == ErrorCode.REVISION_CONFLICT
        assert exc_guard.value.details.get("applied") is False
        # Proves mutation primitive in rendered script was NOT reached
        assert fake_adsk.mutated is False
        # Proves current_fingerprint diverged from initial_fp
        diverged_fp = exc_guard.value.details.get("current_fingerprint")
        assert diverged_fp != initial_fp

        # Proves Bridge tracker observed diverged_fp and advanced to rev_2
        current_rec = cad_service.revision_tracker.current("doc_1")
        assert current_rec.revision == "rev_2"
        assert current_rec.fingerprint == diverged_fp

        # 4. Immediate second call with rev_1 now blocks at Bridge precheck (no executor dispatch)
        with pytest.raises(BridgeError) as exc_precheck:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": "ent_1",
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                },
                group="metadata",
            )
        assert exc_precheck.value.code == ErrorCode.REVISION_CONFLICT
        assert exc_precheck.value.details.get("current_revision") == "rev_2"

        # 5. Standalone mutation with fresh expected_revision="rev_2" succeeds
        success_res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": "ent_1",
                "name": "tag",
                "value": "v1",
                "expected_revision": "rev_2",
            },
            group="metadata",
        )
        if isinstance(success_res, CadResult):
            assert success_res.status == "succeeded"
            assert success_res.data.get("applied") is True
        else:
            assert success_res.get("status") == "succeeded"
            assert success_res.get("data", {}).get("applied") is True

        # Proves mutation primitive WAS reached and executed
        assert fake_adsk.mutated is True
        # Proves Bridge tracker advanced to rev_3
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_3"


@pytest.mark.asyncio
async def test_service_read_observes_document_and_populates_tracker(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Model snapshot read",
                "document": {
                    "document_ref": "doc_imported",
                    "model_revision": "rev_1",
                    "name": "ImportedDesign",
                    "units": "mm",
                },
                "data": {
                    "fingerprint": "hash-imported-model",
                },
            }),
        }],
        "isError": False,
    })

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot", "detail": "compact"},
        group="read",
    )
    assert isinstance(result, CadResult)
    rec = cad_service.revision_tracker.current("doc_imported")
    assert rec is not None
    assert rec.revision == "rev_1"
    assert rec.fingerprint == "hash-imported-model"


@pytest.mark.asyncio
async def test_falsify_rendered_script_transaction_preview_and_commit_stale_blocks_fresh_applies(
    mock_desktop_service: DesktopNodeService,
):
    """Exercises rendered production transaction script against adsk fake: stale blocks, fresh applies."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records([
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="revision.external_change_detection", state="supported"),
        ])
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_transaction_commit_primitive": lambda payload: setattr(fake_adsk, "tx_committed", True),
                "_transaction_preview_primitive": lambda payload: setattr(fake_adsk, "tx_previewed", True),
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

        # 1. Initial read seeds Bridge tracker
        await cad_service.execute({"node_id": "desk-1", "operation": "model_snapshot"}, group="read")
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"

        # 1b. Begin transaction records baseline_revision="rev_1"
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "begin",
                "transaction_id": "tx_1234",
            },
            group="transaction",
        )
        stored_bl = cad_service.revision_tracker.get_transaction_baseline("tx_1234")
        assert stored_bl is not None
        assert stored_bl["baseline_revision"] == "rev_1"

        # 2. External change occurs in Fusion
        fake_adsk.volume = 300.0

        # 3. Transaction commit with stale tx_1234: rendered script freshness guard rejects before apply
        with pytest.raises(BridgeError) as exc_commit:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "commit",
                    "transaction_id": "tx_1234",
                    "expected_revision": "rev_1",
                },
                group="transaction",
            )
        assert exc_commit.value.code == ErrorCode.REVISION_CONFLICT
        assert exc_commit.value.details.get("applied") is False
        assert fake_adsk.tx_committed is False
        # Proves Bridge tracker observed new fingerprint and advanced to rev_2
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

        # 4. Another external change occurs
        fake_adsk.volume = 400.0

        # 5. Transaction preview with stale tx_1234: Bridge precheck rejects before preview
        with pytest.raises(BridgeError) as exc_preview:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "preview",
                    "transaction_id": "tx_1234",
                    "expected_revision": "rev_2",
                },
                group="transaction",
            )
        assert exc_preview.value.code == ErrorCode.REVISION_CONFLICT
        assert exc_preview.value.details.get("applied") is False
        assert fake_adsk.tx_previewed is False
        # Bridge precheck failed fast without dispatching to Fusion, so tracker remains at rev_2
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

        # 5b. Caller attempting to bypass baseline by passing expected_revision="rev_2" on tx_1234 STILL FAILS
        # because preview/commit always binds to stored baseline ("rev_1"), never caller-selected revision
        with pytest.raises(BridgeError) as exc_bypass:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "commit",
                    "transaction_id": "tx_1234",
                    "expected_revision": "rev_2",
                },
                group="transaction",
            )
        assert exc_bypass.value.code == ErrorCode.REVISION_CONFLICT

        # 6. Read syncs the external change (volume 400.0) into Bridge tracker -> rev_3
        await cad_service.execute({"node_id": "desk-1", "operation": "model_snapshot"}, group="read")
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_3"

        # 7. Abort stale transaction and begin fresh one at rev_3
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "abort",
                "transaction_id": "tx_1234",
            },
            group="transaction",
        )
        assert cad_service.revision_tracker.get_transaction_baseline("tx_1234") is None

        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "begin",
                "transaction_id": "tx_fresh",
            },
            group="transaction",
        )
        fresh_bl = cad_service.revision_tracker.get_transaction_baseline("tx_fresh")
        assert fresh_bl is not None
        assert fresh_bl["baseline_revision"] == "rev_3"

        # 8. Transaction preview on fresh transaction succeeds
        res_preview = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "preview",
                "transaction_id": "tx_fresh",
            },
            group="transaction",
        )
        data = res_preview.data if isinstance(res_preview, CadResult) else res_preview.get("data", {})
        assert data.get("preview") is True
        assert fake_adsk.tx_previewed is True

        # 9. Transaction commit on fresh transaction succeeds
        res_commit = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_fresh",
            },
            group="transaction",
        )
        commit_data = res_commit.data if isinstance(res_commit, CadResult) else res_commit.get("data", {})
        assert commit_data.get("applied") is True
        assert fake_adsk.tx_committed is True
        assert cad_service.revision_tracker.get_transaction_baseline("tx_fresh") is None


@pytest.mark.asyncio
async def test_falsify_missing_expected_revision_rejected_before_dispatch(
    mock_desktop_service: DesktopNodeService,
):
    """Proves standalone mutation requires expected_revision and rejects before script generation/dispatch."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    # Standalone mutation without expected_revision
    req = {
        "node_id": "desk-1",
        "operation": "set",
        "target": "ent_1",
        "name": "tag",
        "value": "v1",
    }
    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(req, group="metadata")

    assert exc.value.code == ErrorCode.REVISION_CONFLICT
    assert "expected_revision is required" in exc.value.message
    # Proves desktop node was never dispatched
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0


@pytest.mark.asyncio
async def test_falsify_degraded_or_unavailable_revision_capability_blocks_mutation(
    mock_desktop_service: DesktopNodeService,
):
    """Proves every mutation/preview/commit blocks if revision.external_change_detection is degraded or unavailable."""
    cad_service = FusionCadService(mock_desktop_service)

    # Case A: Degraded revision capability (conservative runtime state)
    matrix_degraded = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="transaction.preview_replay", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="degraded", limitations=["Unverified"]),
    ])
    cad_service.set_node_capabilities("desk-1", matrix_degraded)
    cad_service.revision_tracker.observe("doc_1", "hash-1")

    # 1. Standalone mutation blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_mut:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "set", "target": "ent_1", "name": "t", "value": "v", "expected_revision": "rev_1"},
            group="metadata",
        )
    assert exc_mut.value.code == ErrorCode.CAPABILITY_DEGRADED

    # 2. Transaction preview blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_prev:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1", "expected_revision": "rev_1"},
            group="transaction",
        )
    assert exc_prev.value.code == ErrorCode.CAPABILITY_DEGRADED

    # 3. Transaction commit blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_comm:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_1", "expected_revision": "rev_1"},
            group="transaction",
        )
    assert exc_comm.value.code == ErrorCode.CAPABILITY_DEGRADED

    # Case B: Unavailable revision capability
    matrix_unavail = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="transaction.preview_replay", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="unavailable", limitations=["Not supported"]),
    ])
    cad_service.set_node_capabilities("desk-1", matrix_unavail)

    with pytest.raises(FusionCadError) as exc_unavail:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "set", "target": "ent_1", "name": "t", "value": "v", "expected_revision": "rev_1"},
            group="metadata",
        )
    assert exc_unavail.value.code == ErrorCode.CAPABILITY_UNAVAILABLE

    # Transaction staging does NOT require revision.external_change_detection
    cad_service.revision_tracker.begin_transaction("tx_1", "doc_1")
    mock_desktop_service.submit = AsyncMock(return_value={"status": "queued", "operation_id": "op_stage"})
    stage_res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "stage",
            "transaction_id": "tx_1",
            "action": {"action_type": "show", "target": "ent_1"},
        },
        group="transaction",
    )
    assert stage_res is not None


@pytest.mark.asyncio
async def test_falsify_conservative_revision_and_p0_p2_capabilities(
    mock_desktop_service: DesktopNodeService,
):
    """Proves conservative capability states: revision.external_change_detection degraded, P2 unavailable."""
    cad_service = FusionCadService(mock_desktop_service)

    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Runtime capabilities probed",
                "capabilities": [
                    {
                        "name": "revision.external_change_detection",
                        "state": "degraded",
                        "implementation": "timeline-fingerprint-guard",
                        "limitations": ["Fusion-side revision freshness guard and external-change atomicity not guaranteed at contract level; unverified without active runtime atomicity proof"],
                    },
                    {
                        "name": "view.pick",
                        "state": "degraded",
                        "implementation": "native-preselect",
                        "limitations": ["Visual pick requires live feasibility proof"],
                    },
                    {
                        "name": "transaction.preview_replay",
                        "state": "degraded",
                        "implementation": "manual-replay",
                        "limitations": ["Transaction preview replay requires live feasibility proof"],
                    },
                    {
                        "name": "export.dxf",
                        "state": "unavailable",
                        "limitations": ["DXF export contract semantics not supported on this runtime; capability-gated until P2"],
                    },
                    {
                        "name": "view.section",
                        "state": "unavailable",
                        "limitations": ["Section view analysis contract semantics not available on this runtime; capability-gated until P2"],
                    },
                    {
                        "name": "assembly.joints",
                        "state": "unavailable",
                        "limitations": ["Assembly joint operations not supported on this runtime; capability-gated until P2"],
                    },
                ],
            }),
        }],
        "isError": False,
    })

    result = await cad_service.execute({"node_id": "desk-1", "operation": "capabilities"}, group="read")
    assert isinstance(result, CadResult)

    matrix = cad_service.get_node_capabilities("desk-1")
    assert matrix is not None

    # 1. revision.external_change_detection must be degraded, not supported
    rev_cap = matrix.get("revision.external_change_detection")
    assert rev_cap is not None
    assert rev_cap.state == "degraded"
    assert "Fusion-side revision freshness guard" in rev_cap.limitations[0]

    # 2. Conservative capabilities remain degraded
    assert matrix.get("view.pick").state == "degraded"
    assert matrix.get("transaction.preview_replay").state == "degraded"

    # 3. P2 capabilities remain unavailable
    assert matrix.get("export.dxf").state == "unavailable"
    assert matrix.get("view.section").state == "unavailable"
    assert matrix.get("assembly.joints").state == "unavailable"


@pytest.mark.asyncio
async def test_falsify_service_document_switch_and_multi_document_isolation(
    mock_desktop_service: DesktopNodeService,
):
    """Proves multiple documents maintain distinct revisions and don't corrupt each other."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    # Read doc_1
    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Read doc_1",
                "document": {"document_ref": "doc_1", "model_revision": "rev_1", "name": "Doc1", "units": "mm"},
                "data": {"fingerprint": "hash-doc-1-v1"},
            }),
        }],
        "isError": False,
    })
    await cad_service.execute({"node_id": "desk-1", "operation": "model_snapshot"}, group="read")

    # Read doc_2
    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{
            "type": "text",
            "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Read doc_2",
                "document": {"document_ref": "doc_2", "model_revision": "rev_1", "name": "Doc2", "units": "mm"},
                "data": {"fingerprint": "hash-doc-2-v1"},
            }),
        }],
        "isError": False,
    })
    await cad_service.execute({"node_id": "desk-1", "operation": "model_snapshot"}, group="read")

    # Assert both documents tracked independently at rev_1
    assert cad_service.assert_fresh_for_mutation(document_ref="doc_1", expected_revision="rev_1").revision == "rev_1"
    assert cad_service.assert_fresh_for_mutation(document_ref="doc_2", expected_revision="rev_1").revision == "rev_1"

    # External change advances doc_1 to rev_2
    cad_service.revision_tracker.observe("doc_1", "hash-doc-1-v2")
    assert cad_service.assert_fresh_for_mutation(document_ref="doc_1", expected_revision="rev_2").revision == "rev_2"

    # doc_2 is still at rev_1
    assert cad_service.assert_fresh_for_mutation(document_ref="doc_2", expected_revision="rev_1").revision == "rev_1"
    with pytest.raises(FusionCadError):
        cad_service.assert_fresh_for_mutation(document_ref="doc_2", expected_revision="rev_2")


@pytest.mark.asyncio
async def test_falsify_transaction_baseline_bypass_and_staging_bounds(
    mock_desktop_service: DesktopNodeService,
):
    """Proves transaction begin persists baseline, and commit/preview/staging cannot bypass that baseline."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records([
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="revision.external_change_detection", state="supported"),
        ])
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_transaction_commit_primitive": lambda payload: setattr(fake_adsk, "tx_committed", True),
                "_transaction_preview_primitive": lambda payload: setattr(fake_adsk, "tx_previewed", True),
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

        # 1. Staging without transaction begin fails closed with INVALID_ARGUMENT
        with pytest.raises(FusionCadError) as exc_stage_unbegun:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "stage",
                    "transaction_id": "tx_unbegun",
                    "action": {
                        "action_type": "text_create",
                        "text": "Hello",
                        "height_mm": 5.0,
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
                    },
                },
                group="transaction",
            )
        assert exc_stage_unbegun.value.code == ErrorCode.INVALID_ARGUMENT
        assert "call transaction:begin first" in exc_stage_unbegun.value.message

        # 2. Begin transaction records baseline
        begin_res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "begin",
                "transaction_id": "tx_bypass_test",
            },
            group="transaction",
        )
        data = begin_res.data if isinstance(begin_res, CadResult) else begin_res.get("data", {})
        assert data.get("operation") == "begin"
        stored_bl = cad_service.revision_tracker.get_transaction_baseline("tx_bypass_test")
        assert stored_bl is not None
        assert stored_bl["baseline_revision"] == "rev_1"

        # 3. External change occurs in Fusion (volume 100.0 -> 250.0)
        fake_adsk.volume = 250.0

        # 4. Caller attempts commit on tx_bypass_test passing a newer expected_revision="rev_2"
        # Service overrides caller's expected_revision with stored baseline ("rev_1")
        # Authoritative Fusion-side guard detects divergence from stored baseline and rejects
        with pytest.raises(BridgeError) as exc_commit:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "commit",
                    "transaction_id": "tx_bypass_test",
                    "expected_revision": "rev_2",
                },
                group="transaction",
            )
        assert exc_commit.value.code == ErrorCode.REVISION_CONFLICT
        assert fake_adsk.tx_committed is False

        # 5. Caller attempts preview on tx_bypass_test passing expected_revision="rev_99"
        # Must still fail with REVISION_CONFLICT and not reach primitive
        with pytest.raises(BridgeError) as exc_prev:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "preview",
                    "transaction_id": "tx_bypass_test",
                    "expected_revision": "rev_99",
                },
                group="transaction",
            )
        assert exc_prev.value.code == ErrorCode.REVISION_CONFLICT
        assert fake_adsk.tx_previewed is False


@pytest.mark.asyncio
async def test_falsify_missing_required_fingerprint_groups_fail_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves that missing required mutation-sensitive semantic groups fail closed rather than silently omitting."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(primitive_reached=True),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

    # Seed tracker at rev_1
    cad_service.revision_tracker.observe("doc_1", "seed-fp")

    # Test each mandatory group being missing/corrupted in Fusion runtime
    for missing_group in ("timeline", "parameters", "components", "occurrences", "bodies", "sketches", "attributes"):
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
            import adsk.core
            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")

            if missing_group == "timeline":
                design.timeline = None
            elif missing_group == "parameters":
                design.allParameters = None
            elif missing_group == "components":
                design.allComponents = None
            elif missing_group == "occurrences":
                design.rootComponent.allOccurrences = None
            elif missing_group == "bodies":
                design.rootComponent.bRepBodies = None
            elif missing_group == "sketches":
                design.rootComponent.sketches = None
            elif missing_group == "attributes":
                doc.attributes = None

            with pytest.raises(FusionCadError) as exc_group:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "set",
                        "target": "ent_1",
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_group.value.code in (ErrorCode.CAPABILITY_UNAVAILABLE, ErrorCode.FUSION_API_ERROR)
            assert primitive_reached is False


@pytest.mark.asyncio
async def test_falsify_wrong_or_absent_document_identity_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves that requested document_ref mismatch and missing active document/design fail closed."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
        CapabilityRecord(name="revision.external_change_detection", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(primitive_reached=True),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    cad_service.revision_tracker.observe("doc_wrong", "seed-fp")

    # Case A: Requested document_ref="doc_wrong" does not match runtime document "doc_1"
    with AdskFakeContext("doc_1", initial_volume=100.0):
        with pytest.raises(FusionCadError) as exc_mismatch:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": "ent_1",
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                    "document_ref": "doc_wrong",
                },
                group="metadata",
            )
        assert exc_mismatch.value.code == ErrorCode.WRONG_DOCUMENT
        assert "does not match active document runtime identity" in exc_mismatch.value.message
        assert primitive_reached is False

    # Case B: No active document in Fusion runtime context; never synthesize identity from payload.document_ref
    with AdskFakeContext("doc_1", initial_volume=100.0):
        import adsk.core
        app = adsk.core.Application.get()
        app._doc = None  # No active document

        with pytest.raises(FusionCadError) as exc_no_doc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": "ent_1",
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                    "document_ref": "doc_1",
                },
                group="metadata",
            )
        assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN
        assert "Active document and design required" in exc_no_doc.value.message
        assert primitive_reached is False

    # Case C: Document lacks stable runtime identity (mutable name cannot be used)
    with AdskFakeContext("doc_1", initial_volume=100.0):
        import adsk.core
        app = adsk.core.Application.get()
        app.activeDocument.dataId = None  # Strip stable dataId/creationId/dataFile.id

        with pytest.raises(FusionCadError) as exc_no_id:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": "ent_1",
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                    "document_ref": "doc_1",
                },
                group="metadata",
            )
        assert exc_no_id.value.code == ErrorCode.NO_ACTIVE_DESIGN
        assert "Document lacks stable runtime identity" in exc_no_id.value.message
        assert primitive_reached is False

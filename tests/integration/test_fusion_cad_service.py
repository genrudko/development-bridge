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


@pytest.mark.asyncio
async def test_falsify_synthetic_mutation_fake_guards_against_external_change_no_apply(
    mock_desktop_service: DesktopNodeService,
):
    """Proves changed baseline triggers Fusion-side REVISION_CONFLICT, no apply, and advances tracker."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="metadata.attributes", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    # Initial state: Bridge knows doc_1 at rev_1 ("hash-baseline")
    cad_service.revision_tracker.observe("doc_1", "hash-baseline")
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"

    # Synthetic Fusion state: Model was modified externally in Fusion to "hash-diverged"
    fusion_model_state = {"current_fingerprint": "hash-diverged", "mutation_applied": False}

    async def fake_fusion_mcp_execute(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        line = next(l for l in arguments["script"].splitlines() if l.startswith("PAYLOAD_RAW = "))
        raw_json = json.loads(line.split("PAYLOAD_RAW = ", 1)[1])
        payload = json.loads(raw_json) if isinstance(raw_json, str) else raw_json

        expected_fp = payload.get("expected_fingerprint")
        expected_rev = payload.get("expected_revision")

        # Authoritative Fusion-side guard in same command execution
        if expected_fp is not None and expected_fp != fusion_model_state["current_fingerprint"]:
            # Baseline diverged! Reject mutation WITHOUT applying changes
            fusion_model_state["mutation_applied"] = False
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                "Authoritative Fusion-side guard: model fingerprint diverged from baseline",
                details={
                    "document_ref": "doc_1",
                    "expected_revision": expected_rev,
                    "expected_fingerprint": expected_fp,
                    "current_fingerprint": fusion_model_state["current_fingerprint"],
                    "applied": False,
                },
            )

        # Guard passed: apply mutation
        fusion_model_state["mutation_applied"] = True
        fusion_model_state["current_fingerprint"] = "hash-after-mutation"
        return {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "operation_id": "op_test_1",
            "summary": "Metadata set applied",
            "document": {
                "document_ref": "doc_1",
                "model_revision": "rev_3",
                "name": "Part1",
                "units": "mm",
            },
            "data": {
                "fingerprint": "hash-after-mutation",
                "applied": True,
            },
            "changed_refs": ["ent_1"],
        }

    mock_desktop_service.submit = fake_fusion_mcp_execute  # type: ignore[assignment]
    mock_desktop_service.call = fake_fusion_mcp_execute  # type: ignore[assignment]

    # Attempt mutation with expected_revision="rev_1"
    # Precheck passes (Bridge thought doc_1 was rev_1), but Fusion-side guard rejects!
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

    # 1. Authoritative error returned
    assert exc_guard.value.code == ErrorCode.REVISION_CONFLICT
    assert exc_guard.value.details.get("applied") is False
    # 2. Synthetic model proves mutation was NOT applied
    assert fusion_model_state["mutation_applied"] is False

    # 3. Bridge observed the new fingerprint ("hash-diverged") and advanced revision to rev_2!
    current_rec = cad_service.revision_tracker.current("doc_1")
    assert current_rec is not None
    assert current_rec.sequence == 2
    assert current_rec.revision == "rev_2"
    assert current_rec.fingerprint == "hash-diverged"

    # 4. Immediate second call with rev_1 now blocks at Bridge precheck!
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

    # 5. Mutation with fresh expected_revision="rev_2" succeeds
    success_result = await cad_service.execute(
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
    if isinstance(success_result, CadResult):
        assert success_result.status == "succeeded"
    else:
        assert success_result.get("status") == "succeeded"
    assert fusion_model_state["mutation_applied"] is True
    # Bridge tracker advanced to rev_3 after successful mutation
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
async def test_falsify_same_command_guard_no_apply_on_transaction_commit(
    mock_desktop_service: DesktopNodeService,
):
    """Proves transaction commit fails closed with REVISION_CONFLICT Fusion-side when baseline changed."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records([
        CapabilityRecord(name="transaction.preview_replay", state="supported"),
        CapabilityRecord(name="design.access", state="supported"),
    ])
    cad_service.set_node_capabilities("desk-1", matrix)

    cad_service.revision_tracker.observe("doc_1", "hash-baseline")
    fusion_state = {"current_fingerprint": "hash-external-user-edit", "committed": False}

    async def fake_tx_execute(node_id: str, tool_name: str, arguments: dict, journal: dict | None = None):
        line = next(l for l in arguments["script"].splitlines() if l.startswith("PAYLOAD_RAW = "))
        raw_json = json.loads(line.split("PAYLOAD_RAW = ", 1)[1])
        payload = json.loads(raw_json) if isinstance(raw_json, str) else raw_json

        expected_fp = payload.get("expected_fingerprint")
        if expected_fp is not None and expected_fp != fusion_state["current_fingerprint"]:
            fusion_state["committed"] = False
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                "Authoritative Fusion-side guard: transaction baseline diverged before commit",
                details={
                    "document_ref": "doc_1",
                    "expected_fingerprint": expected_fp,
                    "current_fingerprint": fusion_state["current_fingerprint"],
                    "applied": False,
                },
            )
        fusion_state["committed"] = True
        return {"api_version": "fusion.cad/v1", "status": "succeeded", "summary": "Transaction committed"}

    mock_desktop_service.submit = fake_tx_execute  # type: ignore[assignment]
    mock_desktop_service.call = fake_tx_execute  # type: ignore[assignment]

    with pytest.raises(BridgeError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_1234",
                "expected_revision": "rev_1",
            },
            group="transaction",
        )

    assert exc.value.code == ErrorCode.REVISION_CONFLICT
    assert exc.value.details.get("applied") is False
    assert fusion_state["committed"] is False
    # Proves tracker advanced
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"


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

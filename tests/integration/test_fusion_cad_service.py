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

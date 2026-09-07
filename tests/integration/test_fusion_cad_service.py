from __future__ import annotations

import json
import math
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
async def test_service_executes_capabilities_read_and_persists_matrix(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)

    records = [
        CapabilityRecord(
            name="design.access", state="supported", implementation="adsk.fusion.Design"
        ),
        CapabilityRecord(
            name="view.pick",
            state="degraded",
            implementation="native-preselect",
            limitations=("Visual pick requires live feasibility proof",),
        ),
        CapabilityRecord(
            name="export.dxf",
            state="unavailable",
            limitations=(
                "DXF export contract semantics not supported on this runtime; capability-gated until P2",
            ),
        ),
    ]
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
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
                            "capabilities": [
                                r.model_dump(mode="json") for r in records
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )

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
async def test_falsify_finding_1_unprobed_node_fails_closed_before_script_dispatch(
    mock_desktop_service: DesktopNodeService,
):
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
async def test_falsify_finding_1_read_capabilities_stays_ungated_on_unprobed_node(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)

    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Runtime capabilities probed",
                            "capabilities": [
                                {"name": "design.access", "state": "supported"},
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )

    # read:capabilities must NOT be gated and can probe unprobed node
    result = await cad_service.execute(
        {"node_id": "desk-new", "operation": "capabilities"},
        group="read",
    )
    assert isinstance(result, CadResult)
    assert mock_desktop_service.call.call_count == 1
    assert cad_service.get_node_capabilities("desk-new") is not None


@pytest.mark.asyncio
async def test_falsify_finding_1_no_cross_node_leakage(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)

    # Configure matrix ONLY for desk-1
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="entity.token_resolver", state="supported"),
            ]
        ),
    )

    # desk-2 has NOT been probed
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-2", "operation": "entity", "ref": "ent_1"},
            group="read",
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "desk-2" in exc_info.value.details.get("node_id")


@pytest.mark.asyncio
async def test_falsify_finding_1_cache_invalidation_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)

    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="entity.token_resolver", state="supported"),
            ]
        ),
    )
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

    degraded_matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(
                name="view.pick",
                state="degraded",
                implementation="viewport-raycast",
                limitations=("Visual pick requires live feasibility proof",),
            )
        ]
    )
    cad_service.set_node_capabilities("desk-1", degraded_matrix)

    # 1. Calling execute fails closed with CAPABILITY_DEGRADED
    with pytest.raises(BridgeError) as exc_info:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "pick",
                "view_ref": "view_1234",
                "x": 0.5,
                "y": 0.5,
            },
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


@pytest.mark.parametrize(
    "group, operation, payload, required_cap",
    [
        (
            "inspect",
            "describe",
            {"node_id": "desk-1", "operation": "describe", "target": "ent_1"},
            "inspect.measure",
        ),
        (
            "inspect",
            "distance",
            {
                "node_id": "desk-1",
                "operation": "distance",
                "target_a": "ent_1",
                "target_b": "ent_2",
            },
            "inspect.measure",
        ),
        (
            "view",
            "camera_set",
            {"node_id": "desk-1", "operation": "camera_set", "fov": 45.0},
            "view.camera",
        ),
        (
            "view",
            "pick",
            {
                "node_id": "desk-1",
                "operation": "pick",
                "view_ref": "view_1",
                "x": 0.5,
                "y": 0.5,
            },
            "view.pick",
        ),
        (
            "metadata",
            "set",
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": "ent_1",
                "name": "k",
                "value": "v",
            },
            "metadata.attributes",
        ),
        (
            "style",
            "text_create",
            {
                "node_id": "desk-1",
                "operation": "text_create",
                "text": "t",
                "height_mm": 5.0,
                "position": {"x": 0, "y": 0, "z": 0, "frame": {"space": "world"}},
            },
            "style.sketch_text",
        ),
        (
            "style",
            "show",
            {"node_id": "desk-1", "operation": "show", "target": "ent_1"},
            "design.access",
        ),
        (
            "read",
            "entity",
            {"node_id": "desk-1", "operation": "entity", "ref": "ent_1"},
            "entity.token_resolver",
        ),
        (
            "read",
            "feature_tree",
            {"node_id": "desk-1", "operation": "feature_tree"},
            "timeline.access",
        ),
        (
            "read",
            "sketch",
            {"node_id": "desk-1", "operation": "sketch", "ref": "ent_1"},
            "sketch.access",
        ),
        ("validate", "run", {"node_id": "desk-1", "operation": "run"}, "design.access"),
        (
            "transaction",
            "begin",
            {"node_id": "desk-1", "operation": "begin"},
            "transaction.preview_replay",
        ),
        (
            "transaction",
            "preview",
            {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_1"},
            "transaction.preview_replay",
        ),
    ],
)
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
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(
                name=required_cap,
                state="unavailable",
                limitations=(f"{required_cap} is unavailable",),
            )
        ]
    )
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
    settings = DesktopNodeSettings.model_validate(
        {
            "token": "test-token",
            "journal_path": str(tmp_path / "journal.jsonl"),
            "call_timeout_seconds": 1.0,
        }
    )
    return DesktopNodeService(settings)


@pytest.mark.asyncio
async def test_falsify_same_node_reconnect_invalidates_capabilities_real_service(
    real_desktop_service: DesktopNodeService,
):
    # 1. Register desk-1
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    assert real_desktop_service.get_session_generation("desk-1") == 1

    cad_service = FusionCadService(real_desktop_service)

    # 2. Set capability matrix for desk-1
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(
                name="design.access",
                state="supported",
                implementation="adsk.fusion.Design",
            ),
            CapabilityRecord(
                name="entity.token_resolver",
                state="supported",
                implementation="adsk.fusion.Design.findEntityByToken",
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)
    assert cad_service.get_node_capabilities("desk-1") is not None

    # 3. Same-node reconnect: register() is called again for desk-1
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
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
    real_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Runtime capabilities probed",
                            "capabilities": [
                                {
                                    "name": "design.access",
                                    "state": "supported",
                                    "implementation": "adsk.fusion.Design",
                                },
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    assert isinstance(res, CadResult)

    # Now re-probed capabilities are cached with generation 2
    assert cad_service.get_node_capabilities("desk-1") is not None
    assert (
        cad_service.get_node_capabilities("desk-1").get("design.access").state
        == "supported"
    )


@pytest.mark.asyncio
async def test_falsify_tool_change_invalidates_capabilities_real_service(
    real_desktop_service: DesktopNodeService,
):
    # 1. Register desk-1
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    cad_service = FusionCadService(real_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
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
async def test_falsify_runtime_change_invalidates_capabilities_real_service(
    real_desktop_service: DesktopNodeService,
):
    # 1. Register desk-1 with fusion_available=True
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    cad_service = FusionCadService(real_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
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
async def test_falsify_cross_node_isolation_during_reconnect_real_service(
    real_desktop_service: DesktopNodeService,
):
    # 1. Register desk-1 and desk-2
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    await real_desktop_service.register(
        "desk-2", [{"name": "fusion_mcp_execute"}], True
    )

    cad_service = FusionCadService(real_desktop_service)
    matrix1 = CapabilityMatrix.from_records(
        [CapabilityRecord(name="design.access", state="supported")]
    )
    matrix2 = CapabilityMatrix.from_records(
        [CapabilityRecord(name="design.access", state="supported")]
    )
    cad_service.set_node_capabilities("desk-1", matrix1)
    cad_service.set_node_capabilities("desk-2", matrix2)

    assert cad_service.get_node_capabilities("desk-1") is not None
    assert cad_service.get_node_capabilities("desk-2") is not None

    # 2. desk-1 reconnects
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )

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
    real_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Executed model_snapshot",
                            "data": {"components": []},
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    res2 = await cad_service.execute(
        {"node_id": "desk-2", "operation": "model_snapshot"},
        group="read",
    )
    assert isinstance(res2, CadResult)
    assert res2.status == "succeeded"


@pytest.mark.asyncio
async def test_falsify_in_flight_capability_probe_race_re_registration(
    real_desktop_service: DesktopNodeService,
):
    """Proves that if a node re-registers while read:capabilities is in-flight,
    the old probe result is discarded, capabilities remain unprobed, and subsequent
    gated operations fail closed with CAPABILITY_UNAVAILABLE.
    """
    # 1. Register desk-1 (generation 1)
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    assert real_desktop_service.get_session_generation("desk-1") == 1

    cad_service = FusionCadService(real_desktop_service)

    # 2. Simulate in-flight race: during the probe dispatch call, desk-1 re-registers
    orig_call = real_desktop_service.call

    async def call_with_race(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        # Trigger re-registration mid-probe -> bumps session_generation to 2
        await real_desktop_service.register(
            "desk-1", [{"name": "fusion_mcp_execute"}], True
        )
        assert real_desktop_service.get_session_generation("desk-1") == 2
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Probed during race",
                            "capabilities": [
                                {
                                    "name": "design.access",
                                    "state": "supported",
                                    "implementation": "adsk.fusion.Design",
                                },
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }

    real_desktop_service.call = call_with_race  # type: ignore[assignment]

    # 3. Dispatch read:capabilities
    res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
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
    real_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Probed clean",
                            "capabilities": [
                                {
                                    "name": "design.access",
                                    "state": "supported",
                                    "implementation": "adsk.fusion.Design",
                                },
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    assert cad_service.get_node_capabilities("desk-1") is not None
    assert (
        cad_service.get_node_capabilities("desk-1").get("design.access").state
        == "supported"
    )


@pytest.mark.asyncio
async def test_falsify_in_flight_capability_probe_race_cross_node_isolation(
    real_desktop_service: DesktopNodeService,
):
    """Proves in-flight race on desk-1 leaves desk-1 unprobed without affecting desk-2."""
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    await real_desktop_service.register(
        "desk-2", [{"name": "fusion_mcp_execute"}], True
    )

    cad_service = FusionCadService(real_desktop_service)
    # desk-2 has valid cached capabilities
    matrix2 = CapabilityMatrix.from_records(
        [CapabilityRecord(name="design.access", state="supported")]
    )
    cad_service.set_node_capabilities("desk-2", matrix2)
    assert cad_service.get_node_capabilities("desk-2") is not None

    # In-flight race occurs on desk-1
    async def call_race_desk1(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        if node_id == "desk-1":
            # Tool change on desk-1 -> bumps generation
            await real_desktop_service.heartbeat(
                "desk-1", tools=[{"name": "fusion_mcp_execute"}, {"name": "aux"}]
            )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Probed during race",
                            "capabilities": [
                                {
                                    "name": "design.access",
                                    "state": "supported",
                                    "implementation": "adsk.fusion.Design",
                                },
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }

    real_desktop_service.call = call_race_desk1  # type: ignore[assignment]
    await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )

    # desk-1 discarded, desk-2 unaffected
    assert cad_service.get_node_capabilities("desk-1") is None
    assert cad_service.get_node_capabilities("desk-2") is not None


# =========================================================================
# Task 4: Model revision tracking, Bridge precheck, and Fusion-side guard
# =========================================================================


@pytest.mark.asyncio
async def test_service_assert_fresh_for_mutation_interface(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.revision_tracker.observe("doc_1", "hash-v1")

    # 1. Matching expected_revision via dict payload succeeds
    rec1 = cad_service.assert_fresh_for_mutation(
        {"document_ref": "doc_1", "expected_revision": "rev_1"}
    )
    assert rec1.revision == "rev_1"

    # 2. Matching expected_revision via explicit arguments succeeds
    rec2 = cad_service.assert_fresh_for_mutation(
        document_ref="doc_1", expected_revision="rev_1"
    )
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
        cad_service.assert_fresh_for_mutation({"document_ref": "doc_1"})
    assert exc_none.value.code == ErrorCode.REVISION_CONFLICT


@pytest.mark.asyncio
async def test_falsify_stale_expected_revision_blocks_at_bridge_precheck(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
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
        self.missing_witness = False

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
            def __init__(self, ctx_or_items=None):
                if hasattr(ctx_or_items, "attributes"):
                    self._items = ctx_or_items.attributes
                elif isinstance(ctx_or_items, list):
                    self._items = ctx_or_items
                else:
                    self._items = []

            @property
            def count(self):
                return len(self._items)

            def item(self, idx):
                return self._items[idx]

            def add(self, group_name, name, value):
                class Attr:
                    def __init__(self, g, n, v):
                        self.groupName = g
                        self.name = n
                        self.value = v

                attr = Attr(group_name, name, value)
                self._items.append(attr)
                return attr

        class FakeTransform:
            def __init__(self, matrix=None):
                self._matrix = list(
                    matrix
                    or [
                        1.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        1.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        1.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        1.0,
                    ]
                )

            def asArray(self):
                return list(self._matrix)

        class FakeOccurrence:
            def __init__(self, name="Occ1"):
                self.name = name
                self.entityToken = f"occ_token_{name}"
                self.fullPathName = f"Root+{name}"
                self.isVisible = True
                self.isLightBulbOn = True
                self.transform = FakeTransform()
                self.attributes = FakeAttributes()

        class FakeVertex:
            def __init__(self, x=0.0, y=0.0, z=0.0):
                self.geometry = FakePoint(x, y, z)

        class FakeLoop:
            def __init__(self, is_outer=True, edge_count=4, edge_lengths=None):
                self.isOuter = is_outer
                lengths = edge_lengths if edge_lengths is not None else [10.0] * edge_count
                self.edges = FakeCollection(
                    [FakeEdge(idx=i, length=lengths[i]) for i in range(edge_count)]
                )

        class FakeFace:
            def __init__(self, idx=0, area=10.0, centroid=None, body=None):
                self.entityToken = f"face_token_{idx}"
                self.area = area
                self.centroid = centroid or FakePoint(5.0, 5.0, 5.0)
                self.body = body
                self.geometry = type(
                    "FaceGeom",
                    (),
                    {
                        "objectType": "PlaneSurface",
                        "surfaceType": "PlaneSurface",
                        "origin": FakePoint(0.0, 0.0, 0.0),
                        "normal": FakePoint(0.0, 0.0, 1.0),
                    },
                )()
                self.loops = FakeCollection(
                    [
                        FakeLoop(
                            is_outer=True,
                            edge_count=4,
                            edge_lengths=[10.0, 10.0, 10.0, 10.0],
                        )
                    ]
                )
                self.edges = FakeCollection(
                    [FakeEdge(idx=idx * 4 + j, length=10.0) for j in range(4)]
                )
                self.vertices = FakeCollection(
                    [
                        FakeVertex(0.0, 0.0, 0.0),
                        FakeVertex(10.0, 0.0, 0.0),
                        FakeVertex(10.0, 10.0, 0.0),
                        FakeVertex(0.0, 10.0, 0.0),
                    ]
                )
                self.isParamReversed = False
                self.boundingBox = FakeBoundingBox(
                    FakePoint(0, 0, 0), FakePoint(10, 10, 0)
                )
                self.attributes = FakeAttributes()

        class FakeEdge:
            def __init__(self, idx=0, length=10.0):
                self.entityToken = f"edge_token_{idx}"
                self.length = length
                self.geometry = type(
                    "EdgeGeom",
                    (),
                    {
                        "objectType": "Line3D",
                        "curveType": "Line3D",
                        "isClosed": False,
                        "startPoint": FakePoint(0, 0, 0),
                        "endPoint": FakePoint(length, 0, 0),
                    },
                )()
                self.faces = FakeCollection([object(), object()])
                self.startVertex = FakeVertex(0, 0, 0)
                self.endVertex = FakeVertex(length, 0, 0)
                self.isDegenerate = False
                self.isParamReversed = False
                self.boundingBox = FakeBoundingBox(
                    FakePoint(0, 0, 0), FakePoint(length, 0, 0)
                )
                self.attributes = FakeAttributes()

        class FakePhysicalProperties:
            def __init__(self, com=None):
                self.centerOfMass = com or FakePoint(5.0, 5.0, 5.0)

        class FakeBody:
            def __init__(self, ctx):
                self._ctx = ctx
                self.name = "Body1"
                self.entityToken = "body_token_1"
                self.isSolid = True
                self.isVisible = True
                self.isLightBulbOn = True
                self.area = 50.0
                self.faces = FakeCollection(
                    [
                        FakeFace(idx=i, area=10.0, centroid=FakePoint(i, i, i))
                        for i in range(6)
                    ]
                )
                for _fi in range(self.faces.count):
                    self.faces.item(_fi).body = self
                self.edges = FakeCollection(
                    [FakeEdge(idx=i, length=10.0) for i in range(12)]
                )
                self.vertices = FakeCollection(
                    [FakeVertex(x=i, y=i, z=i) for i in range(8)]
                )
                self.boundingBox = FakeBoundingBox(
                    FakePoint(0, 0, 0), FakePoint(10, 10, 10)
                )
                self.physicalProperties = FakePhysicalProperties(
                    FakePoint(5.0, 5.0, 5.0)
                )
                self.attributes = FakeAttributes()

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

        class FakeSketchCurve:
            def __init__(self, idx=0, length=10.0, sp=(0, 0, 0), ep=(10, 0, 0)):
                self.entityToken = f"curve_token_{idx}"
                self.length = length
                self.objectType = "SketchLine"
                self.geometry = type(
                    "CurveGeom",
                    (),
                    {
                        "objectType": "Line3D",
                        "startPoint": FakePoint(*sp),
                        "endPoint": FakePoint(*ep),
                    },
                )()
                self.boundingBox = FakeBoundingBox(FakePoint(*sp), FakePoint(*ep))
                self.startSketchPoint = FakeSketchPoint(idx * 2, *sp)
                self.endSketchPoint = FakeSketchPoint(idx * 2 + 1, *ep)
                self.isConstruction = False
                self.isFixed = False
                self.attributes = FakeAttributes()

        class FakeSketchPoint:
            def __init__(self, idx=0, x=0.0, y=0.0, z=0.0):
                self.entityToken = f"point_token_{idx}"
                self.geometry = FakePoint(x, y, z)
                self.attributes = FakeAttributes()

        class FakeSketch:
            def __init__(self):
                self.name = "Sketch1"
                self.entityToken = "sketch_token_1"
                self.isVisible = True
                self.isLightBulbOn = True
                self.profiles = FakeCollection([object()])
                self.sketchCurves = FakeCollection(
                    [
                        FakeSketchCurve(0, 10.0, (0, 0, 0), (10, 0, 0)),
                        FakeSketchCurve(1, 10.0, (10, 0, 0), (10, 10, 0)),
                        FakeSketchCurve(2, 10.0, (10, 10, 0), (0, 10, 0)),
                        FakeSketchCurve(3, 10.0, (0, 10, 0), (0, 0, 0)),
                    ]
                )
                self.sketchPoints = FakeCollection(
                    [
                        FakeSketchPoint(0, 0, 0, 0),
                        FakeSketchPoint(1, 10, 0, 0),
                        FakeSketchPoint(2, 10, 10, 0),
                        FakeSketchPoint(3, 0, 10, 0),
                    ]
                )
                self.boundingBox = FakeBoundingBox(
                    FakePoint(0, 0, 0), FakePoint(10, 10, 0)
                )
                self.geometricConstraints = FakeCollection([FakeConstraint()])
                self.sketchDimensions = FakeCollection([FakeDimension()])
                self.attributes = FakeAttributes()

        class FakeComponent:
            def __init__(self, ctx):
                self._ctx = ctx
                self.name = "Root"
                self.id = "comp_root"
                self.entityToken = "comp_token_root"
                self.bRepBodies = FakeCollection([FakeBody(ctx)])
                self.sketches = FakeCollection([FakeSketch()])
                self.allOccurrences = FakeCollection([])
                self.attributes = FakeAttributes()

        class FakeFeature:
            def __init__(self, token="feat_extrude_1", name="Extrude1"):
                self.entityToken = token
                self.name = name
                self.attributes = FakeAttributes()

        class FakeTimelineItem:
            def __init__(self):
                self.index = 0
                self.entityToken = "feat_extrude_1"
                self.name = "Extrude1"
                self.isSuppressed = False
                self.isValid = True
                self.isRolledBack = False
                self.healthStatus = "ok"
                self.attributes = FakeAttributes()
                self.entity = FakeFeature()

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
                self._token_map = {}
                self._register_entities(self.rootComponent)

            def _register_entities(self, root):
                self._token_map[root.entityToken] = root
                body = root.bRepBodies.item(0)
                self._token_map[body.entityToken] = body
                for i in range(body.faces.count):
                    f = body.faces.item(i)
                    self._token_map[f.entityToken] = f
                for i in range(body.edges.count):
                    e = body.edges.item(i)
                    self._token_map[e.entityToken] = e
                for i in range(root.sketches.count):
                    s = root.sketches.item(i)
                    self._token_map[s.entityToken] = s
                    for j in range(s.sketchCurves.count):
                        cv = s.sketchCurves.item(j)
                        self._token_map[cv.entityToken] = cv
                    for j in range(s.sketchPoints.count):
                        pt = s.sketchPoints.item(j)
                        self._token_map[pt.entityToken] = pt

            def findEntityByToken(self, token):
                return self._token_map.get(token)

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

        class FakeMeasureResult:
            def __init__(self, value, p1=None, p2=None):
                self.value = value
                self.pointOne = p1
                self.pointTwo = p2

        class FakeMeasureManager:
            def __init__(self, ctx):
                self._ctx = ctx

            def _centroid(self, entity):
                if hasattr(entity, "centroid") and entity.centroid is not None:
                    return entity.centroid
                if (
                    hasattr(entity, "physicalProperties")
                    and entity.physicalProperties is not None
                ):
                    return entity.physicalProperties.centerOfMass
                if hasattr(entity, "boundingBox") and entity.boundingBox is not None:
                    bb = entity.boundingBox
                    return FakePoint(
                        (bb.minPoint.x + bb.maxPoint.x) / 2.0,
                        (bb.minPoint.y + bb.maxPoint.y) / 2.0,
                        (bb.minPoint.z + bb.maxPoint.z) / 2.0,
                    )
                return FakePoint(0.0, 0.0, 0.0)

            def _dist(self, a, b):
                return math.sqrt(
                    (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2
                )

            def measureDistance(self, e1, e2):
                p1 = self._centroid(e1)
                p2 = self._centroid(e2)
                if getattr(self._ctx, "missing_witness", False):
                    return FakeMeasureResult(self._dist(p1, p2), None, None)
                return FakeMeasureResult(self._dist(p1, p2), p1, p2)

            def measureMinimumDistance(self, e1, e2):
                return self.measureDistance(e1, e2)

        class FakeApplication:
            def __init__(self, ctx):
                self._doc = FakeDocument(ctx)
                self.measureManager = FakeMeasureManager(ctx)

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
        matrix = CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="metadata.attributes", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        )
        cad_service.set_node_capabilities("desk-1", matrix)
        body_ref = cad_service.ref_registry.issue(
            document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
        ).ref

        # Execute rendered script directly inside desktop node submit/call
        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_mutation_primitive": lambda payload: setattr(
                    fake_adsk, "mutated", True
                ),
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

        # 1. Initial snapshot read: exercises production read script and seeds Bridge tracker with baseline
        snap_res = await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
        )
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
                    "target": body_ref,
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
                    "target": body_ref,
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
                "target": body_ref,
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
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
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
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )

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
        matrix = CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        )
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_transaction_commit_primitive": lambda payload: (
                    setattr(fake_adsk, "tx_committed", True),
                    setattr(fake_adsk, "volume", float(fake_adsk.volume) + 50.0),
                ),
                "_transaction_preview_primitive": lambda payload: setattr(
                    fake_adsk, "tx_previewed", True
                ),
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

        # 1. Initial read seeds Bridge tracker
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
        )
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
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
        )
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_3"

        # 7. Abort on stale diverged transaction fails with REVISION_CONFLICT and preserves baseline
        with pytest.raises(BridgeError) as exc_abort:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "abort",
                    "transaction_id": "tx_1234",
                },
                group="transaction",
            )
        assert exc_abort.value.code == ErrorCode.REVISION_CONFLICT
        assert (
            cad_service.revision_tracker.get_transaction_baseline("tx_1234") is not None
        )

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
        data = (
            res_preview.data
            if isinstance(res_preview, CadResult)
            else res_preview.get("data", {})
        )
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
        commit_data = (
            res_commit.data
            if isinstance(res_commit, CadResult)
            else res_commit.get("data", {})
        )
        assert commit_data.get("applied") is True
        assert fake_adsk.tx_committed is True
        assert cad_service.revision_tracker.get_transaction_baseline("tx_fresh") is None


@pytest.mark.asyncio
async def test_falsify_missing_expected_revision_rejected_before_dispatch(
    mock_desktop_service: DesktopNodeService,
):
    """Proves standalone mutation requires expected_revision and rejects before script generation/dispatch."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
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
    matrix_degraded = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection",
                state="degraded",
                limitations=["Unverified"],
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix_degraded)
    cad_service.revision_tracker.observe("doc_1", "hash-1")

    # 1. Standalone mutation blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_mut:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": "ent_1",
                "name": "t",
                "value": "v",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_mut.value.code == ErrorCode.CAPABILITY_DEGRADED

    # 2. Transaction preview blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_prev:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "preview",
                "transaction_id": "tx_1",
                "expected_revision": "rev_1",
            },
            group="transaction",
        )
    assert exc_prev.value.code == ErrorCode.CAPABILITY_DEGRADED

    # 3. Transaction commit blocks with CAPABILITY_DEGRADED
    with pytest.raises(FusionCadError) as exc_comm:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_1",
                "expected_revision": "rev_1",
            },
            group="transaction",
        )
    assert exc_comm.value.code == ErrorCode.CAPABILITY_DEGRADED

    # Case B: Unavailable revision capability
    matrix_unavail = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection",
                state="unavailable",
                limitations=["Not supported"],
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix_unavail)

    with pytest.raises(FusionCadError) as exc_unavail:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": "ent_1",
                "name": "t",
                "value": "v",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_unavail.value.code == ErrorCode.CAPABILITY_UNAVAILABLE

    # Transaction staging does NOT require revision.external_change_detection
    cad_service.revision_tracker.begin_transaction("tx_1", "doc_1")
    mock_desktop_service.submit = AsyncMock(
        return_value={"status": "queued", "operation_id": "op_stage"}
    )
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

    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Runtime capabilities probed",
                            "capabilities": [
                                {
                                    "name": "revision.external_change_detection",
                                    "state": "degraded",
                                    "implementation": "timeline-fingerprint-guard",
                                    "limitations": [
                                        "Fusion-side revision freshness guard and external-change atomicity not guaranteed at contract level; unverified without active runtime atomicity proof"
                                    ],
                                },
                                {
                                    "name": "view.pick",
                                    "state": "degraded",
                                    "implementation": "native-preselect",
                                    "limitations": [
                                        "Visual pick requires live feasibility proof"
                                    ],
                                },
                                {
                                    "name": "transaction.preview_replay",
                                    "state": "degraded",
                                    "implementation": "manual-replay",
                                    "limitations": [
                                        "Transaction preview replay requires live feasibility proof"
                                    ],
                                },
                                {
                                    "name": "export.dxf",
                                    "state": "unavailable",
                                    "limitations": [
                                        "DXF export contract semantics not supported on this runtime; capability-gated until P2"
                                    ],
                                },
                                {
                                    "name": "view.section",
                                    "state": "unavailable",
                                    "limitations": [
                                        "Section view analysis contract semantics not available on this runtime; capability-gated until P2"
                                    ],
                                },
                                {
                                    "name": "assembly.joints",
                                    "state": "unavailable",
                                    "limitations": [
                                        "Assembly joint operations not supported on this runtime; capability-gated until P2"
                                    ],
                                },
                            ],
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
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
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # Read doc_1
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Read doc_1",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                                "name": "Doc1",
                                "units": "mm",
                            },
                            "data": {"fingerprint": "hash-doc-1-v1"},
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
    )

    # Read doc_2
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Read doc_2",
                            "document": {
                                "document_ref": "doc_2",
                                "model_revision": "rev_1",
                                "name": "Doc2",
                                "units": "mm",
                            },
                            "data": {"fingerprint": "hash-doc-2-v1"},
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
    )

    # Assert both documents tracked independently at rev_1
    assert (
        cad_service.assert_fresh_for_mutation(
            document_ref="doc_1", expected_revision="rev_1"
        ).revision
        == "rev_1"
    )
    assert (
        cad_service.assert_fresh_for_mutation(
            document_ref="doc_2", expected_revision="rev_1"
        ).revision
        == "rev_1"
    )

    # External change advances doc_1 to rev_2
    cad_service.revision_tracker.observe("doc_1", "hash-doc-1-v2")
    assert (
        cad_service.assert_fresh_for_mutation(
            document_ref="doc_1", expected_revision="rev_2"
        ).revision
        == "rev_2"
    )

    # doc_2 is still at rev_1
    assert (
        cad_service.assert_fresh_for_mutation(
            document_ref="doc_2", expected_revision="rev_1"
        ).revision
        == "rev_1"
    )
    with pytest.raises(FusionCadError):
        cad_service.assert_fresh_for_mutation(
            document_ref="doc_2", expected_revision="rev_2"
        )


@pytest.mark.asyncio
async def test_falsify_transaction_baseline_bypass_and_staging_bounds(
    mock_desktop_service: DesktopNodeService,
):
    """Proves transaction begin persists baseline, and commit/preview/staging cannot bypass that baseline."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        )
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_transaction_commit_primitive": lambda payload: (
                    setattr(fake_adsk, "tx_committed", True),
                    setattr(fake_adsk, "volume", float(fake_adsk.volume) + 50.0),
                ),
                "_transaction_preview_primitive": lambda payload: setattr(
                    fake_adsk, "tx_previewed", True
                ),
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
                        "position": {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                            "frame": {"space": "world"},
                        },
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
        data = (
            begin_res.data
            if isinstance(begin_res, CadResult)
            else begin_res.get("data", {})
        )
        assert data.get("operation") == "begin"
        stored_bl = cad_service.revision_tracker.get_transaction_baseline(
            "tx_bypass_test"
        )
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
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

    # Seed tracker at rev_1
    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref

    # Test each mandatory group being missing/corrupted in Fusion runtime
    for missing_group in (
        "timeline",
        "parameters",
        "components",
        "occurrences",
        "bodies",
        "sketches",
        "attributes",
    ):
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0):
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
                        "target": body_ref,
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_group.value.code in (
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.FUSION_API_ERROR,
            )
            assert primitive_reached is False


@pytest.mark.asyncio
async def test_falsify_wrong_or_absent_document_identity_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves that requested document_ref mismatch and missing active document/design fail closed."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]

    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    cad_service.revision_tracker.observe("doc_wrong", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref
    wrong_doc_ref = cad_service.ref_registry.issue(
        document_ref="doc_wrong",
        kind="body",
        name="Body1",
        native_token="wrong_doc_body_token",
    ).ref

    # Case A: Requested document_ref="doc_wrong" does not match runtime document "doc_1"
    with AdskFakeContext("doc_1", initial_volume=100.0):
        with pytest.raises(FusionCadError) as exc_mismatch:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": wrong_doc_ref,
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                    "document_ref": "doc_wrong",
                },
                group="metadata",
            )
        assert exc_mismatch.value.code == ErrorCode.WRONG_DOCUMENT
        assert (
            "does not match active document runtime identity"
            in exc_mismatch.value.message
        )
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
                    "target": body_ref,
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
                    "target": body_ref,
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


@pytest.mark.asyncio
async def test_falsify_async_transaction_lifecycle_queued_failed_and_succeeded(
    mock_desktop_service: DesktopNodeService,
):
    """Proves async transaction authority is never changed on queued or failed/uncertain states, only proven terminal success."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Async transaction:begin queued acknowledgment returns status: queued truthfully
    # and MUST NOT manufacture authoritative baseline in RevisionTracker
    mock_desktop_service.submit = AsyncMock(
        return_value={"operation_id": "op_async_begin", "status": "queued"}
    )
    sub_res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "begin",
            "transaction_id": "tx_async_1",
            "document_ref": "doc_1",
        },
        group="transaction",
    )
    assert sub_res == {"operation_id": "op_async_begin", "status": "queued"}
    # Tracker must NOT have any baseline for tx_async_1
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is None

    # 2. Terminal failed or uncertain begin does NOT manufacture transaction state
    op_status_fail = {
        "operation_id": "op_async_begin",
        "node_id": "desk-1",
        "status": "failed",
        "summary": "transaction:begin",
        "checkpoint": {
            "operation": "begin",
            "group": "transaction",
            "transaction_id": "tx_async_1",
            "document_ref": "doc_1",
        },
    }
    with pytest.raises(FusionCadError) as exc_fail:
        cad_service.finalize_terminal_operation(
            op_status_fail,
            {
                "status": "failed",
                "error": {
                    "code": "FUSION_API_ERROR",
                    "message": "Fusion script failed",
                },
            },
        )
    assert exc_fail.value.code == ErrorCode.FUSION_API_ERROR
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is None

    # Uncertain state
    op_status_unc = {
        "operation_id": "op_async_begin",
        "node_id": "desk-1",
        "status": "uncertain",
        "summary": "transaction:begin",
        "checkpoint": {
            "operation": "begin",
            "group": "transaction",
            "transaction_id": "tx_async_1",
            "document_ref": "doc_1",
        },
    }
    with pytest.raises(FusionCadError):
        cad_service.finalize_terminal_operation(op_status_unc, {"status": "uncertain"})
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is None

    # 3. Terminal succeeded begin with empty fingerprint fails closed and does NOT establish baseline
    op_status_succ = {
        "operation_id": "op_async_begin",
        "node_id": "desk-1",
        "status": "succeeded",
        "summary": "transaction:begin",
        "checkpoint": {
            "operation": "begin",
            "group": "transaction",
            "transaction_id": "tx_async_1",
            "document_ref": "doc_1",
        },
    }
    with pytest.raises(FusionCadError) as exc_empty_fp:
        cad_service.finalize_terminal_operation(
            op_status_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction begin completed",
                "data": {
                    "operation": "begin",
                    "applied": True,
                    "fingerprint": "",
                    "transaction_id": "tx_async_1",
                },
                "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            },
        )
    assert exc_empty_fp.value.code == ErrorCode.FUSION_API_ERROR
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is None

    # 4. Proven terminal succeeded begin with valid fingerprint persists authoritative baseline
    cad_service.finalize_terminal_operation(
        op_status_succ,
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Transaction begin completed",
            "data": {
                "operation": "begin",
                "applied": True,
                "fingerprint": "proven_fp_123",
                "transaction_id": "tx_async_1",
            },
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
        },
    )
    stored = cad_service.revision_tracker.get_transaction_baseline("tx_async_1")
    assert stored is not None
    assert stored["baseline_revision"] == "rev_1"
    assert stored["baseline_fingerprint"] == "proven_fp_123"

    # 5. Async commit queued acknowledgment MUST NOT clear stored baseline
    mock_desktop_service.submit = AsyncMock(
        return_value={"operation_id": "op_async_commit", "status": "queued"}
    )
    comm_sub_res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "commit",
            "transaction_id": "tx_async_1",
        },
        group="transaction",
    )
    assert comm_sub_res == {"operation_id": "op_async_commit", "status": "queued"}
    # Stored baseline must STILL exist
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 6. Failed or uncertain commit MUST NOT clear stored baseline
    op_status_comm_fail = {
        "operation_id": "op_async_commit",
        "node_id": "desk-1",
        "status": "failed",
        "summary": "transaction:commit",
        "checkpoint": {
            "operation": "commit",
            "group": "transaction",
            "transaction_id": "tx_async_1",
        },
    }
    with pytest.raises(FusionCadError):
        cad_service.finalize_terminal_operation(
            op_status_comm_fail,
            {"status": "failed", "error": {"code": "FUSION_API_ERROR"}},
        )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7. Commit success verification:
    # 7a. Lacking stable runtime document identity MUST NOT clear stored baseline
    op_status_comm_succ = {
        "operation_id": "op_async_commit",
        "node_id": "desk-1",
        "status": "succeeded",
        "summary": "Transaction commit completed",
        "checkpoint": {
            "operation": "commit",
            "group": "transaction",
            "transaction_id": "tx_async_1",
        },
    }
    with pytest.raises(FusionCadError) as exc_no_doc:
        cad_service.finalize_terminal_operation(
            op_status_comm_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction commit completed",
                "document": None,
                "data": {
                    "operation": "commit",
                    "applied": True,
                    "transaction_id": "tx_async_1",
                    "fingerprint": "proven_post_fp_456",
                },
            },
        )
    assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7b. Wrong document identity MUST NOT clear stored baseline
    with pytest.raises(FusionCadError) as exc_wrong_doc:
        cad_service.finalize_terminal_operation(
            op_status_comm_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction commit completed",
                "document": {"document_ref": "doc_other", "model_revision": "rev_1"},
                "data": {
                    "operation": "commit",
                    "applied": True,
                    "transaction_id": "tx_async_1",
                    "fingerprint": "proven_post_fp_456",
                },
            },
        )
    assert exc_wrong_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7b2. Diverged document identity between document state and payload data MUST NOT clear stored baseline
    with pytest.raises(FusionCadError) as exc_diverged_doc:
        cad_service.finalize_terminal_operation(
            op_status_comm_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction commit completed",
                "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
                "data": {
                    "operation": "commit",
                    "applied": True,
                    "transaction_id": "tx_async_1",
                    "document_ref": "doc_diverged",
                    "fingerprint": "proven_post_fp_456",
                },
            },
        )
    assert exc_diverged_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7c. Missing or empty authoritative fingerprint MUST NOT clear stored baseline
    with pytest.raises(FusionCadError) as exc_no_fp:
        cad_service.finalize_terminal_operation(
            op_status_comm_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction commit completed",
                "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
                "data": {
                    "operation": "commit",
                    "applied": True,
                    "transaction_id": "tx_async_1",
                    "fingerprint": "   ",
                },
            },
        )
    assert exc_no_fp.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7d. Succeeded commit lacking doc identity and fingerprint (the old buggy payload) MUST NOT clear stored baseline
    with pytest.raises(FusionCadError):
        cad_service.finalize_terminal_operation(
            op_status_comm_succ,
            {
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "Transaction commit completed",
                "data": {
                    "operation": "commit",
                    "applied": True,
                    "transaction_id": "tx_async_1",
                },
            },
        )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    )

    # 7e. Proven terminal succeeded commit with matching document and real fingerprint clears stored baseline and advances revision
    cad_service.finalize_terminal_operation(
        op_status_comm_succ,
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Transaction commit completed",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {
                "operation": "commit",
                "applied": True,
                "transaction_id": "tx_async_1",
                "fingerprint": "proven_post_fp_456",
            },
        },
    )
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is None
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"
    assert (
        cad_service.revision_tracker.current("doc_1").fingerprint
        == "proven_post_fp_456"
    )


@pytest.mark.asyncio
async def test_falsify_transaction_preview_and_commit_bound_to_begin_baseline_and_wrong_doc_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves preview and commit stay bound to stored begin baseline, ignoring caller freshness values, and wrong document fails closed."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    cad_service.revision_tracker.observe("doc_1", "seed_fp_1")
    cad_service.revision_tracker.begin_transaction(
        "tx_bound", "doc_1", "rev_1", "seed_fp_1"
    )

    captured_payload = None

    async def capture_submit(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal captured_payload
        import json

        script = arguments["script"]
        # extract PAYLOAD_RAW
        for line in script.splitlines():
            if line.startswith("PAYLOAD_RAW = "):
                raw_json = line[len("PAYLOAD_RAW = ") :]
                captured_payload = json.loads(
                    json.loads(raw_json) if raw_json.startswith('"') else raw_json
                )
                break
        return {"operation_id": "op_bound", "status": "queued"}

    mock_desktop_service.submit = capture_submit  # type: ignore[assignment]

    # 1. Caller attempts to pass forged expected_revision="rev_999"
    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "preview",
            "transaction_id": "tx_bound",
            "expected_revision": "rev_999",
        },
        group="transaction",
    )
    assert captured_payload is not None
    # Script payload MUST be bound to stored begin baseline, NOT caller-selected values
    assert captured_payload["expected_revision"] == "rev_1"
    assert captured_payload["expected_fingerprint"] == "seed_fp_1"
    assert captured_payload["document_ref"] == "doc_1"

    # 2. Caller attempts to target a different document with tx_bound: fails closed with WRONG_DOCUMENT
    with pytest.raises(FusionCadError) as exc_wrong_doc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_bound",
                "document_ref": "doc_other",
            },
            group="transaction",
        )
    assert exc_wrong_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert (
        "does not match active document runtime identity"
        in exc_wrong_doc.value.message
    )


@pytest.mark.asyncio
async def test_falsify_rendered_script_attribute_owner_relocation_changes_fingerprint(
    mock_desktop_service: DesktopNodeService,
):
    """Proves executing rendered production scripts detects attribute relocation between document, components, occurrences, bodies, sketches, and timeline."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    fingerprints = {}

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]

    owner_locations = [
        "document",
        "body",
        "sketch",
        "component",
        "occurrence",
        "timeline",
        "feature",
    ]

    for loc in owner_locations:
        with AdskFakeContext("doc_1", initial_volume=100.0):
            import adsk.core

            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")
            root = design.rootComponent

            # Add an occurrence to rootComponent for testing occurrence owner
            if hasattr(root, "allOccurrences"):

                class FakeOcc:
                    def __init__(self):
                        self.name = "Occ1"
                        self.entityToken = "occ_token_1"
                        self.fullPathName = "Root+Occ1"
                        self.isVisible = True
                        self.isLightBulbOn = True

                        class FT:
                            def asArray(self):
                                return [
                                    1.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    1.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    1.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    0.0,
                                    1.0,
                                ]

                        self.transform = FT()

                        class FA:
                            def __init__(self):
                                self._items = []

                            @property
                            def count(self):
                                return len(self._items)

                            def item(self, idx):
                                return self._items[idx]

                            def add(self, g, n, v):
                                class Attr:
                                    def __init__(self, g, n, v):
                                        self.groupName = g
                                        self.name = n
                                        self.value = v

                                self._items.append(Attr(g, n, v))

                        self.attributes = FA()

                occ = FakeOcc()
                root.allOccurrences = type(
                    "FakeColl", (), {"count": 1, "item": lambda self, idx, o=occ: o}
                )()

            # Place attribute ("bridge.cad/v1", "marker", "val1") at the specified location
            if loc == "document":
                doc.attributes.add("bridge.cad/v1", "marker", "val1")
            elif loc == "body":
                root.bRepBodies.item(0).attributes.add(
                    "bridge.cad/v1", "marker", "val1"
                )
            elif loc == "sketch":
                root.sketches.item(0).attributes.add("bridge.cad/v1", "marker", "val1")
            elif loc == "component":
                root.attributes.add("bridge.cad/v1", "marker", "val1")
            elif loc == "occurrence":
                occ.attributes.add("bridge.cad/v1", "marker", "val1")
            elif loc == "timeline":
                design.timeline.item(0).attributes.add(
                    "bridge.cad/v1", "marker", "val1"
                )
            elif loc == "feature":
                design.timeline.item(0).entity.attributes.add(
                    "bridge.cad/v1", "marker", "val1"
                )

            res = await cad_service.execute(
                {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
            )
            assert isinstance(res, CadResult)
            fp = res.data["fingerprint"]
            fingerprints[loc] = fp

    # Every location must produce a distinct fingerprint
    distinct_fps = set(fingerprints.values())
    assert len(distinct_fps) == len(owner_locations), (
        f"Fingerprints did not differentiate owner locations: {fingerprints}"
    )


@pytest.mark.asyncio
async def test_falsify_rendered_script_unreadable_mandatory_fingerprint_data_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves rendered production script fails closed before write when mandatory transform, visibility, geometry, or attributes are unreadable."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]

    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref

    unreadable_cases = [
        "corrupt_transform",
        "missing_transform_asArray",
        "missing_body_volume",
        "missing_body_area",
        "missing_body_isSolid",
        "missing_body_visibility",
        "missing_body_bbox",
        "missing_body_vertex_geometry",
        "missing_body_attributes",
        "missing_body_entityToken",
        "missing_sketch_visibility",
        "missing_sketch_profiles",
        "missing_sketch_geometricConstraints",
        "missing_sketch_point_geometry",
        "missing_sketch_attributes",
        "missing_sketch_entityToken",
        "missing_component_attributes",
        "missing_component_entityToken",
        "missing_occurrence_attributes",
        "missing_occurrence_entityToken",
        "missing_timeline_attributes",
        "missing_timeline_entityToken",
        "unreadable_doc_attributes",
    ]

    for case in unreadable_cases:
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0):
            import adsk.core

            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")
            root = design.rootComponent

            if case == "corrupt_transform":
                # Add an occurrence with transform=None
                class BadOcc:
                    name = "Occ1"
                    fullPathName = "Root+Occ1"
                    transform = None

                root.allOccurrences = type(
                    "FakeColl", (), {"count": 1, "item": lambda s, idx: BadOcc()}
                )()
            elif case == "missing_transform_asArray":

                class BadOcc2:
                    name = "Occ1"
                    fullPathName = "Root+Occ1"
                    transform = object()  # lacks asArray

                root.allOccurrences = type(
                    "FakeColl", (), {"count": 1, "item": lambda s, idx: BadOcc2()}
                )()
            elif case == "missing_body_volume":
                root.bRepBodies.item(0)._ctx.volume = None
            elif case == "missing_body_area":
                root.bRepBodies.item(0).area = None
            elif case == "missing_body_isSolid":
                root.bRepBodies.item(0).isSolid = None
            elif case == "missing_body_visibility":
                root.bRepBodies.item(0).isVisible = None
                root.bRepBodies.item(0).isLightBulbOn = None
            elif case == "missing_body_bbox":
                root.bRepBodies.item(0).boundingBox = None
            elif case == "missing_body_vertex_geometry":
                root.bRepBodies.item(0).vertices = None
            elif case == "missing_body_attributes":
                root.bRepBodies.item(0).attributes = None
            elif case == "missing_body_entityToken":
                root.bRepBodies.item(0).entityToken = ""
            elif case == "missing_sketch_visibility":
                root.sketches.item(0).isVisible = None
                root.sketches.item(0).isLightBulbOn = None
            elif case == "missing_sketch_profiles":
                root.sketches.item(0).profiles = None
            elif case == "missing_sketch_geometricConstraints":
                root.sketches.item(0).geometricConstraints = None
            elif case == "missing_sketch_point_geometry":
                root.sketches.item(0).sketchPoints = None
            elif case == "missing_sketch_attributes":
                root.sketches.item(0).attributes = None
            elif case == "missing_sketch_entityToken":
                root.sketches.item(0).entityToken = ""
            elif case == "missing_component_attributes":
                root.attributes = None
            elif case == "missing_component_entityToken":
                root.entityToken = ""
                root.id = ""
            elif case == "missing_occurrence_attributes":

                class BadOccAttrs:
                    name = "Occ1"
                    entityToken = "occ_1"
                    fullPathName = "Root+Occ1"
                    isVisible = True
                    isLightBulbOn = True
                    transform = type(
                        "FakeTransform", (), {"asArray": lambda self: [1.0] * 16}
                    )()
                    attributes = None

                root.allOccurrences = type(
                    "FakeColl", (), {"count": 1, "item": lambda s, idx: BadOccAttrs()}
                )()
            elif case == "missing_occurrence_entityToken":

                class BadOccToken:
                    name = "Occ1"
                    entityToken = ""
                    fullPathName = "Root+Occ1"
                    isVisible = True
                    isLightBulbOn = True
                    transform = type(
                        "FakeTransform", (), {"asArray": lambda self: [1.0] * 16}
                    )()
                    attributes = type(
                        "FakeAttrs", (), {"count": 0, "item": lambda s, idx: None}
                    )()

                root.allOccurrences = type(
                    "FakeColl", (), {"count": 1, "item": lambda s, idx: BadOccToken()}
                )()
            elif case == "missing_timeline_attributes":
                design.timeline.item(0).attributes = None
            elif case == "missing_timeline_entityToken":
                design.timeline.item(0).entityToken = ""
                design.timeline.item(0).entity.entityToken = ""
            elif case == "unreadable_doc_attributes":
                doc.attributes = None

            with pytest.raises(FusionCadError) as exc_case:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "set",
                        "target": body_ref,
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_case.value.code in (
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.FUSION_API_ERROR,
            ), f"Unexpected code for case {case}: {exc_case.value.code}"
            assert primitive_reached is False, (
                f"Primitive was reached for unreadable case {case}!"
            )


@pytest.mark.asyncio
async def test_falsify_sketch_geometry_movement_triggers_revision_conflict_in_rendered_pipeline(
    mock_desktop_service: DesktopNodeService,
):
    """Proves altering sketch point coordinates without changing counts triggers REVISION_CONFLICT in rendered pipeline."""
    with AdskFakeContext("doc_1", initial_volume=100.0):
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="metadata.attributes", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        )
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_mutation_primitive": lambda payload: None,
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
        body_ref = cad_service.ref_registry.issue(
            document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
        ).ref

        # 1. Snapshot read establishes initial baseline
        snap_res = await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
        )
        assert isinstance(snap_res, CadResult)
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"

        # 2. Alter sketch point geometry without changing count of sketch points or curves
        import adsk.core

        app = adsk.core.Application.get()
        doc = app.activeDocument
        design = doc.products.itemByClass("adsk::fusion::Design")
        sketch = design.rootComponent.sketches.item(0)
        # Move point 0 from (0, 0, 0) to (42.0, 99.0, 0)
        sketch.sketchPoints.item(0).geometry.x = 42.0
        sketch.sketchPoints.item(0).geometry.y = 99.0

        # 3. Attempt mutation expecting rev_1 -> must fail closed with REVISION_CONFLICT
        with pytest.raises(FusionCadError) as exc_info:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": body_ref,
                    "name": "tag",
                    "value": "v1",
                    "expected_revision": "rev_1",
                },
                group="metadata",
            )
        assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
        assert exc_info.value.details.get("applied") is False


@pytest.mark.asyncio
async def test_falsify_transaction_begin_fails_closed_without_establishing_baseline_on_empty_fingerprint_or_doc_ref(
    mock_desktop_service: DesktopNodeService,
):
    """Proves transaction:begin terminal execution with empty/whitespace fingerprint or missing doc_ref fails closed and does not establish a baseline."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # Case A: empty fingerprint returned by terminal script execution
    mock_sub = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Executed transaction:begin",
                            "document": {
                                "document_ref": "doc_tx_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_bad_fp",
                                "operation": "begin",
                                "fingerprint": "   ",
                            },
                        }
                    ),
                }
            ],
        }
    )
    mock_desktop_service.call = mock_sub
    mock_desktop_service.submit = mock_sub

    with pytest.raises(FusionCadError) as exc_fp:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "begin", "transaction_id": "tx_bad_fp"},
            group="transaction",
        )
    assert exc_fp.value.code == ErrorCode.FUSION_API_ERROR
    assert "missing, empty, or whitespace real fingerprint" in exc_fp.value.message
    # Baseline must NOT be established
    assert cad_service.revision_tracker.get_transaction_baseline("tx_bad_fp") is None

    # Case B: missing active document reference
    mock_sub_no_doc = AsyncMock(
        return_value={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Executed transaction:begin",
                            "document": None,
                            "data": {
                                "transaction_id": "tx_no_doc",
                                "operation": "begin",
                                "fingerprint": "real_fp_123",
                            },
                        }
                    ),
                }
            ],
        }
    )
    mock_desktop_service.call = mock_sub_no_doc
    mock_desktop_service.submit = mock_sub_no_doc

    with pytest.raises(FusionCadError) as exc_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "begin", "transaction_id": "tx_no_doc"},
            group="transaction",
        )
    assert exc_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN
    assert "without an active document reference" in exc_doc.value.message
    # Baseline must NOT be established
    assert cad_service.revision_tracker.get_transaction_baseline("tx_no_doc") is None


@pytest.mark.asyncio
async def test_falsify_rendered_mutation_returns_real_fusion_post_apply_fingerprint_and_advances_guard(
    mock_desktop_service: DesktopNodeService,
):
    """Proves mutation returns real Fusion-side post-apply fingerprint (not synthetic) and advances revision authority."""
    with AdskFakeContext("doc_1", initial_volume=100.0):
        cad_service = FusionCadService(mock_desktop_service)
        matrix = CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="metadata.attributes", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        )
        cad_service.set_node_capabilities("desk-1", matrix)

        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["script"]
            scope = {
                "__name__": "__main__",
                "_mutation_primitive": lambda payload: None,
            }
            exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
            return scope["_output"]

        mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
        mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
        body_ref = cad_service.ref_registry.issue(
            document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
        ).ref

        # Initial read
        snap_res = await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
        )
        data_initial = (
            snap_res.data if isinstance(snap_res, CadResult) else snap_res["data"]
        )
        initial_fp = data_initial.get("fingerprint")
        assert initial_fp
        assert "mutated" not in initial_fp

        # Mutate
        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "tag",
                "value": "v1",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
        data_res = res.data if isinstance(res, CadResult) else res["data"]
        doc_res = res.document if isinstance(res, CadResult) else res["document"]
        post_fp = data_res.get("fingerprint")
        assert post_fp
        assert post_fp != initial_fp
        assert "mutated" not in post_fp
        # Returned revision matches tracker current
        assert (
            doc_res.model_revision
            if hasattr(doc_res, "model_revision")
            else doc_res["model_revision"]
        ) == "rev_2"
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"
        assert cad_service.revision_tracker.current("doc_1").fingerprint == post_fp

        # Next mutation using fresh rev_2 succeeds
        res2 = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "tag2",
                "value": "v2",
                "expected_revision": "rev_2",
            },
            group="metadata",
        )
        data_res2 = res2.data if isinstance(res2, CadResult) else res2["data"]
        doc_res2 = res2.document if isinstance(res2, CadResult) else res2["document"]
        assert (
            doc_res2.model_revision
            if hasattr(doc_res2, "model_revision")
            else doc_res2["model_revision"]
        ) == "rev_3"
        assert data_res2.get("fingerprint") != post_fp


@pytest.mark.asyncio
async def test_falsify_abort_rollback_preserves_baseline_on_failure_uncertain_or_inconsistency(
    mock_desktop_service: DesktopNodeService,
):
    """Proves abort/rollback clears baseline only after proven successful terminal result with stable runtime doc identity and acceptable real fingerprint."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Seed baseline for tx_abort
    cad_service.revision_tracker.observe("doc_1", "baseline_fp_1")
    cad_service.revision_tracker.begin_transaction(
        "tx_abort", "doc_1", "rev_1", "baseline_fp_1"
    )
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    def set_mock_resp(val):
        mock_desktop_service.call = AsyncMock(return_value=val)
        mock_desktop_service.submit = AsyncMock(return_value=val)

    # Case A: Desktop node execution fails or returns non-succeeded status -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "failed",
                            "summary": "transaction:abort failed",
                            "error": {
                                "code": "FUSION_API_ERROR",
                                "message": "Failed to abort",
                            },
                        }
                    ),
                }
            ],
            "isError": True,
        }
    )
    with pytest.raises(BridgeError):
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
            group="transaction",
        )
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    # Case B: Abort returns without stable runtime document identity -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:abort",
                            "document": None,
                            "data": {
                                "transaction_id": "tx_abort",
                                "operation": "abort",
                                "applied": True,
                                "fingerprint": "baseline_fp_1",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_no_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
            group="transaction",
        )
    assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    # Case C: Abort returns document mismatch -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:abort",
                            "document": {
                                "document_ref": "doc_other",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_abort",
                                "operation": "abort",
                                "applied": True,
                                "fingerprint": "baseline_fp_1",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_wrong_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
            group="transaction",
        )
    assert exc_wrong_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    # Case D: Abort returns empty/whitespace fingerprint -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:abort",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_abort",
                                "operation": "abort",
                                "applied": True,
                                "fingerprint": "   ",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_empty_fp:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
            group="transaction",
        )
    assert exc_empty_fp.value.code == ErrorCode.FUSION_API_ERROR
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    # Case E: Abort returns diverged/inconsistent fingerprint -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:abort",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_abort",
                                "operation": "abort",
                                "applied": True,
                                "fingerprint": "diverged_random_fp",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_diverged:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
            group="transaction",
        )
    assert exc_diverged.value.code == ErrorCode.REVISION_CONFLICT
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is not None

    # Case F: Proven successful abort with valid document identity and matching fingerprint clears baseline
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:abort",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_abort",
                                "operation": "abort",
                                "applied": True,
                                "fingerprint": "baseline_fp_1",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    res_abort = await cad_service.execute(
        {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort"},
        group="transaction",
    )
    assert res_abort is not None
    assert cad_service.revision_tracker.get_transaction_baseline("tx_abort") is None


@pytest.mark.asyncio
async def test_falsify_commit_preserves_baseline_on_failure_uncertain_or_inconsistency(
    mock_desktop_service: DesktopNodeService,
):
    """Proves commit clears baseline only after proven successful terminal result with stable runtime doc identity and authoritative fingerprint."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Seed baseline for tx_commit
    cad_service.revision_tracker.observe("doc_1", "baseline_fp_1")
    cad_service.revision_tracker.begin_transaction(
        "tx_commit", "doc_1", "rev_1", "baseline_fp_1"
    )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    def set_mock_resp(val):
        mock_desktop_service.call = AsyncMock(return_value=val)
        mock_desktop_service.submit = AsyncMock(return_value=val)

    # Case A: Desktop node execution fails or returns non-succeeded status -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "failed",
                            "summary": "transaction:commit failed",
                            "error": {
                                "code": "FUSION_API_ERROR",
                                "message": "Failed to commit",
                            },
                        }
                    ),
                }
            ],
            "isError": True,
        }
    )
    with pytest.raises(BridgeError):
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
            group="transaction",
        )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    # Case B: Commit returns without stable runtime document identity -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:commit",
                            "document": None,
                            "data": {
                                "transaction_id": "tx_commit",
                                "operation": "commit",
                                "applied": True,
                                "fingerprint": "new_fp_post",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_no_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
            group="transaction",
        )
    assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    # Case C: Commit returns document mismatch -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:commit",
                            "document": {
                                "document_ref": "doc_other",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_commit",
                                "operation": "commit",
                                "applied": True,
                                "fingerprint": "new_fp_post",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_wrong_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
            group="transaction",
        )
    assert exc_wrong_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    # Case C2: Commit returns diverged document identity between document state and payload data -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:commit",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_commit",
                                "operation": "commit",
                                "applied": True,
                                "document_ref": "doc_diverged",
                                "fingerprint": "new_fp_post",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_diverged_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
            group="transaction",
        )
    assert exc_diverged_doc.value.code == ErrorCode.WRONG_DOCUMENT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    # Case D: Commit returns empty/whitespace fingerprint -> baseline preserved
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:commit",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_commit",
                                "operation": "commit",
                                "applied": True,
                                "fingerprint": "   ",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    with pytest.raises(FusionCadError) as exc_empty_fp:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
            group="transaction",
        )
    assert exc_empty_fp.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit") is not None
    )

    # Case E: Proven successful commit with valid document identity and real fingerprint clears baseline and advances revision
    set_mock_resp(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction:commit",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": {
                                "transaction_id": "tx_commit",
                                "operation": "commit",
                                "applied": True,
                                "fingerprint": "new_fp_post",
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
    )
    res_commit = await cad_service.execute(
        {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_commit"},
        group="transaction",
    )
    assert res_commit is not None
    assert cad_service.revision_tracker.get_transaction_baseline("tx_commit") is None
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "new_fp_post"


@pytest.mark.asyncio
async def test_falsify_no_doc_1_fallback_and_fabricated_fingerprint_rejected(
    mock_desktop_service: DesktopNodeService,
):
    """Proves assert_fresh_for_mutation does not fall back to 'doc_1' and caller mock_model_state is rejected."""
    cad_service = FusionCadService(mock_desktop_service)

    # 1. Empty tracker assert_fresh_for_mutation fails with NO_ACTIVE_DESIGN rather than falling back to "doc_1"
    with pytest.raises(FusionCadError) as exc_no_doc:
        cad_service.assert_fresh_for_mutation(expected_revision="rev_1")
    assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN

    # 2. execute rejects caller-supplied mock_model_state before dispatch
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    with pytest.raises(BridgeError) as exc_mock:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "model_snapshot",
                "mock_model_state": {"document": {"document_ref": "doc_forged"}},
            },
            group="read",
        )
    assert exc_mock.value.code == ErrorCode.INVALID_ARGUMENT
    assert any(
        ve.get("type") == "extra_forbidden"
        and "mock_model_state" in ve.get("loc", [])
        for ve in exc_mock.value.details.get("validation_errors", [])
    ), exc_mock.value.details

    # 3. Even if supplied directly to script bundle, mock_model_state is not recognized
    from app.fusion_cad.scripts import FusionCadScriptBundle

    bundle = FusionCadScriptBundle()
    script = bundle.build(
        "read",
        {
            "operation": "model_snapshot",
            "mock_model_state": {"document": {"document_ref": "doc_forged"}},
        },
    )
    scope = {"__name__": "__main__"}
    exec(compile(script, "<test-script>", "exec"), scope)  # noqa: S102
    assert scope["_output"]["status"] == "failed"


@pytest.mark.asyncio
async def test_falsify_rendered_face_edge_unreadable_attributes_or_tokens_fail_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves face, edge, sketch curve, and sketch point with unreadable attributes or empty entity tokens fail closed before mutation."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref

    unreadable_cases = [
        "face_attributes_none",
        "face_token_empty",
        "edge_attributes_none",
        "edge_token_empty",
        "sketch_curve_attributes_none",
        "sketch_curve_token_empty",
        "sketch_point_attributes_none",
        "sketch_point_token_empty",
    ]

    for case in unreadable_cases:
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0):
            import adsk.core

            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")
            body = design.rootComponent.bRepBodies.item(0)
            sketch = design.rootComponent.sketches.item(0)

            if case == "face_attributes_none":
                body.faces.item(0).attributes = None
            elif case == "face_token_empty":
                body.faces.item(0).entityToken = ""
                body.faces.item(0).id = ""
            elif case == "edge_attributes_none":
                body.edges.item(0).attributes = None
            elif case == "edge_token_empty":
                body.edges.item(0).entityToken = ""
                body.edges.item(0).id = ""
            elif case == "sketch_curve_attributes_none":
                sketch.sketchCurves.item(0).attributes = None
            elif case == "sketch_curve_token_empty":
                sketch.sketchCurves.item(0).entityToken = ""
                sketch.sketchCurves.item(0).id = ""
            elif case == "sketch_point_attributes_none":
                sketch.sketchPoints.item(0).attributes = None
            elif case == "sketch_point_token_empty":
                sketch.sketchPoints.item(0).entityToken = ""
                sketch.sketchPoints.item(0).id = ""

            with pytest.raises(FusionCadError) as exc_case:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "set",
                        "target": body_ref,
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_case.value.code in (
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.FUSION_API_ERROR,
            ), f"Unexpected code for {case}: {exc_case.value.code}"
            assert primitive_reached is False


@pytest.mark.asyncio
async def test_falsify_face_edge_and_sketch_geometry_topology_fail_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves rendered production script fails closed if face/edge/sketch curve topology or geometry collections are unreadable."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref

    corrupt_cases = [
        "face_loops_none",
        "face_bbox_none",
        "edge_faces_none",
        "edge_bbox_none",
        "sketch_curve_bbox_none",
        "sketch_curve_start_point_geom_none",
    ]

    for case in corrupt_cases:
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0):
            import adsk.core

            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")
            body = design.rootComponent.bRepBodies.item(0)
            sketch = design.rootComponent.sketches.item(0)

            if case == "face_loops_none":
                body.faces.item(0).loops = None
            elif case == "face_bbox_none":
                body.faces.item(0).boundingBox = None
            elif case == "edge_faces_none":
                body.edges.item(0).faces = None
            elif case == "edge_bbox_none":
                body.edges.item(0).boundingBox = None
            elif case == "sketch_curve_bbox_none":
                sketch.sketchCurves.item(0).boundingBox = None
            elif case == "sketch_curve_start_point_geom_none":
                sketch.sketchCurves.item(0).startSketchPoint.geometry = None

            with pytest.raises(FusionCadError) as exc_case:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "set",
                        "target": body_ref,
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_case.value.code in (
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.FUSION_API_ERROR,
            )
            assert primitive_reached is False


@pytest.mark.asyncio
async def test_falsify_mandatory_attribute_collections_fail_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves that missing mandatory attribute collections across all 11 owner types fail closed with CAPABILITY_UNAVAILABLE."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    primitive_reached = False

    async def run_rendered_production_script(
        node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
    ):
        nonlocal primitive_reached
        script = arguments["script"]
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda payload: globals().update(
                primitive_reached=True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    mock_desktop_service.submit = run_rendered_production_script  # type: ignore[assignment]
    mock_desktop_service.call = run_rendered_production_script  # type: ignore[assignment]
    cad_service.revision_tracker.observe("doc_1", "seed-fp")
    body_ref = cad_service.ref_registry.issue(
        document_ref="doc_1", kind="body", name="Body1", native_token="body_token_1"
    ).ref

    missing_owner_collections = [
        "missing_doc_attributes",
        "missing_root_occurrences",
        "missing_root_bodies",
        "missing_body_faces",
        "missing_body_edges",
        "missing_root_sketches",
        "missing_sketch_curves",
        "missing_sketch_points",
        "missing_timeline",
    ]

    for case in missing_owner_collections:
        primitive_reached = False
        with AdskFakeContext("doc_1", initial_volume=100.0):
            import adsk.core

            app = adsk.core.Application.get()
            doc = app.activeDocument
            design = doc.products.itemByClass("adsk::fusion::Design")
            root = design.rootComponent

            if case == "missing_doc_attributes":
                doc.attributes = None
            elif case == "missing_root_occurrences":
                root.allOccurrences = None
            elif case == "missing_root_bodies":
                root.bRepBodies = None
            elif case == "missing_body_faces":
                root.bRepBodies.item(0).faces = None
            elif case == "missing_body_edges":
                root.bRepBodies.item(0).edges = None
            elif case == "missing_root_sketches":
                root.sketches = None
            elif case == "missing_sketch_curves":
                root.sketches.item(0).sketchCurves = None
            elif case == "missing_sketch_points":
                root.sketches.item(0).sketchPoints = None
            elif case == "missing_timeline":
                design.timeline = None

            with pytest.raises(FusionCadError) as exc_case:
                await cad_service.execute(
                    {
                        "node_id": "desk-1",
                        "operation": "set",
                        "target": body_ref,
                        "name": "tag",
                        "value": "v1",
                        "expected_revision": "rev_1",
                    },
                    group="metadata",
                )
            assert exc_case.value.code in (
                ErrorCode.CAPABILITY_UNAVAILABLE,
                ErrorCode.FUSION_API_ERROR,
            )
            assert primitive_reached is False


@pytest.mark.asyncio
async def test_falsify_commit_abort_rollback_require_applied_is_true(
    mock_desktop_service: DesktopNodeService,
):
    """Proves commit/abort/rollback fails closed and preserves baseline and tracker when applied is missing, False, or non-bool."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    def set_mock_resp(data_payload):
        resp = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "transaction execution",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_1",
                            },
                            "data": data_payload,
                        }
                    ),
                }
            ],
            "isError": False,
        }
        mock_desktop_service.call = AsyncMock(return_value=resp)
        mock_desktop_service.submit = AsyncMock(return_value=resp)

    # 1. Commit with applied=False preserves baseline and does not advance tracker
    cad_service.revision_tracker.observe("doc_1", "base_fp")
    cad_service.revision_tracker.begin_transaction(
        "tx_commit_1", "doc_1", "rev_1", "base_fp"
    )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit_1") is not None
    )
    set_mock_resp(
        {
            "transaction_id": "tx_commit_1",
            "operation": "commit",
            "applied": False,
            "fingerprint": "new_fp",
        }
    )
    with pytest.raises(FusionCadError) as exc_false:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_commit_1",
            },
            group="transaction",
        )
    assert exc_false.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit_1") is not None
    )
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "base_fp"

    # 2. Commit with missing applied preserves baseline and does not advance tracker
    set_mock_resp(
        {
            "transaction_id": "tx_commit_1",
            "operation": "commit",
            "fingerprint": "new_fp",
        }
    )
    with pytest.raises(FusionCadError) as exc_missing:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_commit_1",
            },
            group="transaction",
        )
    assert exc_missing.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_commit_1") is not None
    )
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"

    # 3. Commit with non-bool applied ("true", 1, None) preserves baseline and tracker
    for non_bool in ["true", 1, None, [True]]:
        set_mock_resp(
            {
                "transaction_id": "tx_commit_1",
                "operation": "commit",
                "applied": non_bool,
                "fingerprint": "new_fp",
            }
        )
        with pytest.raises(FusionCadError) as exc_non_bool:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "commit",
                    "transaction_id": "tx_commit_1",
                },
                group="transaction",
            )
        assert exc_non_bool.value.code == ErrorCode.FUSION_API_ERROR
        assert (
            cad_service.revision_tracker.get_transaction_baseline("tx_commit_1")
            is not None
        )
        assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"

    # 4. Abort and rollback with applied=False preserve baseline
    cad_service.revision_tracker.begin_transaction(
        "tx_abort_1", "doc_1", "rev_1", "base_fp"
    )
    set_mock_resp(
        {
            "transaction_id": "tx_abort_1",
            "operation": "abort",
            "applied": False,
            "fingerprint": "base_fp",
        }
    )
    with pytest.raises(FusionCadError) as exc_abort:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "abort", "transaction_id": "tx_abort_1"},
            group="transaction",
        )
    assert exc_abort.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_abort_1") is not None
    )

    cad_service.revision_tracker.begin_transaction(
        "tx_rollback_1", "doc_1", "rev_1", "base_fp"
    )
    set_mock_resp(
        {
            "transaction_id": "tx_rollback_1",
            "operation": "rollback",
            "applied": "true",
            "fingerprint": "base_fp",
        }
    )
    with pytest.raises(FusionCadError) as exc_rollback:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "rollback",
                "transaction_id": "tx_rollback_1",
            },
            group="transaction",
        )
    assert exc_rollback.value.code == ErrorCode.FUSION_API_ERROR
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_rollback_1")
        is not None
    )


@pytest.mark.asyncio
async def test_falsify_abort_rollback_rejects_divergent_tracker_fingerprint(
    mock_desktop_service: DesktopNodeService,
):
    """Proves baseline='base', tracker current='external', abort/rollback result='external' => REVISION_CONFLICT and baseline preserved."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Seed baseline='base'
    cad_service.revision_tracker.observe("doc_1", "base")
    cad_service.revision_tracker.begin_transaction(
        "tx_abort_div", "doc_1", "rev_1", "base"
    )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_abort_div")
        is not None
    )

    # 2. External change advances tracker to 'external'
    cad_service.revision_tracker.observe("doc_1", "external")
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "external"
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

    def set_mock_resp(op_name, fp):
        resp = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": f"transaction:{op_name}",
                            "document": {
                                "document_ref": "doc_1",
                                "model_revision": "rev_2",
                            },
                            "data": {
                                "transaction_id": f"tx_{op_name}_div",
                                "operation": op_name,
                                "applied": True,
                                "fingerprint": fp,
                            },
                        }
                    ),
                }
            ],
            "isError": False,
        }
        mock_desktop_service.call = AsyncMock(return_value=resp)
        mock_desktop_service.submit = AsyncMock(return_value=resp)

    # 3. Abort returns result fp='external' -> REVISION_CONFLICT, baseline preserved, tracker NOT restored
    set_mock_resp("abort", "external")
    with pytest.raises(FusionCadError) as exc_abort:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "abort",
                "transaction_id": "tx_abort_div",
            },
            group="transaction",
        )
    assert exc_abort.value.code == ErrorCode.REVISION_CONFLICT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_abort_div")
        is not None
    )
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "external"
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

    # 4. Rollback returns result fp='external' -> REVISION_CONFLICT, baseline preserved, tracker NOT restored
    cad_service.revision_tracker.begin_transaction(
        "tx_rollback_div", "doc_1", "rev_1", "base"
    )
    set_mock_resp("rollback", "external")
    with pytest.raises(FusionCadError) as exc_rb:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "rollback",
                "transaction_id": "tx_rollback_div",
            },
            group="transaction",
        )
    assert exc_rb.value.code == ErrorCode.REVISION_CONFLICT
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_rollback_div")
        is not None
    )
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "external"
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"


@pytest.mark.asyncio
async def test_falsify_externalization_failure_preserves_baseline_and_tracker_authority(
    mock_desktop_service: DesktopNodeService,
):
    """Proves outward failure during store_external_result preserves baseline and tracker authority unchanged."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Seed baseline
    cad_service.revision_tracker.observe("doc_1", "base_fp")
    cad_service.revision_tracker.begin_transaction(
        "tx_ext_fail", "doc_1", "rev_1", "base_fp"
    )
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_ext_fail") is not None
    )

    # 2. Return a successful commit result containing binary data
    resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "transaction:commit with binary payload",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "transaction_id": "tx_ext_fail",
                            "operation": "commit",
                            "applied": True,
                            "fingerprint": "post_fp",
                            "screenshot_bytes": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=resp)
    mock_desktop_service.submit = AsyncMock(return_value=resp)

    # 3. Force store_external_result to fail
    mock_desktop_service.store_external_result = MagicMock(
        side_effect=RuntimeError("External artifact storage disk full")
    )

    with pytest.raises(BridgeError) as exc_ext:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_ext_fail",
            },
            group="transaction",
        )
    assert exc_ext.value.code == ErrorCode.INTERNAL_ERROR
    assert "Failed to externalize binary result payload" in exc_ext.value.message

    # Baseline authority must remain preserved
    assert (
        cad_service.revision_tracker.get_transaction_baseline("tx_ext_fail") is not None
    )
    # Tracker authority must remain unchanged at rev_1 and base_fp
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "base_fp"


@pytest.mark.asyncio
async def test_fusion_read_model_snapshot_compact_and_full(
    mock_desktop_service: DesktopNodeService,
):
    """Proves fusion_read model_snapshot normalizes semantic snapshot, computes structural hash, and saves in SnapshotStore."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="timeline.access", state="supported"),
            CapabilityRecord(name="selection.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    raw_model_data = {
        "document": {"document_ref": "doc_main_123", "name": "Assembly1"},
        "model_revision": "rev_1",
        "counts": {"faces": 240, "edges": 360, "vertices": 120},
        "faces": [{"id": f"face_{i}", "area": 10.0} for i in range(240)],
        "components": [{"name": "CompA", "id": "comp_1"}],
        "occurrences": [{"name": "CompA:1", "full_path_name": "CompA:1"}],
        "bodies": [
            {
                "name": "BodyA",
                "component_name": "CompA",
                "faces_count": 240,
                "edges_count": 360,
                "vertices_count": 120,
            }
        ],
        "sketches": [{"name": "SketchA", "profiles_count": 1}],
        "timeline": [
            {
                "index": 0,
                "name": "Extrude1",
                "feature_type": "ExtrudeFeature",
                "inputs": [],
                "outputs": ["ent_bodyA"],
            }
        ],
        "parameters": {
            "model_parameters": [{"name": "d1", "value": 10.0, "unit": "mm"}],
            "user_parameters": [{"name": "len", "value": 50.0, "unit": "mm"}],
        },
    }

    def set_mock_snapshot_resp(detail="compact"):
        resp = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": f"Model snapshot read ({detail})",
                            "document": {
                                "document_ref": "doc_main_123",
                                "model_revision": "rev_1",
                            },
                            "data": raw_model_data,
                        }
                    ),
                }
            ],
            "isError": False,
        }
        mock_desktop_service.call = AsyncMock(return_value=resp)
        mock_desktop_service.submit = AsyncMock(return_value=resp)

    # 1. Compact snapshot
    set_mock_snapshot_resp("compact")
    res_compact = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot", "detail": "compact"},
        group="read",
    )
    assert res_compact.status == "succeeded"
    assert res_compact.data["counts"]["faces"] == 240
    assert "faces" not in res_compact.data or res_compact.data.get("faces") is None
    assert res_compact.data["structural_hash"]
    snapshot_id = res_compact.document.snapshot_id
    assert snapshot_id.startswith("snap_")

    # Stored in SnapshotStore
    stored = cad_service.snapshot_store.get(snapshot_id)
    assert stored is not None
    assert stored.snapshot_id == snapshot_id
    assert stored.counts.faces == 240

    # 2. Full detail snapshot includes topology
    set_mock_snapshot_resp("full")
    res_full = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot", "detail": "full"},
        group="read",
    )
    assert res_full.status == "succeeded"
    assert res_full.data["faces"] is not None
    assert len(res_full.data["faces"]) == 240


@pytest.mark.asyncio
async def test_fusion_read_feature_tree_fidelity(
    mock_desktop_service: DesktopNodeService,
):
    """Proves fusion_read feature_tree exposes timeline index and dependency fidelity (never upgrading inferred)."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="timeline.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Feature tree read",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "features": [
                                {
                                    "index": 0,
                                    "name": "BaseSketch",
                                    "feature_type": "SketchFeature",
                                    "is_suppressed": False,
                                    "health_status": "ok",
                                    "inputs": [],
                                    "outputs": ["ent_sk_1"],
                                },
                                {
                                    "index": 1,
                                    "name": "Extrude1",
                                    "feature_type": "ExtrudeFeature",
                                    "is_suppressed": False,
                                    "health_status": "warning",
                                    "diagnostic_message": "Dependency missing reference",
                                    "inputs": [
                                        {
                                            "ref": "ent_sk_1",
                                            "kind": "sketch",
                                            "dependency_type": "exact",
                                        },
                                        {
                                            "ref": "ent_body_inferred",
                                            "kind": "body",
                                            "dependency_type": "inferred",
                                        },
                                    ],
                                    "outputs": ["ent_body_1"],
                                },
                            ],
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=resp)
    mock_desktop_service.submit = AsyncMock(return_value=resp)

    res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "feature_tree"},
        group="read",
    )
    assert res.status == "succeeded"
    features = res.data["features"]
    assert len(features) == 2
    assert features[1]["name"] == "Extrude1"
    assert features[1]["health_status"] == "warning"
    assert features[1]["diagnostic_message"] == "Dependency missing reference"

    deps = {d["ref"]: d["dependency_type"] for d in features[1]["dependencies"]}
    assert deps["ent_sk_1"] == "exact"
    assert deps["ent_body_inferred"] == "inferred"


@pytest.mark.asyncio
async def test_fusion_read_sketch_and_parameters(
    mock_desktop_service: DesktopNodeService,
):
    """Proves sketch reads preserve profile/constraint filters without DOF invention, and parameters filter properly."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="sketch.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Sketch read
    sketch_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Sketch read",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "sketch": {
                                "ref": "ent_sk_1",
                                "name": "SketchProfile",
                                "fully_constrained": True,
                                "profiles": [{"ref": "ent_prof_1", "area": 50.0}],
                                "constraints": [
                                    {"type": "Coincident", "is_satisfied": True}
                                ],
                                "dimensions": [{"name": "d1", "value": 25.0}],
                            }
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=sketch_resp)
    mock_desktop_service.submit = AsyncMock(return_value=sketch_resp)

    res_sketch = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "sketch",
            "ref": "ent_sk_1",
            "include_profiles": False,
        },
        group="read",
    )
    assert res_sketch.status == "succeeded"
    assert res_sketch.data["fully_constrained"] is True
    assert len(res_sketch.data["profiles"]) == 0  # filtered out
    assert len(res_sketch.data["constraints"]) == 1
    assert res_sketch.data.get("dof") is None  # no DOF invented

    # 2. Parameters read
    param_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Parameters read",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "parameters": {
                                "model_parameters": [{"name": "d1", "value": 10.0}],
                                "user_parameters": [{"name": "p_user", "value": 100.0}],
                            }
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=param_resp)
    mock_desktop_service.submit = AsyncMock(return_value=param_resp)

    res_params = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "parameters",
            "include_model_params": False,
            "include_user_params": True,
        },
        group="read",
    )
    assert res_params.status == "succeeded"
    assert "model_parameters" not in res_params.data["parameters"]
    assert len(res_params.data["parameters"]["user_parameters"]) == 1


@pytest.mark.asyncio
async def test_fusion_read_selection_and_query(
    mock_desktop_service: DesktopNodeService,
):
    """Proves selection returns refs and frames, and query operates over snapshot entities."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="selection.primitives", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # 1. Selection read
    sel_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Selection read",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "entities": [
                                {
                                    "ref": "ent_face_10",
                                    "kind": "BRepFace",
                                    "name": "Face10",
                                    "selection_point": {
                                        "x": 5.0,
                                        "y": 10.0,
                                        "z": 0.0,
                                        "frame": {"space": "world"},
                                    },
                                    "frame": {"space": "world"},
                                }
                            ]
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=sel_resp)
    mock_desktop_service.submit = AsyncMock(return_value=sel_resp)

    res_sel = await cad_service.execute(
        {"node_id": "desk-1", "operation": "selection"},
        group="read",
    )
    assert res_sel.status == "succeeded"
    assert res_sel.data["count"] == 1
    assert len(res_sel.data["refs"]) == 1
    assert res_sel.data["entities"][0]["selection_point"]["x"] == 5.0

    # 2. Selector query against snapshot entities
    from app.fusion_cad.snapshots import (
        BodySummary,
        ModelSnapshot,
        SnapshotCounts,
    )

    snap = ModelSnapshot(
        snapshot_id="snap_query_test",
        document_ref="doc_1",
        model_revision="rev_1",
        structural_hash="hash_qt",
        counts=SnapshotCounts(bodies=2),
        bodies=(
            BodySummary(ref="ent_b1", name="ArmBody", is_solid=True),
            BodySummary(ref="ent_b2", name="BracketBody", is_solid=True),
        ),
    )
    cad_service.snapshot_store.put(snap)

    query_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Query executed",
                        "document": {
                            "document_ref": "doc_1",
                            "model_revision": "rev_1",
                        },
                        "data": {},
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=query_resp)
    mock_desktop_service.submit = AsyncMock(return_value=query_resp)

    res_query = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "query",
            "selector": {"kind": "body", "name": {"regex": "^Arm"}},
        },
        group="read",
    )
    assert res_query.status == "succeeded"
    assert res_query.data["matched_count"] == 1
    assert res_query.data["refs"] == ("ent_b1",)


@pytest.mark.asyncio
async def test_fusion_read_synthetic_large_snapshot_externalization(
    mock_desktop_service: DesktopNodeService,
):
    """Proves oversized semantic snapshot uses existing retained external-result path (Step 6)."""
    # Create service with low inline limit to trigger externalization
    cad_service = FusionCadService(mock_desktop_service, inline_limit_bytes=500)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="timeline.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # Large snapshot payload exceeding 500 bytes
    large_payload = {
        "document": {"document_ref": "doc_large", "name": "LargeAssembly"},
        "model_revision": "rev_1",
        "counts": {"faces": 1000, "edges": 2000, "vertices": 500},
        "components": [
            {"name": f"Component_{i}", "id": f"comp_{i}"} for i in range(20)
        ],
        "bodies": [{"name": f"Body_{i}", "faces_count": 50} for i in range(20)],
    }

    resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Large model snapshot read",
                        "document": {
                            "document_ref": "doc_large",
                            "model_revision": "rev_1",
                        },
                        "data": large_payload,
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=resp)
    mock_desktop_service.submit = AsyncMock(return_value=resp)

    external_mock_return = {
        "external_result": {
            "result_id": "ext_snap_12345",
            "size_bytes": 54321,
            "sha256": "abc123sha256snapshot",
        },
        "isError": False,
    }
    mock_desktop_service.store_external_result = MagicMock(
        return_value=external_mock_return
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot", "detail": "compact"},
        group="read",
    )

    # Must return external_result reference rather than oversized inline JSON
    assert "external_result" in result
    assert result["external_result"]["result_id"] == "ext_snap_12345"
    mock_desktop_service.store_external_result.assert_called_once()

    # Stored payload in store_external_result must be the normalized CadResult dict
    call_args = mock_desktop_service.store_external_result.call_args[0]
    assert call_args[0] == "desk-1"
    externalized_payload = call_args[1]
    assert externalized_payload["status"] == "succeeded"
    assert "structural_hash" in externalized_payload["data"]

    # SnapshotStore still safely recorded the snapshot
    latest_snap = cad_service.snapshot_store.get_latest("doc_large")
    assert latest_snap is not None
    assert latest_snap.counts.faces == 1000
    assert len(latest_snap.components) == 20


@pytest.mark.asyncio
async def test_falsify_finding_2_selection_normalization_strips_native_token_fields(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: Selection normalization consumes entityToken internally but strips native/internal token fields."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="selection.primitives", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    sel_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Selection read",
                        "document": {
                            "document_ref": "doc_sel_test",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "entities": [
                                {
                                    "ref": "ent_face_raw",
                                    "kind": "BRepFace",
                                    "name": "Face42",
                                    "entityToken": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
                                    "native_token": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
                                    "token": "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm",
                                    "selection_point": {
                                        "x": 1.0,
                                        "y": 2.0,
                                        "z": 3.0,
                                        "frame": {"space": "world"},
                                    },
                                    "frame": {"space": "world"},
                                }
                            ]
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=sel_resp)
    mock_desktop_service.submit = AsyncMock(return_value=sel_resp)

    res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "selection"},
        group="read",
    )
    assert res.status == "succeeded"
    assert res.data["count"] == 1
    returned_entity = res.data["entities"][0]

    # Public ref issued and registered
    assert returned_entity["ref"].startswith("ent_")
    # Invariant: native token consumed internally by registry
    record = cad_service.ref_registry.get_internal_record(
        returned_entity["ref"], "doc_sel_test"
    )
    assert record is not None
    assert record.native_token == "AQAAAB4AAAAxMjM0NTY3ODkwYWJjZGVm"

    # Invariant: returned public entity must STRIP entityToken, native_token, token
    assert "entityToken" not in returned_entity
    assert "native_token" not in returned_entity
    assert "token" not in returned_entity
    assert "AQAA" not in str(returned_entity)


@pytest.mark.asyncio
async def test_falsify_finding_4_query_supports_component_path_and_metadata_selectors(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 4: fusion_read:query must faithfully support Task 5 SelectorEngine semantics with full candidate metadata."""
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="selection.primitives", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    # Fusion script returns candidates with component_path, tags, logical_object, role, etc.
    candidates_data = [
        {
            "ref": "ent_body_sched",
            "name": "ScheduleTextBody",
            "kind": "body",
            "component_path": ["Root", "Panel:1"],
            "occurrence": "ent_occ_panel1",
            "is_visible": True,
            "role": ["decorative_text"],
            "tags": [
                {
                    "group": "bridge.cad/v1",
                    "name": "layout",
                    "value": "schedule",
                }
            ],
            "logical_object": "text_schedule_01",
        },
        {
            "ref": "ent_body_other",
            "name": "BaseFrame",
            "kind": "body",
            "component_path": ["Root", "Frame:1"],
            "occurrence": "ent_occ_frame1",
            "is_visible": True,
            "role": ["structural"],
            "tags": [
                {
                    "group": "bridge.cad/v1",
                    "name": "layout",
                    "value": "frame",
                }
            ],
            "logical_object": "text_frame_01",
        },
    ]

    def make_query_resp(candidates):
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "api_version": "fusion.cad/v1",
                            "status": "succeeded",
                            "summary": "Candidates collected",
                            "document": {
                                "document_ref": "doc_query_meta",
                                "model_revision": "rev_1",
                            },
                            "data": {"entities": candidates},
                        }
                    ),
                }
            ],
            "isError": False,
        }

    mock_desktop_service.call = AsyncMock(return_value=make_query_resp(candidates_data))
    mock_desktop_service.submit = AsyncMock(
        return_value=make_query_resp(candidates_data)
    )

    # 1. Query by component_path selector
    res_path = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "query",
            "selector": {"component_path": ["Root", "Panel:1"]},
        },
        group="read",
    )
    assert res_path.status == "succeeded"
    assert res_path.data["matched_count"] == 1
    assert res_path.data["refs"] == ("ent_body_sched",)

    # 2. Query by metadata tag selector
    res_tag = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "query",
            "selector": {
                "tag": {
                    "group": "bridge.cad/v1",
                    "name": "layout",
                    "value": "schedule",
                }
            },
        },
        group="read",
    )
    assert res_tag.status == "succeeded"
    assert res_tag.data["matched_count"] == 1
    assert res_tag.data["refs"] == ("ent_body_sched",)

    # 3. Query by logical_object selector
    res_logical = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "query",
            "selector": {"logical_object": "text_schedule_01"},
        },
        group="read",
    )
    assert res_logical.status == "succeeded"
    assert res_logical.data["matched_count"] == 1
    assert res_logical.data["refs"] == ("ent_body_sched",)


@pytest.mark.asyncio
async def test_service_read_operations_never_leak_nested_native_tokens(
    mock_desktop_service: DesktopNodeService,
):
    """Regression: Service-level read operations (model_snapshot, sketch, query, selection)
    must sanitize nested native token aliases without stringifying values.
    """
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="sketch.access", state="supported"),
            CapabilityRecord(name="timeline.access", state="supported"),
            CapabilityRecord(name="selection.primitives", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    secret_snap_tok = "secret::adsk::token::service_snap::9999"
    secret_sk_tok = "secret::adsk::token::service_sk::8888"
    secret_query_tok = "secret::adsk::token::service_query::7777"
    secret_sel_tok = "secret::adsk::token::service_sel::6666"

    # 1. read:model_snapshot with nested tokens in faces, logical_objects, etc.
    raw_snap_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Snapshot captured",
                        "document": {
                            "document_ref": "doc_sec_service",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "counts": {"faces": 1, "edges": 1, "vertices": 1},
                            "components": [{"name": "C1"}],
                            "occurrences": [{"name": "C1:1", "full_path_name": "C1:1"}],
                            "bodies": [
                                {"name": "B1", "faces_count": 1, "edges_count": 1}
                            ],
                            "sketches": [{"name": "S1"}],
                            "timeline": [
                                {"index": 0, "name": "F1", "feature_type": "Extrude"}
                            ],
                            "parameters": {
                                "model_parameters": [],
                                "user_parameters": [],
                            },
                            "faces": [
                                {
                                    "id": "f1",
                                    "area": 10.5,
                                    "entityToken": secret_snap_tok,
                                }
                            ],
                            "logical_objects": [
                                {
                                    "name": "role",
                                    "value": "mount",
                                    "nested": {"token": secret_snap_tok},
                                }
                            ],
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_snap_resp)
    mock_desktop_service.submit = AsyncMock(return_value=raw_snap_resp)

    res_snap = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot", "detail": "full"},
        group="read",
    )
    snap_str = str(res_snap.model_dump(mode="python"))
    assert secret_snap_tok not in snap_str, (
        "Leaked secret token in service model_snapshot"
    )
    # Ensure float area is preserved as float
    assert res_snap.data["faces"][0]["area"] == 10.5

    # 2. read:sketch with nested token in profiles
    raw_sk_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Sketch read",
                        "document": {
                            "document_ref": "doc_sec_service",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "sketch": {
                                "ref": "ent_sk_1",
                                "name": "Sk1",
                                "profiles": [
                                    {
                                        "name": "p1",
                                        "area": 3.14,
                                        "entityToken": secret_sk_tok,
                                    }
                                ],
                            }
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_sk_resp)
    mock_desktop_service.submit = AsyncMock(return_value=raw_sk_resp)

    res_sk = await cad_service.execute(
        {"node_id": "desk-1", "operation": "sketch", "ref": "ent_sk_1"},
        group="read",
    )
    sk_str = str(res_sk.model_dump(mode="python"))
    assert secret_sk_tok not in sk_str, "Leaked secret token in service sketch"
    assert res_sk.data["profiles"][0]["area"] == 3.14

    # 3. read:query with nested token in candidate tags/metadata
    raw_query_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Candidates collected",
                        "document": {
                            "document_ref": "doc_sec_service",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "entities": [
                                {
                                    "ref": "ent_q_1",
                                    "name": "Q1",
                                    "kind": "body",
                                    "entityToken": secret_query_tok,
                                    "metadata": {
                                        "token": secret_query_tok,
                                        "count": 42,
                                    },
                                }
                            ]
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_query_resp)
    mock_desktop_service.submit = AsyncMock(return_value=raw_query_resp)

    res_query = await cad_service.execute(
        {"node_id": "desk-1", "operation": "query", "selector": {"kind": "body"}},
        group="read",
    )
    query_str = str(res_query.model_dump(mode="python"))
    assert secret_query_tok not in query_str, "Leaked secret token in service query"
    assert res_query.data["entities"][0]["metadata"]["count"] == 42

    # 4. read:selection with nested token
    raw_sel_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "succeeded",
                        "summary": "Selection read",
                        "document": {
                            "document_ref": "doc_sec_service",
                            "model_revision": "rev_1",
                        },
                        "data": {
                            "entities": [
                                {
                                    "ref": "ent_sel_1",
                                    "name": "SelectedFace",
                                    "kind": "BRepFace",
                                    "entityToken": secret_sel_tok,
                                    "extra": {"nested_tok": {"token": secret_sel_tok}},
                                }
                            ]
                        },
                    }
                ),
            }
        ],
        "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_sel_resp)
    mock_desktop_service.submit = AsyncMock(return_value=raw_sel_resp)

    res_sel = await cad_service.execute(
        {"node_id": "desk-1", "operation": "selection"},
        group="read",
    )
    sel_str = str(res_sel.model_dump(mode="python"))
    assert secret_sel_tok not in sel_str, "Leaked secret token in service selection"


@pytest.mark.asyncio
async def test_failed_service_read_with_nested_tokens_never_leaks_secrets_in_cad_error(
    mock_desktop_service: DesktopNodeService,
):
    """Regression (a): failed service read with nested token aliases in error/details
    must expose no secret via FusionCadError details/message/str/repr.
    """
    cad_service = FusionCadService(mock_desktop_service)
    matrix = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(name="sketch.access", state="supported"),
        ]
    )
    cad_service.set_node_capabilities("desk-1", matrix)

    secret_native_tok = "secret::adsk::token::fail_read::9999"
    secret_nested_tok = "secret::adsk::token::fail_read_nested::8888"
    secret_err_tok = "secret::adsk::token::fail_err_alias::7777"

    raw_error_resp = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "api_version": "fusion.cad/v1",
                        "status": "failed",
                        "error": {
                            "code": "REF_STALE",
                            "message": "Target entity reference ent_face_stale is stale",
                            "details": {
                                "entityToken": secret_native_tok,
                                "target": "ent_face_stale",
                                "nested": {
                                    "native_token": secret_nested_tok,
                                    "token": secret_err_tok,
                                    "diagnostic": "topological_recompute_diverged",
                                },
                            },
                        },
                    }
                ),
            }
        ],
        "isError": True,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_error_resp)
    mock_desktop_service.submit = AsyncMock(return_value=raw_error_resp)

    # 1. model_snapshot failure
    with pytest.raises(FusionCadError) as exc_info:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "model_snapshot", "detail": "full"},
            group="read",
        )
    err = exc_info.value
    err_details_str = str(err.details)
    err_str = str(err)
    err_repr = repr(err)

    for secret in (secret_native_tok, secret_nested_tok, secret_err_tok):
        assert secret not in err_details_str, (
            f"Leaked {secret} in FusionCadError.details"
        )
        assert secret not in err_str, f"Leaked {secret} in FusionCadError str()"
        assert secret not in err_repr, f"Leaked {secret} in FusionCadError repr()"
        assert secret not in err.message, f"Leaked {secret} in FusionCadError message"

    # Legitimate non-token diagnostics must be preserved
    assert err.code == ErrorCode.REF_STALE
    assert err.message == "Referenced CAD entity is stale or no longer exists"
    assert err.details.get("target") == "ent_face_stale"
    assert (
        err.details.get("nested", {}).get("diagnostic")
        == "topological_recompute_diverged"
    )


class _FakePoint:
    """Minimal point-like object for mutating fake Fusion geometry in inspection tests."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


# =========================================================================
# Task 7: P0 inspection operations
# =========================================================================


def _register_inspect_refs(cad_service, doc="doc_1"):
    refs = {}
    refs["body"] = cad_service.ref_registry.issue(
        document_ref=doc,
        kind="body",
        name="Body1",
        native_token="body_token_1",
    ).ref
    refs["face"] = cad_service.ref_registry.issue(
        document_ref=doc,
        kind="face",
        name="Face0",
        native_token="face_token_0",
    ).ref
    refs["face1"] = cad_service.ref_registry.issue(
        document_ref=doc,
        kind="face",
        name="Face1",
        native_token="face_token_1",
    ).ref
    refs["edge"] = cad_service.ref_registry.issue(
        document_ref=doc,
        kind="edge",
        name="Edge0",
        native_token="edge_token_0",
    ).ref
    refs["sketch"] = cad_service.ref_registry.issue(
        document_ref=doc,
        kind="sketch",
        name="Sketch1",
        native_token="sketch_token_1",
    ).ref
    return refs


def _inspect_matrix():
    return CapabilityMatrix.from_records(
        [CapabilityRecord(name="inspect.measure", state="supported")]
    )


@pytest.mark.asyncio
async def test_fusion_inspect_describe_area_volume_perimeter_centroid(
    mock_desktop_service: DesktopNodeService,
):
    """Proves inspect describe/scalar measures normalize exact units and frames."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # describe body
        res = await cad_service.execute(
            {"node_id": "desk-1", "operation": "describe", "target": refs["body"]},
            group="inspect",
        )
        assert res.status == "succeeded"
        assert res.data["ref"] == refs["body"]
        assert res.data["kind"] == "body"
        assert res.data["frame"]["space"] == "world"
        assert res.data["measures"]["volume"]["unit"] == "mm^3"
        assert res.data["measures"]["volume"]["value"] == pytest.approx(1_000_000.0)
        assert res.data["measures"]["area"]["unit"] == "mm^2"

        # area (body surface area)
        res_area = await cad_service.execute(
            {"node_id": "desk-1", "operation": "area", "target": refs["body"]},
            group="inspect",
        )
        assert res_area.data["quantity"] == "area"
        assert res_area.data["unit"] == "mm^2"
        assert res_area.data["value"] == pytest.approx(5000.0)

        # volume (body)
        res_vol = await cad_service.execute(
            {"node_id": "desk-1", "operation": "volume", "target": refs["body"]},
            group="inspect",
        )
        assert res_vol.data["quantity"] == "volume"
        assert res_vol.data["unit"] == "mm^3"
        assert res_vol.data["value"] == pytest.approx(1_000_000.0)

        # perimeter (face) = 4 edges x 10 mm
        res_per = await cad_service.execute(
            {"node_id": "desk-1", "operation": "perimeter", "target": refs["face"]},
            group="inspect",
        )
        assert res_per.data["quantity"] == "perimeter"
        assert res_per.data["unit"] == "mm"
        assert res_per.data["value"] == pytest.approx(400.0)

        # centroid (body) with explicit frame
        res_cen = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "centroid",
                "target": refs["body"],
                "frame": {"space": "world"},
            },
            group="inspect",
        )
        assert res_cen.data["point"]["frame"]["space"] == "world"
        assert res_cen.data["point"]["x"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_fusion_inspect_bounding_box_oriented_bbox_and_edge(
    mock_desktop_service: DesktopNodeService,
):
    """Proves bounding_box carries explicit frames, body oriented_bbox fails closed
    (the axis-aligned body.boundingBox is never relabeled as an oriented_bbox),
    and edge length is exact."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # bounding_box with world frame
        res_bb = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "bounding_box",
                "target": refs["body"],
                "frame": {"space": "world"},
            },
            group="inspect",
        )
        assert res_bb.data["bounding_box"]["frame"]["space"] == "world"
        assert res_bb.data["bounding_box"]["min_point"]["x"] == 0.0
        assert res_bb.data["bounding_box"]["max_point"]["z"] == 100.0

        # Body oriented_bbox must FAIL CLOSED: this P0 path has no exact
        # Fusion OBB measure API, and the axis-aligned body.boundingBox must
        # never be relabeled as an oriented bounding box.
        with pytest.raises(FusionCadError) as exc_obb:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "oriented_bbox",
                    "target": refs["body"],
                },
                group="inspect",
            )
        assert exc_obb.value.code == ErrorCode.UNSUPPORTED_GEOMETRY

        # edge perimeter/length
        res_edge = await cad_service.execute(
            {"node_id": "desk-1", "operation": "perimeter", "target": refs["edge"]},
            group="inspect",
        )
        assert res_edge.data["unit"] == "mm"
        assert res_edge.data["value"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_fusion_inspect_distance_minimum_distance_and_angle(
    mock_desktop_service: DesktopNodeService,
):
    """Proves distance/minimum_distance return mm with explicit points and angle is deg."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # distance body centroid (5,5,5) -> face0 centroid (0,0,0)
        res_dist = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "distance",
                "target_a": refs["body"],
                "target_b": refs["face"],
            },
            group="inspect",
        )
        assert res_dist.data["quantity"] == "distance"
        assert res_dist.data["unit"] == "mm"
        assert res_dist.data["value"] == pytest.approx(10.0 * math.sqrt(75.0))
        assert res_dist.data["from_point"]["frame"]["space"] == "world"
        assert res_dist.data["to_point"]["frame"]["space"] == "world"

        # minimum_distance
        res_min = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "minimum_distance",
                "target_a": refs["body"],
                "target_b": refs["face"],
            },
            group="inspect",
        )
        assert res_min.data["quantity"] == "minimum_distance"
        assert res_min.data["unit"] == "mm"

        # angle between two coplanar faces (normals (0,0,1) both) -> 0 deg
        res_angle = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "angle",
                "target_a": refs["face"],
                "target_b": refs["face1"],
            },
            group="inspect",
        )
        assert res_angle.data["unit"] == "deg"
        assert res_angle.data["value"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_fusion_inspect_relation_contracts(
    mock_desktop_service: DesktopNodeService,
):
    """Proves parallel/perpendicular/coplanar/concentric return matches, measured deviation, and explicit tolerance."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # face_a normal (0,0,1); face_b normal (0,0,1) -> parallel
        res_par = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "parallel",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_deg": 0.5,
            },
            group="inspect",
        )
        assert res_par.data["relation"] == "parallel"
        assert res_par.data["matches"] is True
        assert res_par.data["measured"]["angle_deg"] == 0.0
        assert res_par.data["tolerance"] == {"value": 0.5, "unit": "deg"}

        # Make face_b normal perpendicular for perpendicular test
        face_b.geometry.normal = _FakePoint(1.0, 0.0, 0.0)
        res_perp = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "perpendicular",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_deg": 0.1,
            },
            group="inspect",
        )
        assert res_perp.data["relation"] == "perpendicular"
        assert res_perp.data["matches"] is True
        assert res_perp.data["measured"]["angle_deg"] == pytest.approx(0.0)
        assert res_perp.data["tolerance"]["unit"] == "deg"

        # Restore face_b normal; both coplanar (same origin/normal)
        face_b.geometry.normal = _FakePoint(0.0, 0.0, 1.0)
        res_cop = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "coplanar",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res_cop.data["relation"] == "coplanar"
        assert res_cop.data["matches"] is True
        assert res_cop.data["measured"]["angle_deg"] == 0.0
        assert res_cop.data["measured"]["distance_mm"] == 0.0
        assert res_cop.data["tolerance"]["unit"] == "mm"

        # Concentric: make both faces circular with shared axis
        face_a.geometry.axis = _FakePoint(0.0, 0.0, 1.0)
        face_a.geometry.center = _FakePoint(5.0, 5.0, 0.0)
        face_a.geometry.radius = 5.0
        face_b.geometry.axis = _FakePoint(0.0, 0.0, 1.0)
        face_b.geometry.center = _FakePoint(5.0, 5.0, 0.0)
        face_b.geometry.radius = 7.0
        res_conc = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res_conc.data["relation"] == "concentric"
        assert res_conc.data["matches"] is True
        assert res_conc.data["measured"]["angle_deg"] == 0.0
        assert res_conc.data["measured"]["offset_mm"] == 0.0
        assert res_conc.data["tolerance"]["unit"] == "mm"
        assert res_conc.data["tolerances"]["angle_deg"] == 0.01
        assert res_conc.data["tolerances"]["offset_mm"] == 0.001


@pytest.mark.asyncio
async def test_fusion_inspect_face_to_face_thickness_exact_only(
    mock_desktop_service: DesktopNodeService,
):
    """Proves face_to_face_thickness returns exact unambiguous thickness and rejects ambiguous geometry."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # Exact thickness: opposing normals with a 5 mm gap
        face_a.geometry.origin = _FakePoint(0.0, 0.0, 0.0)
        face_a.geometry.normal = _FakePoint(0.0, 0.0, 1.0)
        face_b.geometry.origin = _FakePoint(0.0, 0.0, 5.0)
        face_b.geometry.normal = _FakePoint(0.0, 0.0, -1.0)
        res_thick = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "face_to_face_thickness",
                "face_a": refs["face"],
                "face_b": refs["face1"],
            },
            group="inspect",
        )
        assert res_thick.data["quantity"] == "thickness"
        assert res_thick.data["value"] == pytest.approx(50.0)
        assert res_thick.data["unit"] == "mm"
        assert res_thick.data["unambiguous"] is True

        # Ambiguous: parallel same-direction faces do not define wall thickness
        face_b.geometry.normal = _FakePoint(0.0, 0.0, 1.0)
        with pytest.raises(FusionCadError) as exc_amb:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face"],
                    "face_b": refs["face1"],
                },
                group="inspect",
            )
        assert exc_amb.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_unsupported_targets_fail_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves unsupported target types return TYPE_MISMATCH/UNSUPPORTED_GEOMETRY, never guessed values."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # volume on a face -> TYPE_MISMATCH
        with pytest.raises(FusionCadError) as exc_vol:
            await cad_service.execute(
                {"node_id": "desk-1", "operation": "volume", "target": refs["face"]},
                group="inspect",
            )
        assert exc_vol.value.code == ErrorCode.TYPE_MISMATCH

        # perimeter on a body -> TYPE_MISMATCH
        with pytest.raises(FusionCadError) as exc_per:
            await cad_service.execute(
                {"node_id": "desk-1", "operation": "perimeter", "target": refs["body"]},
                group="inspect",
            )
        assert exc_per.value.code == ErrorCode.TYPE_MISMATCH

        # non-world frame request -> UNSUPPORTED_GEOMETRY (exact conversion not fabricated)
        with pytest.raises(FusionCadError) as exc_frame:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "centroid",
                    "target": refs["body"],
                    "frame": {"space": "occurrence", "ref": "ent_occ_1"},
                },
                group="inspect",
            )
        assert exc_frame.value.code == ErrorCode.UNSUPPORTED_GEOMETRY

    # Outside any active design: NO_ACTIVE_DESIGN fail closed
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities("desk-1", _inspect_matrix())
    mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
    with pytest.raises(FusionCadError) as exc_no_doc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "describe", "target": "ent_unknown"},
            group="inspect",
        )
    assert exc_no_doc.value.code == ErrorCode.NO_ACTIVE_DESIGN


# =========================================================================
# Task 7 review findings: native cm -> mm, no heuristic fallbacks,
# conservative thickness, concentric angular+offset
# =========================================================================


@pytest.mark.asyncio
async def test_fusion_inspect_centroid_no_bbox_fallback(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: body centroid must NOT fall back to bounding-box center."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        body.physicalProperties = None  # exact centroid unavailable

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "centroid",
                    "target": refs["body"],
                    "frame": {"space": "world"},
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_sketch_centroid_unsupported(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: sketch centroid must NOT fall back to bounding-box center."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "centroid",
                    "target": refs["sketch"],
                    "frame": {"space": "world"},
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_curved_edge_centroid_unsupported(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: curved-edge centroid must not use endpoint midpoint."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        edge = body.edges.item(0)
        edge.geometry.objectType = "Arc3D"
        edge.geometry.curveType = "Arc3D"

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "centroid",
                    "target": refs["edge"],
                    "frame": {"space": "world"},
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_distance_missing_witness_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: distance must not fall back to centroids when witness points are missing."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0) as fake_adsk:
        fake_adsk.missing_witness = True
        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "distance",
                    "target_a": refs["body"],
                    "target_b": refs["face"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_distance_no_measure_manager_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 2: distance must not fall back to centroid math when measureManager is unavailable."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        app.measureManager = None

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "minimum_distance",
                    "target_a": refs["body"],
                    "target_b": refs["face"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_different_bodies_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 3: thickness requires provably same-solid faces."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)
        face_a.geometry.origin = _FakePoint(0.0, 0.0, 0.0)
        face_a.geometry.normal = _FakePoint(0.0, 0.0, 1.0)
        face_b.geometry.origin = _FakePoint(0.0, 0.0, 5.0)
        face_b.geometry.normal = _FakePoint(0.0, 0.0, -1.0)
        # Different solid -> cannot prove wall thickness
        face_b.body = object()

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face"],
                    "face_b": refs["face1"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_thickness_disjoint_faces_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 3: thickness requires projected overlap proving a material path."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)
        face_a.geometry.origin = _FakePoint(0.0, 0.0, 0.0)
        face_a.geometry.normal = _FakePoint(0.0, 0.0, 1.0)
        face_b.geometry.origin = _FakePoint(0.0, 0.0, 5.0)
        face_b.geometry.normal = _FakePoint(0.0, 0.0, -1.0)
        # Move face_b vertices far away -> no projected overlap -> disjoint
        for vi in range(face_b.vertices.count):
            face_b.vertices.item(vi).geometry = _FakePoint(100.0, 100.0, 5.0)

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "face_to_face_thickness",
                    "face_a": refs["face"],
                    "face_b": refs["face1"],
                },
                group="inspect",
            )
        assert exc.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_non_parallel_axes_reports_angle(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 4: concentric requires angular parallelism within tolerance."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)
        face_a.geometry.axis = _FakePoint(0.0, 0.0, 1.0)
        face_a.geometry.center = _FakePoint(5.0, 5.0, 0.0)
        face_a.geometry.radius = 5.0
        face_b.geometry.axis = _FakePoint(1.0, 0.0, 0.0)
        face_b.geometry.center = _FakePoint(5.0, 5.0, 5.0)
        face_b.geometry.radius = 7.0

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 1.0,
            },
            group="inspect",
        )
        assert res.data["matches"] is False
        assert res.data["measured"]["angle_deg"] == pytest.approx(90.0)
        assert res.data["measured"]["offset_mm"] == pytest.approx(0.0)
        assert res.data["tolerances"]["angle_deg"] == 0.01
        assert res.data["tolerances"]["offset_mm"] == 1.0


@pytest.mark.asyncio
async def test_fusion_inspect_concentric_offset_exceeds_tolerance(
    mock_desktop_service: DesktopNodeService,
):
    """Falsify Finding 4: parallel but offset axes are not concentric."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)
        face_a = body.faces.item(0)
        face_b = body.faces.item(1)
        face_a.geometry.axis = _FakePoint(0.0, 0.0, 1.0)
        face_a.geometry.center = _FakePoint(5.0, 5.0, 0.0)
        face_a.geometry.radius = 5.0
        face_b.geometry.axis = _FakePoint(0.0, 0.0, 1.0)
        face_b.geometry.center = _FakePoint(5.0, 6.0, 0.0)
        face_b.geometry.radius = 7.0

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)
        res = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "concentric",
                "target_a": refs["face"],
                "target_b": refs["face1"],
                "tolerance_deg": 0.01,
                "tolerance_mm": 0.001,
            },
            group="inspect",
        )
        assert res.data["matches"] is False
        assert res.data["measured"]["angle_deg"] == pytest.approx(0.0)
        assert res.data["measured"]["offset_mm"] == pytest.approx(10.0)

@pytest.mark.asyncio
async def test_fusion_inspect_face_oriented_bbox_straight_edges_exact_curved_edge_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    """Proves face oriented_bbox is exact only for positively verified
    straight-edged polygonal boundaries and fails closed for curved edges."""
    async def run_rendered_inspect(node_id, tool_name, arguments, journal=None):
        script = arguments["script"]
        scope = {"__name__": "__main__"}
        exec(compile(script, "<rendered-inspect-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]

    with AdskFakeContext("doc_1", initial_volume=1000.0):
        import adsk.core

        app = adsk.core.Application.get()
        design = app.activeDocument.products.itemByClass("adsk::fusion::Design")
        body = design.rootComponent.bRepBodies.item(0)

        cad_service = FusionCadService(mock_desktop_service)
        cad_service.set_node_capabilities("desk-1", _inspect_matrix())
        mock_desktop_service.call = run_rendered_inspect  # type: ignore[assignment]
        mock_desktop_service.submit = run_rendered_inspect  # type: ignore[assignment]

        refs = _register_inspect_refs(cad_service)

        # Straight-edged polygonal face (4 Line3D edges): exact vertex projection.
        res_obb = await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "oriented_bbox",
                "target": refs["face"],
            },
            group="inspect",
        )
        obb = res_obb.data["oriented_bbox"]
        assert len(obb["axes"]) == 3
        assert obb["extents"] == pytest.approx((50.0, 50.0, 0.0))
        assert obb["frame"]["space"] == "world"
        assert obb["center"]["frame"]["space"] == "world"

        # Curved boundary edge: must fail closed, never a guessed vertex box.
        face_edge = body.faces.item(0).loops.item(0).edges.item(0)
        face_edge.geometry.objectType = "Arc3D"
        face_edge.geometry.curveType = "Arc3D"
        with pytest.raises(FusionCadError) as exc_curved:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "oriented_bbox",
                    "target": refs["face"],
                },
                group="inspect",
            )
        assert exc_curved.value.code == ErrorCode.UNSUPPORTED_GEOMETRY


# =========================================================================
# Task 10: transactional metadata, roles, tags, provenance
# =========================================================================

from app.fusion_cad.metadata import (
    PROVENANCE_ATTRIBUTE_NAME,
    PROVENANCE_CREATOR_TOOL,
    RESERVED_METADATA_GROUP,
    parse_provenance_attribute,
)

_METADATA_MUTATION_OPS = frozenset(
    {"set", "remove", "tag", "untag", "set_role", "clear_role"}
)


def _payload_operation(script: str):
    for line in script.splitlines():
        if line.startswith("PAYLOAD_RAW = "):
            raw = line[len("PAYLOAD_RAW = "):]
            return json.loads(json.loads(raw) if raw.startswith('"') else raw).get(
                "operation"
            )
    return None


class FakeFusionDesktop:
    """fake_desktop: executes rendered production scripts against a fake Fusion
    runtime and counts mutation dispatches separately from read dispatches so the
    one-command geometry+provenance invariant can be proven."""

    def __init__(self, fake_adsk):
        self._fake_adsk = fake_adsk
        self.mutation_calls = 0
        self.read_calls = 0
        self.mutation_primitive = None

    def _dispatch(self, arguments):
        script = arguments["script"]
        op = _payload_operation(script)
        if op in _METADATA_MUTATION_OPS:
            self.mutation_calls += 1
        else:
            self.read_calls += 1
        scope = {"__name__": "__main__"}
        if self.mutation_primitive is not None:
            scope["_mutation_primitive"] = self.mutation_primitive
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        return scope["_output"]


    def get_session_generation(self, node_id):
        return 1
    async def call(self, node_id, tool_name, arguments, journal=None):
        return self._dispatch(arguments)

    async def submit(self, node_id, tool_name, arguments, journal=None):
        return self._dispatch(arguments)


def _enable_fake_attribute_removal(fake_adsk):
    """Teach the fake attribute collections the real Fusion removal API
    (Attribute.deleteMe) so metadata removals are exercised offline."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    if getattr(attrs_cls, "_bridge_remove_patched", False):
        return
    original_add = attrs_cls.add

    def add_with_delete(self, group_name, name, value):
        attr = original_add(self, group_name, name, value)
        items = self._items
        attr.deleteMe = lambda: items.remove(attr)
        return attr

    def remove(self, attr):
        self._items.remove(attr)

    attrs_cls.add = add_with_delete
    attrs_cls.remove = remove
    attrs_cls._bridge_remove_patched = True


def _enable_fake_fusion_add_overwrite(fake_adsk):
    """Teach the fake attribute collections the OFFICIAL Fusion semantics for
    Attributes.add(groupName, name, value): when the owner already has an
    attribute with the same group and name, add UPDATES that existing attribute
    in place and returns the SAME object (no new object is appended). Used only
    by the Fusion-like overwrite rollback regression; the base fake keeps its
    append behavior for the other Task 10 tests."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    if getattr(attrs_cls, "_bridge_fusion_overwrite_patched", False):
        return
    base_add = attrs_cls.add

    def add_with_fusion_overwrite(self, group_name, name, value):
        for i in range(self.count):
            existing = self.item(i)
            if (
                getattr(existing, "groupName", None) == group_name
                and getattr(existing, "name", None) == name
            ):
                existing.value = value
                return existing
        return base_add(self, group_name, name, value)

    attrs_cls.add = add_with_fusion_overwrite
    attrs_cls._bridge_fusion_overwrite_patched = True


@pytest.fixture
def fake_desktop():
    """Yields {"adsk": fake_adsk, "desktop": FakeFusionDesktop} inside a fake Fusion runtime."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        _enable_fake_attribute_removal(fake_adsk)
        yield {"adsk": fake_adsk, "desktop": FakeFusionDesktop(fake_adsk)}


def _metadata_matrix():
    return CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="metadata.attributes", state="supported"),
            CapabilityRecord(name="design.access", state="supported"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )


def _register_body_ref(cad_service, doc="doc_1"):
    return cad_service.ref_registry.issue(
        document_ref=doc,
        kind="body",
        name="Body1",
        native_token="body_token_1",
    ).ref


def _document_attributes():
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs = doc.attributes
    return {
        (attrs.item(i).groupName, attrs.item(i).name): attrs.item(i).value
        for i in range(attrs.count)
    }


def _body_attributes():
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    design = doc.products.itemByClass("adsk::fusion::Design")
    body = design.rootComponent.bRepBodies.item(0)
    attrs = body.attributes
    return {
        (attrs.item(i).groupName, attrs.item(i).name): attrs.item(i).value
        for i in range(attrs.count)
    }


def _seed_unrelated_attributes(fake_adsk):
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    doc.attributes.add("vendor.custom", "color", "blue")
    doc.attributes.add("bridge.cad/v1", "user_note", "keepme")


async def _seed_baseline(cad_service, desktop):
    """Seed the revision baseline from a real semantic read (never a synthetic fingerprint)."""
    snap = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
    )
    assert isinstance(snap, CadResult)
    return cad_service.revision_tracker.current("doc_1").revision


@pytest.mark.asyncio
async def test_geometry_and_provenance_use_one_mutation_command(fake_desktop):
    """Geometry change + provenance + tag metadata are applied by exactly ONE
    mutation command; no hidden post-commit metadata command may follow."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    desktop.mutation_primitive = lambda payload: setattr(
        fake_adsk, "volume", float(fake_adsk.volume) + 25.0
    )

    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    # Semantic read seeds the revision baseline (a read dispatch, not a mutation)
    snap = await cad_service.execute(
        {"node_id": "desk-1", "operation": "model_snapshot"}, group="read"
    )
    assert isinstance(snap, CadResult)
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"
    assert desktop.mutation_calls == 0
    assert desktop.read_calls == 1

    body_ref = _register_body_ref(cad_service)

    # ONE command must apply the geometry change AND provenance + tag metadata
    res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    res_data = res.data if isinstance(res, CadResult) else res["data"]

    assert desktop.mutation_calls == 1, (
        "geometry + provenance must be applied by one mutation command"
    )
    assert desktop.read_calls == 1, "no hidden post-commit metadata command may follow"
    # Geometry changed inside that same single command
    assert fake_adsk.volume == 125.0

    # Metadata + provenance are persisted on the exactly resolved entity owner;
    # the document owner never receives them (no document fallback).
    attrs = _body_attributes()
    assert attrs.get(("bridge.cad/v1", "tag:layout")) == "schedule"
    provenance_value = attrs.get(("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME))
    assert provenance_value
    provenance = parse_provenance_attribute(provenance_value)
    assert provenance.creator_tool == PROVENANCE_CREATOR_TOOL
    assert provenance.creator_operation == "fusion_metadata:tag"
    assert provenance.operation_id.startswith("op_")
    # created_revision truthfully records the revision the changed entity
    # exists in (the post-mutation revision), not the pre-mutation expected one
    assert provenance.created_revision == "rev_2"
    assert [(t.name, t.value) for t in provenance.tags] == [("layout", "schedule")]
    document_attrs = _document_attributes()
    assert ("bridge.cad/v1", "tag:layout") not in document_attrs
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in document_attrs

    # Result echoes the transactional provenance and advances the revision
    assert res_data.get("applied") is True
    assert res_data.get("provenance", {}).get("creator_operation") == "fusion_metadata:tag"
    doc_state = res.document if isinstance(res, CadResult) else res["document"]
    assert doc_state.model_revision == "rev_2"
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"


@pytest.mark.asyncio
async def test_metadata_set_remove_preserves_unrelated_fusion_attributes(fake_desktop):
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    _seed_unrelated_attributes(fake_adsk)

    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)

    body_ref = _register_body_ref(cad_service)

    res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "set",
            "target": body_ref,
            "name": "finish",
            "value": {"roughness": 0.4, "coating": "anodized"},
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    res_data = res.data if isinstance(res, CadResult) else res["data"]
    assert res_data.get("applied") is True
    body_attrs = _body_attributes()
    assert json.loads(body_attrs.get(("bridge.cad/v1", "finish"))) == {
        "roughness": 0.4,
        "coating": "anodized",
    }
    # Provenance persisted on the same target inside the same command
    assert body_attrs.get(("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME))
    # Unrelated Fusion attributes preserved untouched
    assert _document_attributes().get(("vendor.custom", "color")) == "blue"
    assert _document_attributes().get(("bridge.cad/v1", "user_note")) == "keepme"

    # remove removes only the named reserved-namespace key on that owner
    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "remove",
            "target": body_ref,
            "name": "finish",
            "expected_revision": "rev_2",
        },
        group="metadata",
    )
    body_attrs = _body_attributes()
    assert ("bridge.cad/v1", "finish") not in body_attrs
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) in body_attrs
    assert _document_attributes().get(("vendor.custom", "color")) == "blue"
    assert _document_attributes().get(("bridge.cad/v1", "user_note")) == "keepme"
    assert desktop.mutation_calls == 2


@pytest.mark.asyncio
async def test_metadata_get_query_provenance_roundtrip_readonly(fake_desktop):
    desktop = fake_desktop["desktop"]

    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "transaction_id": "tx_layout_9",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    mutations_so_far = desktop.mutation_calls

    # get is read-only and never requires expected_revision
    res_get = await cad_service.execute(
        {"node_id": "desk-1", "operation": "get", "target": body_ref},
        group="metadata",
    )
    data_get = res_get.data if isinstance(res_get, CadResult) else res_get["data"]
    by_name = {r["name"]: r["value"] for r in data_get.get("records", [])}
    assert by_name.get("tag:layout") == "schedule"
    assert data_get.get("count") == len(data_get.get("records", []))
    assert desktop.mutation_calls == mutations_so_far

    # query filters persisted records by name/value
    res_query = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "query",
            "name": "tag:layout",
            "value": "schedule",
        },
        group="metadata",
    )
    data_query = (
        res_query.data if isinstance(res_query, CadResult) else res_query["data"]
    )
    assert data_query.get("count") == 1

    res_miss = await cad_service.execute(
        {"node_id": "desk-1", "operation": "query", "name": "tag:missing"},
        group="metadata",
    )
    data_miss = res_miss.data if isinstance(res_miss, CadResult) else res_miss["data"]
    assert data_miss.get("count") == 0
    assert desktop.mutation_calls == mutations_so_far

    # provenance op returns the persisted provenance record
    res_prov = await cad_service.execute(
        {"node_id": "desk-1", "operation": "provenance", "target": body_ref},
        group="metadata",
    )
    data_prov = res_prov.data if isinstance(res_prov, CadResult) else res_prov["data"]
    prov = data_prov.get("provenance")
    assert prov["creator_operation"] == "fusion_metadata:tag"
    assert prov["transaction_id"] == "tx_layout_9"
    # Truthful post-mutation revision (the tag mutation advanced rev_1 -> rev_2)
    assert prov["created_revision"] == "rev_2"
    assert desktop.mutation_calls == mutations_so_far

    # Foreign groups are rejected for reads too: Bridge reads only its namespace
    with pytest.raises(FusionCadError) as exc_foreign:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "get",
                "target": body_ref,
                "group": "vendor.custom",
            },
            group="metadata",
        )
    assert exc_foreign.value.code == ErrorCode.INVALID_ARGUMENT
    assert desktop.mutation_calls == mutations_so_far


@pytest.mark.asyncio
async def test_metadata_role_set_clear_and_stale_conflict_preserves_attributes(
    fake_desktop,
):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "set_role",
            "target": body_ref,
            "role": "mounting_bracket",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    assert _body_attributes().get(("bridge.cad/v1", "role")) == "mounting_bracket"

    # clear_role with a non-matching role value must not clear the existing role
    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "clear_role",
            "target": body_ref,
            "role": "decorative_text",
            "expected_revision": "rev_2",
        },
        group="metadata",
    )
    assert _body_attributes().get(("bridge.cad/v1", "role")) == "mounting_bracket"

    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "clear_role",
            "target": body_ref,
            "expected_revision": "rev_3",
        },
        group="metadata",
    )
    assert ("bridge.cad/v1", "role") not in _body_attributes()

    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_4",
        },
        group="metadata",
    )
    mutations_so_far = desktop.mutation_calls

    # External model change advances the observed revision; stale untag is blocked
    cad_service.revision_tracker.observe("doc_1", "diverged-fp")
    with pytest.raises(FusionCadError) as exc_stale:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "untag",
                "target": body_ref,
                "tag_name": "layout",
                "expected_revision": "rev_4",
            },
            group="metadata",
        )
    assert exc_stale.value.code == ErrorCode.REVISION_CONFLICT
    assert _body_attributes().get(("bridge.cad/v1", "tag:layout")) == "schedule"
    assert desktop.mutation_calls == mutations_so_far


@pytest.mark.asyncio
async def test_role_tag_provenance_selectors_read_persisted_model_attributes(
    fake_desktop,
):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "set_role",
            "target": body_ref,
            "role": "mounting_bracket",
            "expected_revision": "rev_2",
        },
        group="metadata",
    )

    # Metadata query returns candidates carrying PERSISTED model attributes
    res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "query"}, group="metadata"
    )
    data = res.data if isinstance(res, CadResult) else res["data"]
    candidates = data.get("candidates", [])
    assert data.get("candidate_count") == 1
    assert candidates[0]["ref"] == body_ref
    attr_names = {r["name"] for r in candidates[0]["attributes"]}
    assert {"tag:layout", "role", PROVENANCE_ATTRIBUTE_NAME}.issubset(attr_names)

    # Selector engine resolves role/tag/provenance from those persisted attributes
    engine = cad_service.selector_engine
    assert engine.query(
        {"tag": {"group": RESERVED_METADATA_GROUP, "name": "layout", "value": "schedule"}},
        candidates,
    ).refs == (body_ref,)
    assert engine.query({"role": "mounting_bracket"}, candidates).refs == (body_ref,)
    assert engine.query(
        {"created_by": {"tool": PROVENANCE_CREATOR_TOOL}}, candidates
    ).refs == (body_ref,)
    assert engine.query({"tag": {"name": "missing"}}, candidates).matched_count == 0


# =========================================================================
# Task 10 Codex-blocker repair regressions (integration, rendered scripts)
# =========================================================================

import re as _re

from app.fusion_cad.metadata import (
    apply_geometry_provenance_plan,
    apply_metadata_mutation_plan,
)
from app.fusion_cad.scripts import FusionCadScriptBundle


def _body_attr_count():
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    design = doc.products.itemByClass("adsk::fusion::Design")
    body = design.rootComponent.bRepBodies.item(0)
    return body.attributes.count


def _exec_rendered_mutate(script: str, mutation_primitive=None):
    scope = {"__name__": "__main__"}
    if mutation_primitive is not None:
        scope["_mutation_primitive"] = mutation_primitive
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    return scope["_output"]


@pytest.mark.asyncio
async def test_metadata_unknown_stale_or_foreign_target_fails_closed_before_dispatch(
    fake_desktop,
):
    """Blocker 2: unknown/stale/cross-document opaque metadata targets fail
    closed BEFORE dispatch; metadata is never silently applied to the document
    owner while echoing an entity ref."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    assert desktop.mutation_calls == 0
    assert desktop.read_calls == 1
    baseline_doc_attrs = _document_attributes()
    baseline_body_attrs = _body_attributes()

    # 1. Unknown opaque ref -> REF_STALE, zero dispatches, zero writes
    with pytest.raises(FusionCadError) as exc_unknown:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": "ent_never_registered",
                "name": "finish",
                "value": "anodized",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_unknown.value.code == ErrorCode.REF_STALE
    assert desktop.mutation_calls == 0
    assert desktop.read_calls == 1
    assert _document_attributes() == baseline_doc_attrs
    assert _body_attributes() == baseline_body_attrs

    # 2. Cross-document opaque ref -> WRONG_DOCUMENT (never document fallback)
    foreign_ref = cad_service.ref_registry.issue(
        document_ref="doc_foreign",
        kind="body",
        name="Body1",
        native_token="foreign_body_token",
    ).ref
    with pytest.raises(FusionCadError) as exc_foreign:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": foreign_ref,
                "name": "finish",
                "value": "anodized",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_foreign.value.code == ErrorCode.WRONG_DOCUMENT
    assert desktop.mutation_calls == 0
    assert _body_attributes() == baseline_body_attrs

    # 3. Reads fail closed too: no silent document-scoped fallback for reads
    with pytest.raises(FusionCadError) as exc_read:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "get",
                "target": "ent_never_registered",
            },
            group="metadata",
        )
    assert exc_read.value.code == ErrorCode.REF_STALE
    assert desktop.mutation_calls == 0
    assert desktop.read_calls == 1

    # 4. The registered ref still resolves exactly and applies normally
    res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    res_data = res.data if isinstance(res, CadResult) else res["data"]
    assert res_data.get("applied") is True
    assert _body_attributes().get(("bridge.cad/v1", "tag:layout")) == "schedule"


@pytest.mark.asyncio
async def test_metadata_mutation_compensates_partial_metadata_after_late_failure(
    fake_desktop,
):
    """Blocker 1: a failure AFTER attribute writes (post-apply fingerprint
    collection explodes) must restore the exact pre-mutation metadata state and
    is never externally reported as success. Geometry has no verified undo
    primitive, so the geometry change of the same failed command is retained —
    the command still fails closed and is never reported as applied."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    desktop.mutation_primitive = lambda payload: setattr(
        fake_adsk, "volume", float(fake_adsk.volume) + 25.0
    )
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    import adsk.core

    doc = adsk.core.Application.get().activeDocument

    class _ExplodesOnSecondFingerprint:
        """First fingerprint read (pre-guard) succeeds; the post-apply read explodes."""

        def __init__(self):
            self._reads = 0

        def __bool__(self):
            self._reads += 1
            if self._reads >= 2:
                raise RuntimeError("post-apply fingerprint collection exploded")
            return False

    doc.isModified = _ExplodesOnSecondFingerprint()

    baseline_body_attrs = _body_attributes()
    baseline_body_attr_count = _body_attr_count()

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "finish",
                "value": "anodized",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    # Never externally reported as success
    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    assert desktop.mutation_calls == 1
    # Partial metadata is compensated: the owner is exactly back to baseline
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count
    # Document owner never received the metadata either
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _document_attributes()


@pytest.mark.asyncio
async def test_metadata_rollback_restores_overwritten_existing_attributes(
    fake_desktop,
):
    """Critical (job_a050be6afa584741a63e739b5f29e4cb): under real Autodesk
    Fusion semantics, Attributes.add(groupName, name, value) UPDATES and returns
    the EXISTING same-group/same-name attribute instead of creating a new one.
    The undo log must therefore distinguish a newly-created write (undone via
    deleteMe) from an overwritten-existing write (undone by restoring the old
    value) so a late failure restores the exact original reserved-namespace
    state instead of deleting pre-existing provenance/metadata."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    # 1. First successful set creates "finish" + provenance on the body owner.
    res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "set",
            "target": body_ref,
            "name": "finish",
            "value": "old-finish",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    res_data = res.data if isinstance(res, CadResult) else res["data"]
    assert res_data.get("applied") is True
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"

    # 2. Model the OFFICIAL Fusion add semantics from here on: a same
    # group+name add updates the existing attribute object in place.
    _enable_fake_fusion_add_overwrite(fake_adsk)

    baseline_body_attrs = _body_attributes()
    baseline_body_attr_count = _body_attr_count()
    assert baseline_body_attrs[("bridge.cad/v1", "finish")] == "old-finish"
    baseline_provenance = baseline_body_attrs[
        ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME)
    ]
    assert baseline_provenance

    import adsk.core

    doc = adsk.core.Application.get().activeDocument

    class _ExplodesOnSecondFingerprint:
        """First fingerprint read (pre-guard) succeeds; the post-apply read
        explodes, so the failure lands AFTER the plan overwrote the existing
        attributes."""

        def __init__(self):
            self._reads = 0

        def __bool__(self):
            self._reads += 1
            if self._reads >= 2:
                raise RuntimeError("post-apply fingerprint collection exploded")
            return False

    doc.isModified = _ExplodesOnSecondFingerprint()

    # 3. Re-set the SAME attribute name: the plan OVERWRITES the existing
    # "finish" and provenance attributes (Fusion add semantics), then the
    # post-apply fingerprint failure must compensate the whole plan.
    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "finish",
                "value": "anodized",
                "expected_revision": "rev_2",
            },
            group="metadata",
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR

    # 4. The exact original reserved-namespace state is restored: old values
    # back, no pre-existing attribute deleted, no phantom duplicates.
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count

    # 5. A healthy retry of the same overwrite succeeds, updates the existing
    # attributes in place (never duplicating), and records fresh provenance.
    doc.isModified = False
    retry = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "set",
            "target": body_ref,
            "name": "finish",
            "value": "anodized",
            "expected_revision": "rev_2",
        },
        group="metadata",
    )
    retry_data = retry.data if isinstance(retry, CadResult) else retry["data"]
    assert retry_data.get("applied") is True
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_3"
    attrs_after = _body_attributes()
    assert attrs_after[("bridge.cad/v1", "finish")] == "anodized"
    assert (
        attrs_after[("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME)]
        != baseline_provenance
    )
    assert _body_attr_count() == baseline_body_attr_count


@pytest.mark.asyncio
async def test_metadata_mid_plan_write_failure_leaves_no_partial_metadata(
    fake_desktop,
):
    """Blocker 1: a mid-plan attribute-write failure must compensate the writes
    already applied so zero partial metadata remains and the command fails."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    original_add = attrs_cls.add

    def add_exploding_on_provenance(self, group_name, name, value):
        if name == PROVENANCE_ATTRIBUTE_NAME:
            raise RuntimeError("simulated mid-plan attribute write failure")
        return original_add(self, group_name, name, value)

    attrs_cls.add = add_exploding_on_provenance
    try:
        baseline_body_attrs = _body_attributes()
        baseline_body_attr_count = _body_attr_count()
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {
                    "node_id": "desk-1",
                    "operation": "set",
                    "target": body_ref,
                    "name": "finish",
                    "value": "anodized",
                    "expected_revision": "rev_1",
                },
                group="metadata",
            )
        assert exc.value.code == ErrorCode.FUSION_API_ERROR
        assert _body_attributes() == baseline_body_attrs
        assert _body_attr_count() == baseline_body_attr_count
        assert desktop.mutation_calls == 1
    finally:
        attrs_cls.add = original_add


@pytest.mark.asyncio
async def test_metadata_geometry_hook_failure_applies_no_metadata(fake_desktop):
    """Blocker 1: the geometry primitive runs BEFORE any metadata write, so a
    geometry failure leaves zero Bridge metadata behind."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]

    def _geometry_explodes(payload):
        raise RuntimeError("geometry primitive exploded")

    desktop.mutation_primitive = _geometry_explodes
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_body_attrs = _body_attributes()
    baseline_doc_attrs = _document_attributes()

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "finish",
                "value": "anodized",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    assert fake_adsk.volume == 100.0
    assert _body_attributes() == baseline_body_attrs
    assert _document_attributes() == baseline_doc_attrs


@pytest.mark.asyncio
async def test_metadata_provenance_uses_durable_command_operation_id(fake_desktop):
    """Blocker 3: the persisted provenance record and the desktop operation
    journal share the SAME durable command operation_id, and created_revision
    truthfully records the post-mutation revision."""
    desktop = fake_desktop["desktop"]
    captured = {}
    inner_submit = desktop.submit

    async def capturing_submit(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        return await inner_submit(node_id, tool_name, arguments, journal=journal)

    desktop.submit = capturing_submit
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    # recipe / logical_object_ref travel at the domain plan layer (supplied by
    # later recipe-driven flows, not by the strict public metadata request
    # schema); the public command still proves the durable operation id share.
    payload_plan_probe = {
        "operation": "tag",
        "tag_name": "layout",
        "tag_value": "schedule",
        "expected_revision": "rev_1",
        "recipe": "name_plate/v1",
        "logical_object_ref": "text_schedule_01",
    }
    apply_metadata_mutation_plan(
        payload_plan_probe,
        operation_id="op_probe_recipe_1",
        created_revision=cad_service.revision_tracker.next_revision("doc_1"),
    )
    assert payload_plan_probe["provenance"]["recipe"] == "name_plate/v1"
    assert payload_plan_probe["provenance"]["logical_object_ref"] == "text_schedule_01"

    res = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "tag",
            "target": body_ref,
            "tag_name": "layout",
            "tag_value": "schedule",
            "expected_revision": "rev_1",
        },
        group="metadata",
    )
    res_data = res.data if isinstance(res, CadResult) else res["data"]
    assert res_data.get("applied") is True

    journal = captured.get("journal")
    assert isinstance(journal, dict)
    persisted = _body_attributes()[
        (RESERVED_METADATA_GROUP, PROVENANCE_ATTRIBUTE_NAME)
    ]
    provenance = parse_provenance_attribute(persisted)
    # Same durable command operation id in journal and provenance
    assert journal.get("operation_id") == provenance.operation_id
    assert _re.fullmatch(r"op_[A-Za-z0-9._-]+", provenance.operation_id)
    # Truthful post-mutation revision (the mutation advanced rev_1 -> rev_2)
    assert provenance.created_revision == "rev_2"
    assert provenance.created_revision != "rev_1"


@pytest.mark.asyncio
async def test_geometry_mutation_script_applies_same_command_provenance_plan(
    fake_desktop,
):
    """Blocker 4: the common safe path — a non-metadata mutate command carries
    the provenance payload and applies it in the SAME script execution that
    changes geometry, with no second command. Later Task 11 geometry features
    reuse exactly this path."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    desktop.mutation_primitive = lambda payload: setattr(
        fake_adsk, "volume", float(fake_adsk.volume) + 10.0
    )
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    tracker = cad_service.revision_tracker
    rec = tracker.current("doc_1")
    assert rec.revision == "rev_1"

    payload = {
        "operation": "show",
        "target": {
            "ref": body_ref,
            "kind": "body",
            "name": "Body1",
            "native_token": "body_token_1",
            "component_path": [],
        },
        "expected_revision": rec.revision,
        "expected_fingerprint": rec.fingerprint,
        "document_ref": "doc_1",
    }
    apply_geometry_provenance_plan(
        payload,
        operation="show",
        creator_operation="fusion_style:show",
        operation_id="op_geo_command_1",
        created_revision=tracker.next_revision("doc_1"),
    )
    script = FusionCadScriptBundle().build("mutate", payload)
    output = _exec_rendered_mutate(script, desktop.mutation_primitive)

    # The same single execution applied the geometry change AND the provenance
    assert output["status"] == "succeeded"
    assert output["data"]["applied"] is True
    assert output["data"]["provenance"]["operation_id"] == "op_geo_command_1"
    assert fake_adsk.volume == 110.0
    persisted = _body_attributes()[
        (RESERVED_METADATA_GROUP, PROVENANCE_ATTRIBUTE_NAME)
    ]
    provenance = parse_provenance_attribute(persisted)
    assert provenance.operation_id == "op_geo_command_1"
    assert provenance.creator_operation == "fusion_style:show"
    assert provenance.created_revision == "rev_2"
    # No separate metadata mutation command was ever dispatched
    assert desktop.mutation_calls == 0
    assert desktop.read_calls == 1


@pytest.mark.asyncio
async def test_mutate_script_never_falls_back_to_document_owner_for_unresolved_target(
    fake_desktop,
):
    """Blocker 2 (script-side defense in depth): a raw unresolved entity ref and
    a hint without a native token must never be mapped onto the document owner,
    even when the rendered script is executed directly."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    tracker = cad_service.revision_tracker
    rec = tracker.current("doc_1")
    bundle = FusionCadScriptBundle()

    for bad_target in ("ent_unregistered_raw", {"ref": "ent_hint_without_token"}):
        payload = {
            "operation": "set",
            "target": bad_target,
            "name": "finish",
            "value": "anodized",
            "expected_revision": rec.revision,
            "expected_fingerprint": rec.fingerprint,
            "document_ref": "doc_1",
        }
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_script_defense_1",
            created_revision=tracker.next_revision("doc_1"),
        )
        script = bundle.build("mutate", payload)
        output = _exec_rendered_mutate(script)

        assert output["status"] == "failed", f"target {bad_target!r} must fail closed"
        assert output["error"]["code"] == "REF_STALE"
        # The document owner never received metadata while echoing the entity ref
        assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _document_attributes()
        assert ("bridge.cad/v1", "finish") not in _document_attributes()

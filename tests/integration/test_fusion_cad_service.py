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
from app.fusion_cad.providers import FusionCadProviderRouter
from app.fusion_cad.service import FusionCadService
from app.fusion_cad.transactions import TransactionState
from app.settings import BridgeSettings, DesktopNodeSettings


@pytest.mark.asyncio
async def test_validate_run_normalizes_raw_evidence_without_advancing_revision(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [CapabilityRecord(name="design.access", state="supported")]
        ),
    )
    cad_service.revision_tracker.observe("doc_1", "fingerprint-before")
    before = cad_service.revision_tracker.current("doc_1")
    mock_desktop_service.submit = AsyncMock(
        return_value={
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Validation evidence collected",
            "data": {
                "document_ref": "doc_1",
                "features": [
                    {
                        "kind": "feature",
                        "name": "BrokenFeature",
                        "native_token": "native-feature-secret",
                        "valid": False,
                        "health": "error",
                    }
                ],
                "timeline": {"available": True, "rolled_back": False},
            },
        }
    )

    result = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "run",
            "profiles": ["pre_mutation"],
        },
        group="validate",
    )

    assert isinstance(result, CadResult)
    assert result.validation is not None
    assert result.validation["verdict"] == "RED"
    assert result.data["read_only"] is True
    assert "native-feature-secret" not in result.model_dump_json()
    assert cad_service.revision_tracker.current("doc_1") == before
    assert mock_desktop_service.submit.call_args.kwargs["journal"]["mutation"] is False


@pytest.mark.asyncio
async def test_validate_rejects_non_p0_profile_before_dispatch(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [CapabilityRecord(name="design.access", state="supported")]
        ),
    )

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "run", "profiles": ["future_profile"]},
            group="validate",
        )

    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    assert mock_desktop_service.submit.call_count == 0


@pytest.fixture
def mock_desktop_service() -> DesktopNodeService:
    service = MagicMock(spec=DesktopNodeService)
    service.call = AsyncMock()
    service.submit = AsyncMock()
    service.store_external_result = MagicMock()
    return service


def test_task13_service_owns_isolated_transaction_store(
    mock_desktop_service: DesktopNodeService,
):
    first = FusionCadService(mock_desktop_service)
    second = FusionCadService(mock_desktop_service)
    first.transaction_store.begin("tx_local", "doc_1", "rev_1", "fp_1", {})
    assert first.transaction_store.get("tx_local").document_ref == "doc_1"
    with pytest.raises(FusionCadError):
        second.transaction_store.get("tx_local")


@pytest.mark.asyncio
async def test_service_executes_capabilities_read_and_persists_matrix(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    mock_desktop_service.tools.return_value = {
        "tools": [{
            "name": "fusion_mcp_execute",
            "input_schema": {"properties": {"featureType": {}, "object": {}}},
        }]
    }

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

    dispatched = mock_desktop_service.call.call_args.args
    assert dispatched[1] == "fusion_mcp_execute"
    assert dispatched[2]["featureType"] == "script"
    assert dispatched[2]["object"]["script"]
    assert "script" not in {k for k in dispatched[2] if k != "object"}
    payload_line = next(
        line for line in dispatched[2]["object"]["script"].splitlines()
        if line.startswith("PAYLOAD_RAW = ")
    )
    transport_payload = json.loads(json.loads(payload_line[len("PAYLOAD_RAW = "):]))
    assert transport_payload["_bridge_result_transport"] == "fusion_mcp_exception_v1"


@pytest.mark.asyncio
async def test_capabilities_read_overlays_degraded_hands_for_configured_rich_provider(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "desk-1": {
                    "reference_node": "desk-1",
                    "rich_node": "rich-1",
                }
            }
        }
    })
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Runtime capabilities probed",
                    "data": {
                        "application": "Autodesk Fusion",
                        "fusion_version": "2.0.18000",
                        "probe_facts": {
                            "has_app": True,
                            "has_design_access": True,
                            "has_entity_token_resolver": True,
                        },
                    },
                    "capabilities": [
                        {"name": "design.access", "state": "supported"},
                        {"name": "entity.token_resolver", "state": "supported"},
                    ],
                }),
            }],
            "isError": False,
        }
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"},
        group="read",
    )

    assert isinstance(result, CadResult)
    returned = {record.name: record for record in result.capabilities or ()}
    assert returned["hands.sketch"].state == "degraded"
    assert returned["hands.feature"].state == "degraded"
    saved = cad_service.get_node_capabilities("desk-1")
    assert saved is not None
    assert saved.get("hands.sketch").state == "degraded"
    assert saved.get("hands.feature").state == "degraded"


@pytest.mark.asyncio
async def test_capabilities_read_strips_incoming_hands_records_without_rich_provider(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Runtime capabilities probed",
                    "data": {
                        "application": "Autodesk Fusion",
                        "fusion_version": "2.0.18000",
                        "probe_facts": {
                            "has_app": True,
                            "has_design_access": True,
                            "has_entity_token_resolver": True,
                        },
                    },
                    "capabilities": [
                        {"name": "design.access", "state": "supported"},
                        {"name": "hands.sketch", "state": "supported"},
                        {"name": "hands.feature", "state": "supported"},
                    ],
                }),
            }],
            "isError": False,
        }
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )

    assert isinstance(result, CadResult)
    returned = {record.name: record for record in result.capabilities or ()}
    assert "hands.sketch" not in returned
    assert "hands.feature" not in returned
    saved = cad_service.get_node_capabilities("desk-1")
    assert saved is not None
    assert saved.get("hands.sketch") is None
    assert saved.get("hands.feature") is None


@pytest.mark.asyncio
async def test_capabilities_read_downgrades_incoming_hands_records_until_live_qualification(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "desk-1": {
                    "reference_node": "desk-1",
                    "rich_node": "rich-1",
                }
            }
        }
    })
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Runtime capabilities probed",
                    "data": {
                        "application": "Autodesk Fusion",
                        "fusion_version": "2.0.18000",
                        "probe_facts": {
                            "has_app": True,
                            "has_design_access": True,
                            "has_entity_token_resolver": True,
                        },
                    },
                    "capabilities": [
                        {"name": "design.access", "state": "supported"},
                        {"name": "hands.sketch", "state": "supported"},
                        {"name": "hands.feature", "state": "supported"},
                    ],
                }),
            }],
            "isError": False,
        }
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )

    assert isinstance(result, CadResult)
    hands = [record for record in result.capabilities or () if record.name.startswith("hands.")]
    assert [record.name for record in hands] == ["hands.sketch", "hands.feature"]
    assert all(record.state == "degraded" for record in hands)
    saved = cad_service.get_node_capabilities("desk-1")
    assert saved is not None
    assert saved.get("hands.sketch").state == "degraded"
    assert saved.get("hands.feature").state == "degraded"


@pytest.mark.asyncio
async def test_capabilities_read_uses_reference_node_generation_for_logical_provider_route(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "logical-a": {
                    "reference_node": "reference-a",
                    "rich_node": "rich-a",
                }
            }
        }
    })
    generations = {"logical-a": 99, "reference-a": 7, "rich-a": 3}
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: generations[node_id]
    )
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Runtime capabilities probed",
                    "data": {
                        "application": "Autodesk Fusion",
                        "fusion_version": "2.0.18000",
                        "probe_facts": {
                            "has_app": True,
                            "has_design_access": True,
                            "has_entity_token_resolver": True,
                        },
                    },
                    "capabilities": [
                        {"name": "design.access", "state": "supported"},
                        {"name": "entity.token_resolver", "state": "supported"},
                    ],
                }),
            }],
            "isError": False,
        }
    )
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )

    await cad_service.execute(
        {"node_id": "logical-a", "operation": "capabilities"},
        group="read",
    )

    assert mock_desktop_service.call.call_args.args[0] == "reference-a"
    assert cad_service.get_node_capabilities("logical-a") is not None
    generations["reference-a"] = 8
    assert cad_service.get_node_capabilities("logical-a") is None


@pytest.mark.asyncio
async def test_routed_capability_probe_discovers_transport_schema_on_reference_node(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "logical-a": {
                    "reference_node": "reference-a",
                    "rich_node": "rich-a",
                }
            }
        }
    })
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    mock_desktop_service.tools = MagicMock(
        side_effect=lambda node_id: {
            "tools": [{
                "name": "fusion_mcp_execute",
                "input_schema": {
                    "properties": {"featureType": {}, "object": {}}
                },
            }]
        }
        if node_id == "reference-a"
        else {"tools": []}
    )
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: {"reference-a": 7, "rich-a": 3}[node_id]
    )
    mock_desktop_service.call = AsyncMock(
        return_value={
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "api_version": "fusion.cad/v1",
                    "status": "succeeded",
                    "summary": "Runtime capabilities probed",
                    "data": {
                        "application": "Autodesk Fusion",
                        "fusion_version": "2.0.18000",
                        "probe_facts": {
                            "has_app": True,
                            "has_design_access": True,
                            "has_entity_token_resolver": True,
                        },
                    },
                    "capabilities": [
                        {"name": "design.access", "state": "supported"},
                        {"name": "entity.token_resolver", "state": "supported"},
                    ],
                }),
            }],
            "isError": False,
        }
    )

    await cad_service.execute(
        {"node_id": "logical-a", "operation": "capabilities"}, group="read"
    )

    mock_desktop_service.tools.assert_called_once_with("reference-a")
    dispatched = mock_desktop_service.call.call_args.args
    assert dispatched[0] == "reference-a"
    payload_line = next(
        line for line in dispatched[2]["object"]["script"].splitlines()
        if line.startswith("PAYLOAD_RAW = ")
    )
    transport_payload = json.loads(json.loads(payload_line[len("PAYLOAD_RAW = "):]))
    assert transport_payload["_bridge_result_transport"] == "fusion_mcp_exception_v1"



@pytest.mark.asyncio
async def test_hands_provider_policy_ignores_reference_qualification_flags_and_promotes_only_bridge_owned_session(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {"provider_routes": {"desk-1": {
            "reference_node": "desk-1", "rich_node": "rich-1"
        }}}
    })
    generations = {"desk-1": 4, "rich-1": 9}
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: generations[node_id]
    )
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    raw = {
        "content": [{"type": "text", "text": json.dumps({
            "api_version": "fusion.cad/v1", "status": "succeeded",
            "summary": "Runtime capabilities probed",
            "data": {
                "application": "Autodesk Fusion",
                "probe_facts": {
                    "has_app": True,
                    "has_design_access": True,
                    "has_entity_token_resolver": True,
                    "hands_runtime_verified": True,
                    "hands_sketch_runtime_verified": True,
                    "hands_feature_runtime_verified": True,
                },
            },
            "capabilities": [{"name": "design.access", "state": "supported"}],
        })}], "isError": False,
    }
    mock_desktop_service.call = AsyncMock(return_value=raw)

    before = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    before_hands = {r.name: r for r in before.capabilities or ()}
    assert before_hands["hands.sketch"].state == "degraded"
    assert before_hands["hands.feature"].state == "degraded"

    proof = cad_service.qualify_hands_runtime(
        "desk-1", expected_rich_node="rich-1", expected_session_generation=9
    )
    assert proof == {
        "logical_node": "desk-1", "rich_node": "rich-1", "session_generation": 9,
        "qualified": True,
    }
    after = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    after_hands = {r.name: r for r in after.capabilities or ()}
    assert after_hands["hands.sketch"].state == "supported"
    assert after_hands["hands.feature"].state == "supported"


@pytest.mark.asyncio
async def test_configured_rich_route_emits_exact_hands_policy_records_when_probe_data_is_empty(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {"provider_routes": {"desk-1": {
            "reference_node": "desk-1", "rich_node": "rich-1"
        }}}
    })
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: {"desk-1": 1, "rich-1": 1}[node_id]
    )
    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps({
            "api_version": "fusion.cad/v1", "status": "succeeded",
            "summary": "Runtime capabilities probed", "data": {},
            "capabilities": [{"name": "design.access", "state": "unavailable"}],
        })}], "isError": False,
    })

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    hands = [r for r in result.capabilities or () if r.name.startswith("hands.")]
    assert [r.name for r in hands] == ["hands.sketch", "hands.feature"]
    assert all(r.state == "unavailable" for r in hands)


def test_hands_runtime_qualification_requires_exact_rich_provider_generation(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {"provider_routes": {"desk-1": {
            "reference_node": "desk-1", "rich_node": "rich-1"
        }}}
    })
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: {"desk-1": 2, "rich-1": 7}[node_id]
    )
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )

    with pytest.raises(FusionCadError) as exc:
        cad_service.qualify_hands_runtime(
            "desk-1", expected_rich_node="rich-1", expected_session_generation=6
        )
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert cad_service.hands_runtime_qualification("desk-1") is None


@pytest.mark.asyncio
async def test_rich_provider_reconnect_invalidates_supported_hands_capability_cache(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {"provider_routes": {"desk-1": {
            "reference_node": "desk-1", "rich_node": "rich-1"
        }}}
    })
    generations = {"desk-1": 5, "rich-1": 11}
    mock_desktop_service.get_session_generation = MagicMock(
        side_effect=lambda node_id: generations[node_id]
    )
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    cad_service.qualify_hands_runtime(
        "desk-1", expected_rich_node="rich-1", expected_session_generation=11
    )
    mock_desktop_service.call = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps({
            "api_version": "fusion.cad/v1", "status": "succeeded",
            "summary": "Runtime capabilities probed",
            "data": {"probe_facts": {
                "has_app": True, "has_design_access": True,
                "has_entity_token_resolver": True,
            }},
            "capabilities": [{"name": "design.access", "state": "supported"}],
        })}], "isError": False,
    })
    await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )
    assert cad_service.get_node_capabilities("desk-1").get("hands.sketch").state == "supported"

    generations["rich-1"] = 12
    assert cad_service.get_node_capabilities("desk-1") is None
    assert cad_service.hands_runtime_qualification("desk-1") is None


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


def _prime_commit_ready_transaction(
    service: FusionCadService, transaction_id: str, document_ref: str = "doc_1"
) -> dict:
    """Make an existing authoritative transaction eligible for P0 commit tests."""
    baseline = service.revision_tracker.get_transaction_baseline(transaction_id)
    if baseline is None:
        current = service.revision_tracker.current(document_ref)
        if current is None:
            current = service.revision_tracker.observe(document_ref, "fp_test_baseline")
        service.revision_tracker.begin_transaction(
            transaction_id, document_ref, current.revision, current.fingerprint
        )
        baseline = service.revision_tracker.get_transaction_baseline(transaction_id)
    assert baseline is not None
    record = service.transaction_store.find(transaction_id)
    if record is None:
        record = service.transaction_store.begin(
            transaction_id,
            document_ref,
            baseline["baseline_revision"],
            baseline["baseline_fingerprint"],
            {},
        )
    if record.state is TransactionState.NEW:
        record = service.transaction_store.stage(
            transaction_id, {"action_type": "text_create"}
        )
    if record.state is TransactionState.STAGED and record.preview_evidence is None:
        service.transaction_store.begin_preview(
            transaction_id, baseline["baseline_fingerprint"]
        )
        service.transaction_store.finish_preview(
            transaction_id,
            preview={"replay_signature": {"plan_hash": record.plan_hash}},
        )
    ready = service.transaction_store.get(transaction_id)
    assert ready.state is TransactionState.STAGED
    assert ready.preview_evidence is not None
    return dict(ready.preview_evidence["replay_signature"])


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
                self.objectType = "adsk::fusion::BRepFace"
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
                self.objectType = "adsk::fusion::BRepEdge"
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
                self.objectType = "adsk::fusion::BRepBody"
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
            script = arguments["object"]["script"]
            # Pure metadata mutation: do not inject the internal geometry hook.
            # Geometry-bearing operations must provide the explicit compensation
            # contract covered by the Task 10 atomicity regressions below.
            scope = {"__name__": "__main__"}
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
        # No metadata side effect was applied before the stale guard failed.
        assert _body_attributes() == {}
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

        # The pure metadata write itself is the mutation and is persisted.
        assert _body_attributes().get((RESERVED_METADATA_GROUP, "tag")) == "v1"
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
        preview_baseline = {"volume": None}

        async def run_rendered_production_script(
            node_id: str, tool_name: str, arguments: dict, journal: dict | None = None
        ):
            script = arguments["object"]["script"]
            def tx_begin(payload):
                preview_baseline["volume"] = float(fake_adsk.volume)

            def tx_apply(plan):
                fake_adsk.tx_previewed = True
                fake_adsk.volume = float(fake_adsk.volume) + 50.0
                return {
                    "refs": ["ent_text_spike"],
                    "provenance": {"transaction_id": plan[0]["transaction_id"]},
                    "same_operation_provenance": True,
                }

            def tx_abort(payload):
                if preview_baseline["volume"] is not None:
                    fake_adsk.volume = preview_baseline["volume"]

            scope = {
                "__name__": "__main__",
                "_transaction_begin_primitive": tx_begin,
                "_transaction_apply_plan_primitive": tx_apply,
                "_transaction_snapshot_primitive": lambda payload: {
                    "structural_hash": "preview-hash",
                    "counts": {"bodies": 1, "sketches": 2},
                    "refs": ["ent_text_spike"],
                },
                "_transaction_validate_primitive": lambda payload: {"status": "passed", "errors": []},
                "_transaction_abort_primitive": tx_abort,
                "_transaction_commit_primitive": lambda payload: setattr(fake_adsk, "tx_committed", True),
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
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "stage", "transaction_id": "tx_1234",
             "action": {"action_type": "text_create", "text": "ПЫТОК", "height_mm": 4.0,
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}}}},
            group="transaction",
        )
        stale_record = cad_service.transaction_store.get("tx_1234")
        cad_service.transaction_store.begin_preview("tx_1234", stale_record.baseline_fingerprint)
        cad_service.transaction_store.finish_preview(
            "tx_1234",
            preview={"replay_signature": {"plan_hash": stale_record.plan_hash}},
        )

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
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "stage", "transaction_id": "tx_fresh",
             "action": {"action_type": "text_create", "text": "ПЫТОК", "height_mm": 4.0,
                        "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}}}},
            group="transaction",
        )

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
            script = arguments["object"]["script"]
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
        # Commit eligibility is part of the current P0 contract: a stored plan
        # must have an accepted preview before any commit can be dispatched.
        staged = cad_service.transaction_store.stage(
            "tx_bypass_test", {"action_type": "text_create"}
        )
        cad_service.transaction_store.begin_preview(
            "tx_bypass_test", staged.baseline_fingerprint
        )
        cad_service.transaction_store.finish_preview(
            "tx_bypass_test", preview={"replay_signature": {"plan_hash": staged.plan_hash}}
        )

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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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

    # 5. A valid queued commit reserves the transaction before submit returns.
    _prime_commit_ready_transaction(cad_service, "tx_async_1")
    mock_desktop_service.submit = AsyncMock(
        return_value={"operation_id": "op_async_commit", "status": "queued"}
    )
    comm_sub_res = await cad_service.execute(
        {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_async_1"},
        group="transaction",
    )
    assert comm_sub_res == {"operation_id": "op_async_commit", "status": "queued"}
    assert cad_service.transaction_store.get("tx_async_1").state is TransactionState.COMMITTING
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None

    # 6. A terminal failure without authoritative applied=False evidence keeps
    # the reservation: native completion is not safely replayable.
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
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    assert cad_service.transaction_store.get("tx_async_1").state is TransactionState.COMMITTING

    # 7. A separate valid queued commit with proven terminal success may advance
    # revision and clear only its own stored baseline.
    current = cad_service.revision_tracker.current("doc_1")
    assert current is not None
    cad_service.revision_tracker.begin_transaction(
        "tx_async_2", "doc_1", current.revision, current.fingerprint
    )
    accepted2 = _prime_commit_ready_transaction(cad_service, "tx_async_2")
    mock_desktop_service.submit = AsyncMock(
        return_value={"operation_id": "op_async_commit_2", "status": "queued"}
    )
    queued2 = await cad_service.execute(
        {"node_id": "desk-1", "operation": "commit", "transaction_id": "tx_async_2"},
        group="transaction",
    )
    assert queued2["status"] == "queued"
    cad_service.finalize_terminal_operation(
        {
            "operation_id": "op_async_commit_2",
            "node_id": "desk-1",
            "status": "succeeded",
            "summary": "transaction:commit",
            "checkpoint": {
                "operation": "commit",
                "group": "transaction",
                "transaction_id": "tx_async_2",
                "document_ref": "doc_1",
            },
        },
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Transaction commit completed",
            "document": {"document_ref": "doc_1", "model_revision": current.revision},
            "data": {
                "operation": "commit",
                "applied": True,
                "transaction_id": "tx_async_2",
                "fingerprint": "proven_post_fp_456",
                "replay_signature": accepted2,
            },
        },
    )
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_2") is None
    assert cad_service.revision_tracker.get_transaction_baseline("tx_async_1") is not None
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_2"
    assert cad_service.revision_tracker.current("doc_1").fingerprint == "proven_post_fp_456"


@pytest.mark.asyncio
async def test_transaction_stage_does_not_consume_commit_provenance_operation_id(
    real_desktop_service: DesktopNodeService,
):
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    cad_service = FusionCadService(real_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(
                    name="transaction.preview_replay", state="supported"
                ),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        ),
    )
    tx_id = "tx_distinct_stage_commit_ids"

    begin = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "begin",
            "transaction_id": tx_id,
            "document_ref": "doc_1",
        },
        group="transaction",
    )
    begin_status = real_desktop_service.operation_status(
        "desk-1", begin["operation_id"]
    )
    cad_service.finalize_terminal_operation(
        {**begin_status, "status": "succeeded"},
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Transaction begin completed",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {
                "operation": "begin",
                "applied": True,
                "transaction_id": tx_id,
                "fingerprint": "fp_stage_commit_ids",
            },
        },
    )

    stage = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "stage",
            "transaction_id": tx_id,
            "action": {
                "action_type": "text_create",
                "text": "Schedule",
                "height_mm": 4.0,
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
    stage_operation_id = stage["operation_id"]
    stage_status = real_desktop_service.operation_status(
        "desk-1", stage_operation_id
    )
    staged_payload = stage_status["checkpoint"]["finalization_payload"]
    provenance_operation_id = staged_payload["action"]["provenance"]["operation_id"]
    cad_service.finalize_terminal_operation(
        {**stage_status, "status": "succeeded"},
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Transaction stage completed",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {
                "operation": "stage",
                "applied": False,
                "transaction_id": tx_id,
            },
        },
    )
    staged_record = cad_service.transaction_store.get(tx_id)
    cad_service.transaction_store.begin_preview(
        tx_id, staged_record.baseline_fingerprint
    )
    cad_service.transaction_store.finish_preview(
        tx_id,
        preview={"replay_signature": {"plan_hash": staged_record.plan_hash}},
    )

    commit = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "commit",
            "transaction_id": tx_id,
        },
        group="transaction",
    )

    assert stage_operation_id != provenance_operation_id
    assert commit["operation_id"] == provenance_operation_id


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

        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        "missing_timeline_feature_attributes",
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
            elif case == "missing_timeline_feature_attributes":
                design.timeline.item(0).entity.attributes = None
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
            script = arguments["object"]["script"]
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
            script = arguments["object"]["script"]
            # Pure metadata mutation; no geometry hook is present.
            scope = {"__name__": "__main__"}
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
    """Commit only clears authority after one reserved, proven-equivalent success."""
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(name="revision.external_change_detection", state="supported"),
            ]
        ),
    )
    cad_service.revision_tracker.observe("doc_1", "baseline_fp_1")

    def ready(tx_id: str) -> dict:
        current = cad_service.revision_tracker.current("doc_1")
        assert current is not None
        cad_service.revision_tracker.begin_transaction(
            tx_id, "doc_1", current.revision, current.fingerprint
        )
        return _prime_commit_ready_transaction(cad_service, tx_id)

    def response(tx_id: str, *, document="doc_1", data_document=None, fingerprint="new_fp_post", signature=None):
        data = {
            "transaction_id": tx_id,
            "operation": "commit",
            "applied": True,
            "fingerprint": fingerprint,
        }
        if data_document is not None:
            data["document_ref"] = data_document
        if signature is not None:
            data["replay_signature"] = signature
        return {
            "content": [{"type": "text", "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "transaction:commit",
                "document": None if document is None else {"document_ref": document, "model_revision": "rev_1"},
                "data": data,
            })}],
            "isError": False,
        }

    # Explicit failure with no proof of non-application preserves baseline and
    # leaves COMMITTING, preventing a dangerous replay.
    tx_fail = "tx_commit_fail"
    ready(tx_fail)
    mock_desktop_service.submit = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps({
            "api_version": "fusion.cad/v1",
            "status": "failed",
            "error": {"code": "FUSION_API_ERROR", "message": "Failed to commit"},
        })}],
        "isError": True,
    })
    with pytest.raises(BridgeError):
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "commit", "transaction_id": tx_fail},
            group="transaction",
        )
    assert cad_service.revision_tracker.get_transaction_baseline(tx_fail) is not None
    assert cad_service.transaction_store.get(tx_fail).state is TransactionState.COMMITTING

    cases = [
        ("tx_commit_no_doc", response("tx_commit_no_doc", document=None), ErrorCode.NO_ACTIVE_DESIGN),
        ("tx_commit_wrong_doc", response("tx_commit_wrong_doc", document="doc_other"), ErrorCode.WRONG_DOCUMENT),
        ("tx_commit_diverged_doc", response("tx_commit_diverged_doc", data_document="doc_diverged"), ErrorCode.WRONG_DOCUMENT),
        ("tx_commit_empty_fp", response("tx_commit_empty_fp", fingerprint="   "), ErrorCode.FUSION_API_ERROR),
    ]
    for tx_id, raw, expected_code in cases:
        ready(tx_id)
        mock_desktop_service.submit = AsyncMock(return_value=raw)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {"node_id": "desk-1", "operation": "commit", "transaction_id": tx_id},
                group="transaction",
            )
        assert exc.value.code == expected_code
        assert cad_service.revision_tracker.get_transaction_baseline(tx_id) is not None
        assert cad_service.transaction_store.get(tx_id).state is TransactionState.COMMITTING

    tx_ok = "tx_commit_ok"
    signature = ready(tx_ok)
    mock_desktop_service.submit = AsyncMock(
        return_value=response(tx_ok, signature=signature)
    )
    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "commit", "transaction_id": tx_ok},
        group="transaction",
    )
    assert result is not None
    assert cad_service.transaction_store.get(tx_ok).state is TransactionState.COMMITTED
    assert cad_service.revision_tracker.get_transaction_baseline(tx_ok) is None
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
    """Non-boolean/false applied evidence never advances transaction authority."""
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(name="revision.external_change_detection", state="supported"),
            ]
        ),
    )
    cad_service.revision_tracker.observe("doc_1", "base_fp")

    def set_mock_resp(tx_id: str, operation: str, applied_marker, *, include_applied=True):
        data = {
            "transaction_id": tx_id,
            "operation": operation,
            "fingerprint": "base_fp" if operation != "commit" else "new_fp",
        }
        if include_applied:
            data["applied"] = applied_marker
        resp = {
            "content": [{"type": "text", "text": json.dumps({
                "api_version": "fusion.cad/v1",
                "status": "succeeded",
                "summary": "transaction execution",
                "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
                "data": data,
            })}],
            "isError": False,
        }
        mock_desktop_service.call = AsyncMock(return_value=resp)
        mock_desktop_service.submit = AsyncMock(return_value=resp)

    invalid_commit_values = [False, "__missing__", "true", 1, None, [True]]
    for index, marker in enumerate(invalid_commit_values):
        tx_id = f"tx_commit_invalid_{index}"
        current = cad_service.revision_tracker.current("doc_1")
        assert current is not None
        cad_service.revision_tracker.begin_transaction(
            tx_id, "doc_1", current.revision, current.fingerprint
        )
        _prime_commit_ready_transaction(cad_service, tx_id)
        set_mock_resp(
            tx_id,
            "commit",
            marker,
            include_applied=marker != "__missing__",
        )
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {"node_id": "desk-1", "operation": "commit", "transaction_id": tx_id},
                group="transaction",
            )
        assert exc.value.code == ErrorCode.FUSION_API_ERROR
        assert cad_service.revision_tracker.get_transaction_baseline(tx_id) is not None
        assert cad_service.transaction_store.get(tx_id).state is TransactionState.COMMITTING
        assert cad_service.revision_tracker.current("doc_1").fingerprint == "base_fp"

    for tx_id, operation, marker in [
        ("tx_abort_1", "abort", False),
        ("tx_rollback_1", "rollback", "true"),
    ]:
        current = cad_service.revision_tracker.current("doc_1")
        assert current is not None
        cad_service.revision_tracker.begin_transaction(
            tx_id, "doc_1", current.revision, current.fingerprint
        )
        set_mock_resp(tx_id, operation, marker)
        with pytest.raises(FusionCadError) as exc:
            await cad_service.execute(
                {"node_id": "desk-1", "operation": operation, "transaction_id": tx_id},
                group="transaction",
            )
        assert exc.value.code == ErrorCode.FUSION_API_ERROR
        assert cad_service.revision_tracker.get_transaction_baseline(tx_id) is not None
        assert cad_service.revision_tracker.current("doc_1").fingerprint == "base_fp"


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
    accepted_signature = _prime_commit_ready_transaction(cad_service, "tx_ext_fail")

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
                            "replay_signature": accepted_signature,
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        script = arguments["object"]["script"]
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
        self.mutation_compensation_capture = None
        self.mutation_compensation_rollback = None

    def _dispatch(self, arguments):
        script = arguments["object"]["script"]
        op = _payload_operation(script)
        if op in _METADATA_MUTATION_OPS:
            self.mutation_calls += 1
        else:
            self.read_calls += 1
        scope = {"__name__": "__main__"}
        if self.mutation_primitive is not None:
            scope["_mutation_primitive"] = self.mutation_primitive
        if self.mutation_compensation_capture is not None:
            scope["_mutation_compensation_capture"] = self.mutation_compensation_capture
        if self.mutation_compensation_rollback is not None:
            scope["_mutation_compensation_rollback"] = self.mutation_compensation_rollback
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

        def delete_me():
            """Documented Autodesk Attribute.deleteMe: returns True iff the
            deletion succeeded and False otherwise."""
            try:
                items.remove(attr)
            except ValueError:
                return False
            return True

        attr.deleteMe = delete_me
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
    """Yields {"adsk": fake_adsk, "desktop": FakeFusionDesktop} inside a fake Fusion runtime.

    The fake attribute collections implement the documented Autodesk Fusion
    Attributes.add semantics: an add UPDATES and returns the EXISTING
    same-group/same-name attribute instead of appending a duplicate, matching
    the real runtime the mutate script targets."""
    with AdskFakeContext("doc_1", initial_volume=100.0) as fake_adsk:
        _enable_fake_attribute_removal(fake_adsk)
        _enable_fake_fusion_add_overwrite(fake_adsk)
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
    desktop.mutation_compensation_capture = lambda payload: fake_adsk.volume
    desktop.mutation_compensation_rollback = lambda captured: (
        setattr(fake_adsk, "volume", captured) or True
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


def _exec_rendered_mutate(
    script: str,
    mutation_primitive=None,
    mutation_compensation_capture=None,
    mutation_compensation_rollback=None,
):
    scope = {"__name__": "__main__"}
    if mutation_primitive is not None:
        scope["_mutation_primitive"] = mutation_primitive
    if mutation_compensation_capture is not None:
        scope["_mutation_compensation_capture"] = mutation_compensation_capture
    if mutation_compensation_rollback is not None:
        scope["_mutation_compensation_rollback"] = mutation_compensation_rollback
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    return scope["_output"]


def _geometry_plan_payload(cad_service, body_ref, *, operation_id):
    rec = cad_service.revision_tracker.current("doc_1")
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
        operation_id=operation_id,
        created_revision=cad_service.revision_tracker.next_revision("doc_1"),
    )
    return payload


@pytest.mark.asyncio
async def test_geometry_provenance_failure_restores_geometry_and_full_fingerprint(
    fake_desktop,
):
    """RED: a provenance failure after geometry must restore the whole model."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    payload = _geometry_plan_payload(
        cad_service, body_ref, operation_id="op_geometry_rollback_1"
    )
    initial_fp = cad_service.revision_tracker.current("doc_1").fingerprint

    import adsk.core

    attrs_cls = type(adsk.core.Application.get().activeDocument.attributes)
    healthy_add = attrs_cls.add

    def reject_provenance(self, group_name, name, value):
        if name == PROVENANCE_ATTRIBUTE_NAME:
            return None
        return healthy_add(self, group_name, name, value)

    attrs_cls.add = reject_provenance
    try:
        script = FusionCadScriptBundle().build("mutate", payload)
        output = _exec_rendered_mutate(
            script,
            mutation_primitive=lambda _payload: setattr(fake_adsk, "volume", 125.0),
            mutation_compensation_capture=lambda _payload: fake_adsk.volume,
            mutation_compensation_rollback=lambda captured: (
                setattr(fake_adsk, "volume", captured) or True
            ),
        )
    finally:
        attrs_cls.add = healthy_add

    assert output["status"] == "failed"
    assert fake_adsk.volume == 100.0
    assert _body_attributes() == {}
    verify = FusionCadScriptBundle().build(
        "read", {"operation": "model_snapshot", "document_ref": "doc_1"}
    )
    verify_output = _exec_rendered_mutate(verify)
    assert verify_output["data"]["fingerprint"] == initial_fp



@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.parametrize("post_mode", ["invalid", "unchanged"])
@pytest.mark.asyncio
async def test_post_fingerprint_failure_attempts_geometry_rollback_even_if_metadata_rollback_fails(
    fake_desktop, operation, post_mode
):
    """Metadata rollback failure must never skip required geometry rollback."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    rec = cad_service.revision_tracker.current("doc_1")
    payload = {
        "operation": operation,
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
        operation=operation,
        creator_operation=f"fusion_style:{operation}",
        operation_id=f"op_postfp_{operation}_{post_mode}",
        created_revision=cad_service.revision_tracker.next_revision("doc_1"),
    )

    attrs_cls, healthy_add, hostile_add = _arm_hostile_created_delete(
        fake_adsk, PROVENANCE_ATTRIBUTE_NAME, "false_after_delete"
    )
    attrs_cls.add = hostile_add
    try:
        script = FusionCadScriptBundle().build("mutate", payload)
        assert script.count("        _output = run()") == 1
        script = script.replace("        _output = run()", "        _output = None", 1)
        scope = {
            "__name__": "__main__",
            "_mutation_primitive": lambda _payload: setattr(fake_adsk, "volume", 125.0),
            "_mutation_compensation_capture": lambda _payload: fake_adsk.volume,
            "_mutation_compensation_rollback": lambda captured: (
                setattr(fake_adsk, "volume", captured) or True
            ),
        }
        exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
        baseline_fp = rec.fingerprint
        post_fp = "" if post_mode == "invalid" else baseline_fp
        fingerprints = iter([
            (baseline_fp, {}, "doc_1"),
            (post_fp, {}, "doc_1"),
            (baseline_fp, {}, "doc_1"),
        ])
        scope["collect_model_fingerprint"] = lambda _payload=None: next(fingerprints)
        with pytest.raises(Exception) as exc:
            scope["run"]()
        assert getattr(exc.value, "code", None) in {
            "CAPABILITY_UNAVAILABLE",
            "FUSION_API_ERROR",
        }
    finally:
        attrs_cls.add = healthy_add

    assert fake_adsk.volume == 100.0

@pytest.mark.asyncio
async def test_plan_bearing_geometry_without_compensation_fails_before_geometry(
    fake_desktop,
):
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    payload = _geometry_plan_payload(
        cad_service, _register_body_ref(cad_service), operation_id="op_no_rollback_1"
    )

    output = _exec_rendered_mutate(
        FusionCadScriptBundle().build("mutate", payload),
        mutation_primitive=lambda _payload: setattr(fake_adsk, "volume", 125.0),
    )

    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert output["error"]["details"]["applied"] is False
    assert fake_adsk.volume == 100.0
    assert _body_attributes() == {}


@pytest.mark.parametrize("rollback_mode", ["explicit_failure", "fingerprint_mismatch"])
@pytest.mark.asyncio
async def test_geometry_compensation_failure_reports_uncertain_not_applied(
    fake_desktop, rollback_mode
):
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    payload = _geometry_plan_payload(
        cad_service, _register_body_ref(cad_service), operation_id="op_bad_rollback_1"
    )

    import adsk.core

    attrs_cls = type(adsk.core.Application.get().activeDocument.attributes)
    healthy_add = attrs_cls.add
    attrs_cls.add = lambda self, group_name, name, value: (
        None if name == PROVENANCE_ATTRIBUTE_NAME else healthy_add(self, group_name, name, value)
    )
    try:
        output = _exec_rendered_mutate(
            FusionCadScriptBundle().build("mutate", payload),
            mutation_primitive=lambda _payload: setattr(fake_adsk, "volume", 125.0),
            mutation_compensation_capture=lambda _payload: fake_adsk.volume,
            mutation_compensation_rollback=(
                (lambda _captured: False)
                if rollback_mode == "explicit_failure"
                else (lambda _captured: True)
            ),
        )
    finally:
        attrs_cls.add = healthy_add

    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert output["error"]["details"]["applied"] is False
    assert output["error"]["details"]["compensated"] is False


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
    is never externally reported as success. The operation-specific geometry
    compensation must restore the exact full model fingerprint too."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    desktop.mutation_primitive = lambda payload: setattr(
        fake_adsk, "volume", float(fake_adsk.volume) + 25.0
    )
    desktop.mutation_compensation_capture = lambda payload: fake_adsk.volume
    desktop.mutation_compensation_rollback = lambda captured: (
        setattr(fake_adsk, "volume", captured) or True
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
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert exc.value.details.get("applied") is False
    assert desktop.mutation_calls == 1
    # Partial metadata is compensated: the owner is exactly back to baseline
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count
    assert fake_adsk.volume == 100.0
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
            if self._reads == 2:
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
    desktop.mutation_compensation_capture = lambda payload: fake_adsk.volume
    desktop.mutation_compensation_rollback = lambda captured: (
        setattr(fake_adsk, "volume", captured) or True
    )
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
    capture = lambda payload: fake_adsk.volume
    rollback = lambda captured: setattr(fake_adsk, "volume", captured) or True
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
    output = _exec_rendered_mutate(
        script, desktop.mutation_primitive, capture, rollback
    )

    # The same single execution applied the geometry change AND the provenance
    assert output["status"] == "succeeded"
    assert output["data"]["applied"] is True
    assert output["data"]["provenance"]["operation_id"] == "op_geo_command_1"
    # Public result refs are opaque strings only.  The trusted execution hint
    # (native token/name/kind) must never escape through changed_refs, and the
    # result must satisfy the CadResult schema after the mutation committed.
    decoded = CadResult.model_validate(output)
    assert decoded.changed_refs == (body_ref,)
    assert "native_token" not in json.dumps(output.get("changed_refs", []))
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



@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.asyncio
async def test_compensated_arbitrary_mutation_exception_never_leaks_raw_diagnostics(
    fake_desktop, operation
):
    """Arbitrary primitive/runtime exceptions are model-untrusted diagnostics.

    Even after exact compensation succeeds, the public fusion.cad/v1 error must
    use a constant sanitized message/details and must not expose the exception
    string or traceback. Exercise both the primary metadata mutation branch and
    the fallback geometry/style branch.
    """
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    rec = cad_service.revision_tracker.current("doc_1")
    target = {
        "ref": body_ref,
        "kind": "body",
        "name": "Body1",
        "native_token": "body_token_1",
        "component_path": [],
    }
    payload = {
        "operation": operation,
        "target": target,
        "expected_revision": rec.revision,
        "expected_fingerprint": rec.fingerprint,
        "document_ref": "doc_1",
    }
    if operation == "set":
        payload.update({"name": "finish", "value": "anodized"})
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_secret_diag_set",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )
    else:
        apply_geometry_provenance_plan(
            payload,
            operation="show",
            creator_operation="fusion_style:show",
            operation_id="op_secret_diag_show",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )

    secret = f"secret::native::{operation}::AQAA-RAW-TOKEN"

    def hostile_primitive(_payload):
        fake_adsk.volume = 125.0
        raise RuntimeError(secret)

    output = _exec_rendered_mutate(
        FusionCadScriptBundle().build("mutate", payload),
        mutation_primitive=hostile_primitive,
        mutation_compensation_capture=lambda _payload: fake_adsk.volume,
        mutation_compensation_rollback=lambda captured: (
            setattr(fake_adsk, "volume", 100.0) or True
        ),
    )

    assert fake_adsk.volume == 100.0
    assert output["status"] == "failed"
    assert output["error"]["code"] == "FUSION_API_ERROR"
    public = json.dumps(output, ensure_ascii=False)
    assert secret not in public
    assert "traceback" not in output["error"].get("details", {})


@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.asyncio
async def test_result_construction_failure_compensates_and_is_sanitized(
    fake_desktop, operation
):
    """A failure after a distinct post-apply fingerprint is still transactional."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    rec = cad_service.revision_tracker.current("doc_1")
    baseline_attrs = _body_attributes()
    payload = {
        "operation": operation,
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
    if operation == "set":
        payload.update({"name": "finish", "value": "anodized"})
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_result_failure_set",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )
    else:
        apply_geometry_provenance_plan(
            payload,
            operation="show",
            creator_operation="fusion_style:show",
            operation_id="op_result_failure_show",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )

    script = FusionCadScriptBundle().build("mutate", payload)
    script = script.replace("        _output = run()", "        _output = None", 1)
    scope = {
        "__name__": "__main__",
        "_mutation_primitive": lambda _payload: setattr(fake_adsk, "volume", 125.0),
        "_mutation_compensation_capture": lambda _payload: fake_adsk.volume,
        "_mutation_compensation_rollback": lambda captured: (
            setattr(fake_adsk, "volume", captured) or True
        ),
    }
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    secret = f"secret::result::{operation}::AQAA-RAW-TOKEN"

    def hostile_make_result(**_kwargs):
        raise RuntimeError(secret)

    scope["make_result"] = hostile_make_result
    with pytest.raises(scope["FusionScriptError"]) as exc:
        scope["run"]()

    assert exc.value.code == "FUSION_API_ERROR"
    assert exc.value.message == (
        "Mutation execution failed after an apply attempt; exact compensation completed"
    )
    assert exc.value.details == {
        "operation": operation,
        "applied": False,
        "compensated": True,
    }
    assert secret not in json.dumps(exc.value.details)
    assert secret not in exc.value.message
    assert fake_adsk.volume == 100.0
    assert _body_attributes() == baseline_attrs
    verify = FusionCadScriptBundle().build(
        "read", {"operation": "model_snapshot", "document_ref": "doc_1"}
    )
    assert _exec_rendered_mutate(verify)["data"]["fingerprint"] == rec.fingerprint
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"


@pytest.mark.parametrize(
    ("operation", "restoration_mode"),
    [("set", "unavailable"), ("show", "mismatch")],
)
@pytest.mark.asyncio
async def test_result_construction_failure_without_geometry_requires_full_restoration_proof(
    fake_desktop, operation, restoration_mode
):
    """Metadata-only compensation must prove the full fingerprint was restored."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    rec = cad_service.revision_tracker.current("doc_1")
    baseline_attrs = _body_attributes()
    payload = {
        "operation": operation,
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
    if operation == "set":
        payload.update({"name": "finish", "value": "anodized"})
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_result_proof_set",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )
    else:
        apply_geometry_provenance_plan(
            payload,
            operation="show",
            creator_operation="fusion_style:show",
            operation_id="op_result_proof_show",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )

    script = FusionCadScriptBundle().build("mutate", payload)
    script = script.replace("        _output = run()", "        _output = None", 1)
    scope = {"__name__": "__main__"}
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    secret = f"secret::restoration::{operation}::AQAA-RAW-TOKEN"
    fingerprint_calls = iter(
        [
            (rec.fingerprint, {}, "doc_1"),
            (f"distinct-{operation}", {}, "doc_1"),
        ]
    )

    def collect_fingerprint(_payload=None):
        try:
            return next(fingerprint_calls)
        except StopIteration:
            if restoration_mode == "unavailable":
                raise RuntimeError(secret)
            return (f"not-restored-{operation}", {}, "doc_1")

    scope["collect_model_fingerprint"] = collect_fingerprint
    scope["make_result"] = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError(secret)
    )
    with pytest.raises(scope["FusionScriptError"]) as exc:
        scope["run"]()

    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    assert exc.value.details == {
        "operation": operation,
        "applied": False,
        "compensated": False,
    }
    assert secret not in exc.value.message
    assert secret not in json.dumps(exc.value.details)
    assert _body_attributes() == baseline_attrs


@pytest.mark.asyncio
async def test_mid_plan_failure_rolls_back_created_attribute_exactly_once(fake_desktop):
    """An internal plan rollback is not repeated by the outer transaction handler."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    import adsk.core

    attrs_cls = type(adsk.core.Application.get().activeDocument.attributes)
    healthy_add = attrs_cls.add
    delete_calls = {"count": 0}

    def fail_after_created_write(self, group_name, name, value):
        if name == PROVENANCE_ATTRIBUTE_NAME:
            raise RuntimeError("mid-plan failure")
        attr = healthy_add(self, group_name, name, value)
        original_delete = attr.deleteMe

        def counted_delete():
            delete_calls["count"] += 1
            if delete_calls["count"] > 1:
                raise RuntimeError("created attribute rollback repeated")
            return original_delete()

        attr.deleteMe = counted_delete
        return attr

    attrs_cls.add = fail_after_created_write
    try:
        with pytest.raises(FusionCadError):
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
    finally:
        attrs_cls.add = healthy_add

    assert delete_calls["count"] == 1
    assert _body_attributes() == {}

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


# =========================================================================
# Task 10 final narrow repair: Attributes.add null/mismatch fail-closed
# =========================================================================


@pytest.mark.asyncio
async def test_metadata_provenance_add_null_fails_closed_and_restores_exact_state(
    fake_desktop,
):
    """Verified Fusion semantics: Attributes.add(groupName, name, value) returns
    the created/existing Attribute, or null when creation fails. When the
    explicit metadata write succeeds but the provenance Attributes.add returns
    null (persisting no provenance), the command must fail closed and the exact
    pre-command reserved metadata state must be restored: the plan must never be
    recorded/applied and the post-apply fingerprint must never permit reporting
    success without persisted provenance."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    current_add = attrs_cls.add

    def add_null_provenance(self, group_name, name, value):
        # Provenance creation FAILS at the Fusion layer: Attributes.add returns
        # null and no provenance attribute is persisted.
        if name == PROVENANCE_ATTRIBUTE_NAME:
            return None
        return current_add(self, group_name, name, value)

    attrs_cls.add = add_null_provenance
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
    finally:
        attrs_cls.add = current_add

    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    # Exact pre-command reserved metadata state restored: the successful
    # explicit write was compensated and no provenance was left behind.
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count
    # The document owner never received the metadata either.
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _document_attributes()
    assert ("bridge.cad/v1", "finish") not in _document_attributes()


@pytest.mark.asyncio
async def test_metadata_provenance_add_mismatched_attribute_fails_closed_and_restores(
    fake_desktop,
):
    """Repair: when Attributes.add returns an Attribute whose group/name/value
    does not match the requested write, the write cannot be verified as applied;
    the command fails closed and the exact pre-command reserved metadata state
    is restored instead of reporting a fingerprint-distinct success."""
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

    # 2. Model real Fusion overwrite semantics, then make the provenance add
    # return the EXISTING attribute object WITHOUT applying the requested value
    # (a returned Attribute that does not match the requested write).
    _enable_fake_fusion_add_overwrite(fake_adsk)

    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    current_add = attrs_cls.add

    def add_stale_provenance(self, group_name, name, value):
        if name == PROVENANCE_ATTRIBUTE_NAME:
            for i in range(self.count):
                existing = self.item(i)
                if (
                    getattr(existing, "groupName", None) == group_name
                    and getattr(existing, "name", None) == name
                ):
                    # Returned Attribute does NOT match the requested write:
                    # the runtime returned the existing object with its stale value.
                    return existing
        return current_add(self, group_name, name, value)

    attrs_cls.add = add_stale_provenance
    try:
        baseline_body_attrs = _body_attributes()
        baseline_body_attr_count = _body_attr_count()
        assert baseline_body_attrs[("bridge.cad/v1", "finish")] == "old-finish"
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
    finally:
        attrs_cls.add = current_add

    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    # Exact pre-command reserved metadata state restored: the overwritten
    # "finish" value was compensated and the stale provenance is untouched.
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count


# =========================================================================
# Task 10 final bounded repair A: current-write add-result failure after
# observable mutation must be compensated from pre-write state
# =========================================================================


class _MismatchedAttribute:
    """An Attribute object that does NOT match the requested metadata write.

    Used only to simulate a misbehaving/corrupt Fusion runtime whose
    Attributes.add applies the requested state mutation and then returns a
    mismatched Attribute instead of the verified one."""

    def __init__(self, group_name, name, value):
        self.groupName = group_name
        self.name = name
        self.value = value


def _arm_one_shot_bad_add(fake_adsk, target_name, mode):
    """Corrupt the fake Attributes.add for exactly ONE call on target_name.

    The requested state mutation IS applied first (real Fusion create/overwrite
    semantics through the currently installed add), then the call returns null
    ("null" mode) or a mismatched Attribute ("mismatch" mode) instead of the
    verified Attribute. Returns (attrs_cls, healthy_add) so tests can restore
    the healthy add afterwards."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    healthy_add = attrs_cls.add
    armed = {"pending": True}

    def add_mutating_then_bad(self, group_name, name, value):
        result = healthy_add(self, group_name, name, value)
        if (
            armed["pending"]
            and group_name == RESERVED_METADATA_GROUP
            and name == target_name
        ):
            armed["pending"] = False
            if mode == "null":
                return None
            return _MismatchedAttribute(group_name, name, "corrupt-mismatch-value")
        return result

    attrs_cls.add = add_mutating_then_bad
    return attrs_cls, healthy_add


@pytest.mark.parametrize("mode", ["null", "mismatch"])
@pytest.mark.asyncio
async def test_metadata_overwrite_add_bad_result_after_mutation_restores_exact_state(
    fake_desktop, mode
):
    """Finding A (overwritten pre-existing key): a misbehaving runtime can apply
    the requested overwrite and THEN return null or a mismatched Attribute. The
    current write must itself be compensated from the pre-add state so the
    command fails closed AND the exact pre-command reserved namespace
    state/count is restored (never just the earlier undo-log actions)."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    # 1. A successful set creates "finish" + provenance on the body owner.
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

    # 2. Official Fusion overwrite semantics, then ONE corrupt add on the
    # explicit "finish" write: mutate in place, then return null/mismatch.
    _enable_fake_fusion_add_overwrite(fake_adsk)
    attrs_cls, healthy_add = _arm_one_shot_bad_add(fake_adsk, "finish", mode)
    try:
        baseline_body_attrs = _body_attributes()
        baseline_body_attr_count = _body_attr_count()
        assert baseline_body_attrs[("bridge.cad/v1", "finish")] == "old-finish"
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
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    # Command fails closed AND the exact pre-command reserved namespace
    # state/count is restored: the failed current write is compensated too.
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count

    # 3. A healthy retry with the same expected revision applies cleanly.
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
    assert _body_attributes()[("bridge.cad/v1", "finish")] == "anodized"


@pytest.mark.parametrize("mode", ["null", "mismatch"])
@pytest.mark.asyncio
async def test_metadata_create_add_bad_result_after_persist_restores_exact_state(
    fake_desktop, mode
):
    """Finding A (newly-created key actually persisted): the add call persists
    the new reserved attribute but returns null/mismatch. The persisted
    attribute must be re-derived by enumeration and deleted via the verified
    deleteMe primitive — never trusted from the bad returned object — so the
    exact pre-command reserved namespace state/count is restored."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    attrs_cls, healthy_add = _arm_one_shot_bad_add(fake_adsk, "finish", mode)
    try:
        baseline_body_attrs = _body_attributes()
        baseline_body_attr_count = _body_attr_count()
        assert ("bridge.cad/v1", "finish") not in baseline_body_attrs
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
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    # Exact pre-command reserved namespace state/count restored: the persisted
    # creation of the failed current write was compensated.
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count
    assert ("bridge.cad/v1", "finish") not in _body_attributes()
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()


@pytest.mark.asyncio
async def test_metadata_current_write_persist_null_after_prior_write_restores_exact_state(
    fake_desktop,
):
    """Finding A end-to-end: an earlier explicit write succeeds (undo entry),
    then the CURRENT provenance write is actually persisted but returns null.
    Rollback must compensate BOTH the earlier undo-log actions and the failed
    current write so the exact pre-command reserved state/count is restored."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    attrs_cls, healthy_add = _arm_one_shot_bad_add(
        fake_adsk, PROVENANCE_ATTRIBUTE_NAME, "null"
    )
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
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    assert _body_attributes() == baseline_body_attrs
    assert _body_attr_count() == baseline_body_attr_count
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()


# =========================================================================
# Task 10 final bounded repair B: duplicate same (group, name) reserved
# records are corrupted state; mutation must fail closed BEFORE any mutation
# =========================================================================


def _body_reserved_multiset():
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    design = doc.products.itemByClass("adsk::fusion::Design")
    body = design.rootComponent.bRepBodies.item(0)
    attrs = body.attributes
    return [
        (attrs.item(i).groupName, attrs.item(i).name, attrs.item(i).value)
        for i in range(attrs.count)
    ]


@pytest.mark.asyncio
async def test_metadata_duplicate_reserved_names_fail_closed_before_any_mutation(
    fake_desktop,
):
    """Finding B: duplicate same (bridge.cad/v1, name) records inside the
    reserved namespace are corrupted state outside the Autodesk uniqueness
    contract. Their multiset cannot be reconstructed via Attributes.add, so
    mutation/removal must fail closed BEFORE the geometry hook or any reserved
    attribute side effect and preserve the exact duplicate multiset/state."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    design = doc.products.itemByClass("adsk::fusion::Design")
    body = design.rootComponent.bRepBodies.item(0)

    class _CorruptReservedAttr:
        def __init__(self, group_name, name, value):
            self.groupName = group_name
            self.name = name
            self.value = value

    # Corrupted reserved state INJECTED directly (real Fusion Attributes.add
    # can never create same-(group, name) duplicates): two records sharing
    # (group, name), plus an unrelated group that must remain untouched.
    body_attrs = body.attributes
    body_attrs.add("vendor.custom", "color", "blue")
    for _dup_value in ("value-one", "value-two"):
        body_attrs._items.append(
            _CorruptReservedAttr(RESERVED_METADATA_GROUP, "finish", _dup_value)
        )

    # Baseline is seeded from a real semantic read AFTER the corruption so the
    # authoritative freshness guard passes and the duplicate preflight is what
    # rejects the command.
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_multiset = _body_reserved_multiset()
    assert baseline_multiset.count(
        (RESERVED_METADATA_GROUP, "finish", "value-one")
    ) == 1
    assert baseline_multiset.count(
        (RESERVED_METADATA_GROUP, "finish", "value-two")
    ) == 1
    assert ("vendor.custom", "color", "blue") in baseline_multiset

    primitive_calls = {"count": 0}

    def _primitive(payload):
        primitive_calls["count"] += 1

    desktop.mutation_primitive = _primitive

    # 1. Duplicate-aware mutation must fail closed before any mutation.
    with pytest.raises(FusionCadError) as exc_set:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "set",
                "target": body_ref,
                "name": "finish",
                "value": "replaced",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_set.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert primitive_calls["count"] == 0
    assert _body_reserved_multiset() == baseline_multiset

    # 2. Duplicate-aware removal must fail closed before any mutation too.
    with pytest.raises(FusionCadError) as exc_remove:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "remove",
                "target": body_ref,
                "name": "finish",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc_remove.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert primitive_calls["count"] == 0
    assert _body_reserved_multiset() == baseline_multiset
    # The unrelated group remains untouched either way.
    assert ("vendor.custom", "color", "blue") in _body_reserved_multiset()


# =========================================================================
# Task 10 final narrow repair C: Attribute.deleteMe result is verified and
# post-delete enumeration proves the targeted reserved record disappeared
# =========================================================================


def _seed_body_reserved_attribute(name, value):
    """Seed a reserved attribute on the body owner via the Fusion-like fake
    Attributes.add and return the live Attribute object so a test can model a
    misbehaving deleteMe on it."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    design = doc.products.itemByClass("adsk::fusion::Design")
    body = design.rootComponent.bRepBodies.item(0)
    return body.attributes.add(RESERVED_METADATA_GROUP, name, value)


@pytest.mark.asyncio
async def test_metadata_removal_deleteMe_false_noop_fails_closed_and_compensates(
    fake_desktop,
):
    """Documented Autodesk semantics: Attribute.deleteMe returns True iff the
    deletion succeeded; False means the requested attribute was NOT removed.
    A False/no-op deleteMe must never be reported as an applied removal: the
    command fails closed, the exact pre-command reserved state (including the
    still-present requested attribute) is preserved, and no provenance is left
    behind."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    attr = _seed_body_reserved_attribute("finish", "matte")
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_body_attrs = _body_attributes()
    assert baseline_body_attrs.get((RESERVED_METADATA_GROUP, "finish")) == "matte"

    # Misbehaving runtime: deleteMe reports the documented FAILURE result
    # (False) while leaving the attribute in place.
    attr.deleteMe = lambda: False

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "remove",
                "target": body_ref,
                "name": "finish",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    # The requested attribute remains; the failed command is never reported as
    # applied and the exact pre-command state (incl. no provenance) is kept.
    assert _body_attributes() == baseline_body_attrs
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _document_attributes()
    # Exactly one failed mutation dispatch; no hidden follow-up command.
    assert desktop.mutation_calls == 1
    assert desktop.read_calls == 1
    # The failed command never advanced the revision authority.
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"


@pytest.mark.asyncio
async def test_metadata_removal_deleteMe_true_but_still_present_fails_closed(
    fake_desktop,
):
    """Defensive no-op detection: a deleteMe that reports the documented
    success result (True) while the observable post-delete enumeration still
    shows the targeted reserved record is a no-op. The return value alone can
    never prove removal: the command fails closed and the exact pre-command
    state is preserved."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    attr = _seed_body_reserved_attribute("finish", "matte")
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_body_attrs = _body_attributes()
    assert baseline_body_attrs.get((RESERVED_METADATA_GROUP, "finish")) == "matte"

    # Misbehaving runtime: deleteMe reports success (True) but the targeted
    # attribute is still observable in the owner enumeration afterwards.
    attr.deleteMe = lambda: True

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "remove",
                "target": body_ref,
                "name": "finish",
                "expected_revision": "rev_1",
            },
            group="metadata",
        )
    assert exc.value.code == ErrorCode.FUSION_API_ERROR
    assert _body_attributes() == baseline_body_attrs
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _document_attributes()
    assert desktop.mutation_calls == 1
    assert desktop.read_calls == 1
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"


# =========================================================================
# Task 10 final narrow repair D (Codex re-review job_749af... follow-up):
# rollback-side delete-result verification + no raw deleteMe-result
# stringification in forward removal error details
# =========================================================================


_HOSTILE_DELETEME_MARKER = "HOSTILE_NATIVE_DELETEME_STR_MARKER_zz9x"


class _HostileDeleteResult:
    """A malformed/misbehaving Attribute.deleteMe return object (not a bool).

    Its __str__/__repr__ carry a marker that must NEVER be stringified or
    copied into any raw error detail: only safe constant metadata
    (operation/attribute_name/compensated) may be attached."""

    def __str__(self):
        return _HOSTILE_DELETEME_MARKER

    def __repr__(self):
        return _HOSTILE_DELETEME_MARKER


def _arm_post_apply_fingerprint_explosion():
    """First fingerprint read (pre-guard) succeeds; the post-apply read
    explodes so the plan's created writes must be compensated by rollback."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument

    class _ExplodesOnSecondRead:
        def __init__(self):
            self._reads = 0

        def __bool__(self):
            self._reads += 1
            if self._reads >= 2:
                raise RuntimeError("post-apply fingerprint collection exploded")
            return False

    doc.isModified = _ExplodesOnSecondRead()


def _arm_hostile_created_delete(fake_adsk, target_name, hostile_mode):
    """Wrap the currently installed Attributes.add so the FIRST created
    reserved attribute with target_name gets a misbehaving deleteMe:

    - "false_after_delete": deleteMe actually removes the attribute but
      returns False (bad Boolean result that nevertheless mutated state);
    - "true_noop": deleteMe returns True while leaving the attribute in
      place (reported success without observable removal).

    Returns (attrs_cls, healthy_add, hostile_add) so tests can restore the
    healthy add afterwards."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    healthy_add = attrs_cls.add
    armed = {"used": False}

    def add_with_hostile_created_delete(self, group_name, name, value):
        attr = healthy_add(self, group_name, name, value)
        if (
            not armed["used"]
            and group_name == RESERVED_METADATA_GROUP
            and name == target_name
            and attr is not None
        ):
            armed["used"] = True
            original_delete = attr.deleteMe

            if hostile_mode == "false_after_delete":

                def hostile_delete():
                    original_delete()
                    return False

            else:

                def hostile_delete():
                    return True

            attr.deleteMe = hostile_delete
        return attr

    return attrs_cls, healthy_add, add_with_hostile_created_delete


def _arm_null_add_with_hostile_persisted_delete(fake_adsk, target_name, hostile_mode):
    """One-shot failed current write: the add for target_name PERSISTS the
    attribute (real create semantics) and then returns null, attaching a
    misbehaving deleteMe to the persisted attribute. Returns
    (attrs_cls, healthy_add, hostile_add)."""
    import adsk.core

    doc = adsk.core.Application.get().activeDocument
    attrs_cls = type(doc.attributes)
    healthy_add = attrs_cls.add
    armed = {"pending": True}

    def add_persist_then_null_with_hostile_delete(self, group_name, name, value):
        attr = healthy_add(self, group_name, name, value)
        if (
            armed["pending"]
            and group_name == RESERVED_METADATA_GROUP
            and name == target_name
        ):
            armed["pending"] = False
            original_delete = attr.deleteMe

            if hostile_mode == "false_after_delete":

                def hostile_delete():
                    original_delete()
                    return False

            else:

                def hostile_delete():
                    return True

            attr.deleteMe = hostile_delete
            return None
        return attr

    return attrs_cls, healthy_add, add_persist_then_null_with_hostile_delete


def _raw_removal_payload(cad_service, body_ref, rec):
    payload = {
        "operation": "remove",
        "target": {
            "ref": body_ref,
            "kind": "body",
            "name": "Body1",
            "native_token": "body_token_1",
            "component_path": [],
        },
        "name": "finish",
        "expected_revision": rec.revision,
        "expected_fingerprint": rec.fingerprint,
        "document_ref": "doc_1",
    }
    apply_metadata_mutation_plan(
        payload,
        operation_id="op_raw_removal_conf_1",
        created_revision=cad_service.revision_tracker.next_revision("doc_1"),
    )
    return payload


@pytest.mark.asyncio
async def test_forward_removal_raw_error_never_stringifies_hostile_deleteMe_result(
    fake_desktop,
):
    """Finding 1 (raw-script confidentiality): the RAW rendered script error for
    a failed forward metadata removal must never stringify or copy the
    arbitrary deleteMe result object into error details — the object can carry
    untrusted native runtime text. Only safe constant metadata
    (operation/attribute_name) may be attached. The service sanitizer is
    deliberately bypassed by executing the rendered production script
    directly, so this regression cannot be masked by the diagnostics
    allowlist."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    attr = _seed_body_reserved_attribute("finish", "matte")
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    tracker = cad_service.revision_tracker
    rec = tracker.current("doc_1")

    # Misbehaving runtime: the removal deleteMe returns a hostile non-Boolean
    # object instead of the documented Boolean result.
    attr.deleteMe = lambda: _HostileDeleteResult()

    payload = _raw_removal_payload(cad_service, body_ref, rec)
    script = FusionCadScriptBundle().build("mutate", payload)
    output = _exec_rendered_mutate(script)

    assert output["status"] == "failed"
    assert output["error"]["code"] == "FUSION_API_ERROR"
    details = output["error"]["details"]
    # The raw deleteMe result object is never stringified or copied into the
    # raw error details ...
    assert "deleteMe_result" not in details
    raw_dump = json.dumps(output, ensure_ascii=False, default=repr)
    assert _HOSTILE_DELETEME_MARKER not in raw_dump
    # ... only safe constant metadata is attached.
    assert details.get("operation") == "remove"
    assert details.get("attribute_name") == "finish"
    # The failed removal is still compensated back to the exact pre-command
    # reserved state.
    assert _body_attributes().get((RESERVED_METADATA_GROUP, "finish")) == "matte"


@pytest.mark.parametrize("hostile_mode", ["false_after_delete", "true_noop"])
@pytest.mark.asyncio
async def test_rollback_created_delete_result_must_be_verified_fail_closed(
    fake_desktop, hostile_mode
):
    """Finding 2 (rollback 'created' shape): compensation deletes registered
    for attributes this plan CREATED must require the documented True
    Attribute.deleteMe result AND post-delete re-enumeration proving the
    created reserved (name, value) record is observably absent. A False
    result that nevertheless mutated state, or a reported-True no-op, must
    fail the compensation closed with CAPABILITY_UNAVAILABLE / compensated=False —
    compensation success is never inferred from the final snapshot equality
    alone."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    tracker = cad_service.revision_tracker
    rec = tracker.current("doc_1")

    baseline_body_attrs = _body_attributes()

    attrs_cls, healthy_add, hostile_add = _arm_hostile_created_delete(
        fake_adsk, "finish", hostile_mode
    )
    attrs_cls.add = hostile_add
    try:
        _arm_post_apply_fingerprint_explosion()
        payload = {
            "operation": "set",
            "target": {
                "ref": body_ref,
                "kind": "body",
                "name": "Body1",
                "native_token": "body_token_1",
                "component_path": [],
            },
            "name": "finish",
            "value": "anodized",
            "expected_revision": rec.revision,
            "expected_fingerprint": rec.fingerprint,
            "document_ref": "doc_1",
        }
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_rollback_created_1",
            created_revision=tracker.next_revision("doc_1"),
        )
        script = FusionCadScriptBundle().build("mutate", payload)
        output = _exec_rendered_mutate(script)
    finally:
        attrs_cls.add = healthy_add

    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    details = output["error"]["details"]
    # The rollback delete failure must be reported as a compensation failure.
    assert details == {"operation": "set", "applied": False, "compensated": False}
    assert output["error"]["message"] == (
        "Metadata compensation failed or exact restoration could not be verified"
    )
    # The hostile deleteMe result object is never stringified into details.
    raw_dump = json.dumps(output, ensure_ascii=False, default=repr)
    assert _HOSTILE_DELETEME_MARKER not in raw_dump
    if hostile_mode == "false_after_delete":
        # The delete DID mutate persisted state (both created records are
        # gone), yet the bad Boolean result must still fail the compensation
        # closed instead of being accepted from snapshot equality.
        assert _body_attributes() == baseline_body_attrs


@pytest.mark.parametrize("hostile_mode", ["false_after_delete", "true_noop"])
@pytest.mark.asyncio
async def test_rollback_delete_created_by_name_result_must_be_verified_fail_closed(
    fake_desktop, hostile_mode
):
    """Finding 2 (rollback 'delete_created_by_name' shape): compensation
    deletes re-derived by enumeration after a failed/persisting add must
    require the documented True Attribute.deleteMe result AND post-delete
    re-enumeration proving matching reserved name(s) are observably absent.
    Either failure must fail the compensation closed with CAPABILITY_UNAVAILABLE /
    compensated=False."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    tracker = cad_service.revision_tracker
    rec = tracker.current("doc_1")

    baseline_body_attrs = _body_attributes()

    attrs_cls, healthy_add, hostile_add = _arm_null_add_with_hostile_persisted_delete(
        fake_adsk, "finish", hostile_mode
    )
    attrs_cls.add = hostile_add
    try:
        payload = {
            "operation": "set",
            "target": {
                "ref": body_ref,
                "kind": "body",
                "name": "Body1",
                "native_token": "body_token_1",
                "component_path": [],
            },
            "name": "finish",
            "value": "anodized",
            "expected_revision": rec.revision,
            "expected_fingerprint": rec.fingerprint,
            "document_ref": "doc_1",
        }
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_rollback_delname_1",
            created_revision=tracker.next_revision("doc_1"),
        )
        script = FusionCadScriptBundle().build("mutate", payload)
        output = _exec_rendered_mutate(script)
    finally:
        attrs_cls.add = healthy_add

    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    details = output["error"]["details"]
    # The rollback delete failure must be reported as a compensation failure.
    assert details == {"operation": "set", "applied": False, "compensated": False}
    assert output["error"]["message"] == (
        "Metadata compensation failed or exact restoration could not be verified"
    )
    if hostile_mode == "false_after_delete":
        # The delete DID mutate persisted state, yet the bad Boolean result
        # must still fail the compensation closed.
        assert _body_attributes() == baseline_body_attrs
        assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()


@pytest.mark.asyncio
async def test_service_rollback_created_delete_failure_fails_closed_rendered_pipeline(
    fake_desktop,
):
    """Rendered pipeline through the service: a rollback 'created' delete with
    a bad Boolean result (False after actual deletion) must fail the whole
    command closed with CAPABILITY_UNAVAILABLE; the failed command never advances
    the revision authority and never reports applied success."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_body_attrs = _body_attributes()
    baseline_doc_attrs = _document_attributes()

    attrs_cls, healthy_add, hostile_add = _arm_hostile_created_delete(
        fake_adsk, "finish", "false_after_delete"
    )
    attrs_cls.add = hostile_add
    try:
        _arm_post_apply_fingerprint_explosion()
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
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert desktop.mutation_calls == 1
    assert desktop.read_calls == 1
    # The compensation delete actually restored the pre-command reserved
    # state mechanically, yet the bad deleteMe Boolean still failed the
    # command closed (never accepted from snapshot equality).
    assert _body_attributes() == baseline_body_attrs
    assert _document_attributes() == baseline_doc_attrs
    # The failed command never advanced the revision authority.
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"


@pytest.mark.asyncio
async def test_service_rollback_delete_created_by_name_failure_fails_closed(
    fake_desktop,
):
    """Rendered pipeline through the service: a rollback
    'delete_created_by_name' delete with a bad Boolean result (False after
    actual deletion) must fail the whole command closed with
    CAPABILITY_UNAVAILABLE; the failed command never advances the revision
    authority and never reports applied success."""
    fake_adsk = fake_desktop["adsk"]
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)

    baseline_body_attrs = _body_attributes()

    attrs_cls, healthy_add, hostile_add = _arm_null_add_with_hostile_persisted_delete(
        fake_adsk, "finish", "false_after_delete"
    )
    attrs_cls.add = hostile_add
    try:
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
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert desktop.mutation_calls == 1
    assert desktop.read_calls == 1
    # The delete actually mutated persisted state, yet the bad Boolean result
    # must still fail the command closed.
    assert _body_attributes() == baseline_body_attrs
    assert ("bridge.cad/v1", PROVENANCE_ATTRIBUTE_NAME) not in _body_attributes()
    # The failed command never advanced the revision authority.
    assert cad_service.revision_tracker.current("doc_1").revision == "rev_1"


# =========================================================================
# Task 10 final repair: every post-fingerprint compensation is proven against
# the complete baseline; rollback failures normalize; empty plans undo once.
# =========================================================================


def _task10_plan_payload(cad_service, body_ref, operation):
    rec = cad_service.revision_tracker.current("doc_1")
    payload = {
        "operation": operation,
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
    if operation == "set":
        payload.update({"name": "finish", "value": "anodized"})
        apply_metadata_mutation_plan(
            payload,
            operation_id="op_task10_primary",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )
    else:
        apply_geometry_provenance_plan(
            payload,
            operation=operation,
            creator_operation=f"fusion_style:{operation}",
            operation_id="op_task10_fallback",
            created_revision=cad_service.revision_tracker.next_revision("doc_1"),
        )
    return payload, rec


def _task10_unstarted_scope(payload):
    script = FusionCadScriptBundle().build("mutate", payload)
    script = script.replace("        _output = run()", "        _output = None", 1)
    scope = {"__name__": "__main__"}
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    return scope


@pytest.mark.parametrize("add_failure", ["null", "mismatch", "internal"])
@pytest.mark.asyncio
async def test_internally_compensated_metadata_apply_requires_full_restoration_proof(
    fake_desktop, add_failure
):
    """A failed add may mutate before its bad result/exception is observed."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    payload, rec = _task10_plan_payload(cad_service, body_ref, "set")
    scope = _task10_unstarted_scope(payload)

    import adsk.core

    attrs_cls = type(adsk.core.Application.get().activeDocument.attributes)
    healthy_add = attrs_cls.add
    baseline_attrs = _body_attributes()
    fingerprint_calls = {"count": 0}

    def fingerprint(_payload=None):
        fingerprint_calls["count"] += 1
        if fingerprint_calls["count"] == 1:
            return rec.fingerprint, {}, "doc_1"
        return "not-the-restored-baseline", {}, "doc_1"

    def hostile_add(self, group_name, name, value):
        if add_failure == "internal" and name == PROVENANCE_ATTRIBUTE_NAME:
            raise RuntimeError("HOSTILE_INTERNAL_ADD_DIAGNOSTIC_AQAA")
        added = healthy_add(self, group_name, name, value)
        if name != "finish":
            return added
        if add_failure == "null":
            return None
        if add_failure == "mismatch":
            added.value = "mismatched-return-value"
            return added
        return added

    scope["collect_model_fingerprint"] = fingerprint
    attrs_cls.add = hostile_add
    try:
        with pytest.raises(scope["FusionScriptError"]) as exc:
            scope["run"]()
    finally:
        attrs_cls.add = healthy_add

    assert fingerprint_calls["count"] == 2
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    assert exc.value.details == {
        "operation": "set",
        "applied": False,
        "compensated": False,
    }
    assert _body_attributes() == baseline_attrs


@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.parametrize("post_mode", ["throw", "invalid", "unchanged"])
@pytest.mark.asyncio
async def test_post_fingerprint_metadata_compensation_requires_full_baseline_proof(
    fake_desktop, operation, post_mode
):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    payload, rec = _task10_plan_payload(cad_service, body_ref, operation)
    scope = _task10_unstarted_scope(payload)
    secret = "HOSTILE_POST_FINGERPRINT_VALUE_AQAA"
    calls = {"count": 0}

    def fingerprint(_payload=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return rec.fingerprint, {}, "doc_1"
        if calls["count"] == 2:
            if post_mode == "throw":
                raise RuntimeError(secret)
            if post_mode == "invalid":
                return "", {}, secret
            return rec.fingerprint, {}, "doc_1"
        raise RuntimeError(secret)

    scope["collect_model_fingerprint"] = fingerprint
    with pytest.raises(scope["FusionScriptError"]) as exc:
        scope["run"]()

    assert calls["count"] == 3
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    assert exc.value.message == (
        "Exact model restoration after metadata compensation could not be verified"
    )
    assert exc.value.details == {
        "operation": operation,
        "applied": False,
        "compensated": False,
    }
    assert secret not in json.dumps(exc.value.details)


@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.asyncio
async def test_metadata_rollback_failure_is_constant_capability_error(
    fake_desktop, operation
):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    payload, rec = _task10_plan_payload(cad_service, body_ref, operation)
    secret = "HOSTILE_ROLLBACK_PRIMITIVE_AQAA"
    target_name = "finish" if operation == "set" else PROVENANCE_ATTRIBUTE_NAME
    attrs_cls, healthy_add, hostile_add = _arm_hostile_created_delete(
        fake_desktop["adsk"], target_name, "false_after_delete"
    )
    attrs_cls.add = hostile_add
    try:
        scope = _task10_unstarted_scope(payload)
        calls = iter(
            [(rec.fingerprint, {}, "doc_1"), ("", {}, secret)]
        )
        scope["collect_model_fingerprint"] = lambda _payload=None: next(calls)
        with pytest.raises(scope["FusionScriptError"]) as exc:
            scope["run"]()
    finally:
        attrs_cls.add = healthy_add

    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    assert exc.value.message == (
        "Metadata compensation failed or exact restoration could not be verified"
    )
    assert exc.value.details == {
        "operation": operation,
        "applied": False,
        "compensated": False,
    }
    assert secret not in json.dumps(exc.value.details)
    assert secret not in exc.value.message


@pytest.mark.parametrize("operation", ["set", "show"])
@pytest.mark.asyncio
async def test_successful_empty_metadata_plan_rolls_back_exactly_once(
    fake_desktop, operation
):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    await _seed_baseline(cad_service, desktop)
    body_ref = _register_body_ref(cad_service)
    payload, rec = _task10_plan_payload(cad_service, body_ref, operation)
    payload["metadata_writes"] = []
    payload["metadata_removals"] = []
    script = FusionCadScriptBundle().build("mutate", payload)
    script = script.replace("        _output = run()", "        _output = None", 1)
    needle = "    def _rollback_metadata(owner, undo):\n"
    assert script.count(needle) == 1
    script = script.replace(
        needle,
        needle + "        globals()['_task10_rollback_calls'] += 1\n",
        1,
    )
    scope = {"__name__": "__main__", "_task10_rollback_calls": 0}
    exec(compile(script, "<rendered-production-script>", "exec"), scope)  # noqa: S102
    scope["collect_model_fingerprint"] = lambda _payload=None: (
        rec.fingerprint,
        {},
        "doc_1",
    )

    with pytest.raises(scope["FusionScriptError"]) as exc:
        scope["run"]()

    assert exc.value.code == "INVALID_ARGUMENT"
    assert scope["_task10_rollback_calls"] == 1


# =========================================================================
# Task 11: logical Unicode text and visibility service boundary
# =========================================================================


def test_task11_rendered_style_script_fails_closed_without_verified_adapter():
    script = FusionCadScriptBundle().build(
        "mutate",
        {
            "operation": "text_create",
            "text": "РАСПИСАНИЕ ПЫТОК 😈",
            "font": "Arial",
            "height_mm": 6.0,
            "expected_revision": "rev_1",
            "expected_fingerprint": "fingerprint",
            "document_ref": "doc_1",
        },
    )
    output = _exec_rendered_mutate(script)
    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert output["error"]["details"]["applied"] is False
    assert "verified Fusion style adapter" in output["error"]["message"]


def test_task11_rendered_text_rejects_self_attested_provenance_and_persists_plan(
    fake_desktop,
):
    fake_adsk = fake_desktop["adsk"]
    logical_ref = "text_schedule_01"
    payload = {
        "operation": "text_create",
        "text": "РАСПИСАНИЕ ПЫТОК 😈",
        "font": "Arial",
        "height_mm": 6.0,
        "logical_object_ref": logical_ref,
        "expected_revision": "rev_1",
        "expected_fingerprint": "replaced-with-observed-baseline",
        "document_ref": "doc_1",
        "provenance": {
            "creator_tool": "bridge.fusion-cad-agent",
            "creator_operation": "fusion_style:text_create",
            "operation_id": "op_task11_rendered_1",
            "logical_object_ref": logical_ref,
            "created_revision": "rev_2",
            "tags": [],
        },
    }
    # Obtain the real baseline rather than trusting the placeholder above.
    read_scope = {"__name__": "__main__"}
    read_script = FusionCadScriptBundle().build(
        "read", {"operation": "model_snapshot", "document_ref": "doc_1"}
    )
    exec(compile(read_script, "<task11-baseline>", "exec"), read_scope)  # noqa: S102
    payload["expected_fingerprint"] = read_scope["_output"]["data"]["fingerprint"]
    apply_geometry_provenance_plan(
        payload,
        operation="text_create",
        creator_operation="fusion_style:text_create",
        operation_id="op_task11_rendered_1",
        created_revision="rev_2",
    )
    payload["style_semantic_contract"] = "task11.v1"

    def style_primitive(command):
        fake_adsk.volume += 1.0
        return {
            "lineage": {
                "logical_ref": command["logical_object_ref"],
                "generation": 1,
                "is_current": True,
                "sketch": "ent_sketch_text_1",
                "sketch_text_id": "ent_sketch_text_1",
                "feature": None,
                "outputs": [],
                "text": command["text"],
                "font_requested": command["font"],
                "font_used": command["font"],
                "fallback_reason": None,
                "height_mm": command["height_mm"],
            },
            "provenance": command["provenance"],
            "persisted_provenance": command["provenance"],
            "same_operation_provenance": True,
        }

    baseline_volume = fake_adsk.volume
    script = FusionCadScriptBundle().build("mutate", payload)
    scope = {
        "__name__": "__main__",
        "_style_primitive": style_primitive,
        "_mutation_compensation_capture": lambda _command: fake_adsk.volume,
        "_mutation_compensation_rollback": lambda captured: (
            setattr(fake_adsk, "volume", captured) or True
        ),
    }
    exec(compile(script, "<task11-success>", "exec"), scope)  # noqa: S102
    output = scope["_output"]
    assert output["status"] == "failed"
    assert output["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert "provenance owner" in output["error"]["message"]
    assert fake_adsk.volume == baseline_volume

    def authoritative_style_primitive(command):
        result = style_primitive(command)
        result["provenance_owner"] = {
            "ref": "ent_body_01",
            "native_token": "body_token_1",
        }
        return result

    persisted_scope = {
        "__name__": "__main__",
        "_style_primitive": authoritative_style_primitive,
        "_mutation_compensation_capture": lambda _command: fake_adsk.volume,
        "_mutation_compensation_rollback": lambda captured: (
            setattr(fake_adsk, "volume", captured) or True
        ),
    }
    exec(compile(script, "<task11-persisted-provenance>", "exec"), persisted_scope)  # noqa: S102
    persisted_output = persisted_scope["_output"]
    assert persisted_output["status"] == "succeeded"
    assert persisted_output["data"]["lineage"]["text"] == "РАСПИСАНИЕ ПЫТОК 😈"
    assert persisted_output["data"]["same_operation_provenance"] is True
    assert persisted_output["data"]["persisted_provenance"] == payload["provenance"]


@pytest.mark.asyncio
async def test_task11_visibility_requires_expected_revision_before_dispatch(fake_desktop):
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())
    body_ref = _register_body_ref(cad_service)

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "hide", "target": body_ref},
            group="style",
        )

    assert exc.value.code == ErrorCode.REVISION_CONFLICT
    assert desktop.mutation_calls == 0

@pytest.mark.asyncio
async def test_task12_rendered_validate_unpacks_fingerprint_tuple(fake_desktop):
    """Rendered validate:run must consume the shared fingerprint helper tuple."""
    desktop = fake_desktop["desktop"]
    cad_service = FusionCadService(desktop)
    cad_service.set_node_capabilities("desk-1", _metadata_matrix())

    result = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "run",
            "profiles": ["parametric_health"],
        },
        group="validate",
    )

    assert isinstance(result, CadResult)
    assert result.status == "succeeded"
    assert result.data["read_only"] is True
    assert "native_token" not in result.model_dump_json()

@pytest.mark.asyncio
async def test_task13_non_spike_stage_remains_stageable_but_preview_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(name="revision.external_change_detection", state="supported"),
            ]
        ),
    )
    cad_service.revision_tracker.observe("doc_1", "fp_non_spike")
    cad_service.revision_tracker.begin_transaction(
        "tx_non_spike", "doc_1", "rev_1", "fp_non_spike"
    )
    cad_service.transaction_store.begin(
        "tx_non_spike",
        "doc_1",
        "rev_1",
        "fp_non_spike",
        {"structural_hash": "fp_non_spike", "counts": {}, "refs": []},
    )
    mock_desktop_service.submit = AsyncMock(
        return_value={"status": "queued", "operation_id": "op_stage_non_spike"}
    )
    staged = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "stage",
            "transaction_id": "tx_non_spike",
            "action": {"action_type": "show", "target": "ent_1"},
        },
        group="transaction",
    )
    assert staged["status"] == "queued"

    cad_service.transaction_store.stage(
        "tx_non_spike", {"action_type": "show", "target": "ent_1"}
    )
    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {
                "node_id": "desk-1",
                "operation": "preview",
                "transaction_id": "tx_non_spike",
            },
            group="transaction",
        )
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE

@pytest.mark.asyncio
async def test_task13_degraded_transaction_capability_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    degraded = CapabilityMatrix.from_records(
        [
            CapabilityRecord(
                name="transaction.preview_replay",
                state="degraded",
                limitations=("Live acceptance pending",),
            ),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", degraded)
    mock_desktop_service.submit = AsyncMock(
        return_value={"status": "queued", "operation_id": "op_tx_begin"}
    )

    with pytest.raises(FusionCadError) as exc_degraded:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "begin", "transaction_id": "tx_feas_1"},
            group="transaction",
        )
    assert exc_degraded.value.code == ErrorCode.CAPABILITY_DEGRADED
    assert mock_desktop_service.submit.call_count == 0

    unavailable = CapabilityMatrix.from_records(
        [
            CapabilityRecord(name="transaction.preview_replay", state="unavailable"),
            CapabilityRecord(
                name="revision.external_change_detection", state="supported"
            ),
        ]
    )
    cad_service.set_node_capabilities("desk-1", unavailable)
    with pytest.raises(FusionCadError) as exc_unavailable:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "begin", "transaction_id": "tx_feas_2"},
            group="transaction",
        )
    assert exc_unavailable.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert mock_desktop_service.submit.call_count == 0


@pytest.mark.asyncio
async def test_task13_degraded_non_spike_preview_still_fails_closed(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(
                    name="transaction.preview_replay",
                    state="degraded",
                    limitations=("Live acceptance pending",),
                ),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        ),
    )
    rec = cad_service.revision_tracker.observe("doc_1", "fp_base")
    cad_service.revision_tracker.begin_transaction(
        "tx_nonspike", "doc_1", rec.revision, "fp_base"
    )
    cad_service.transaction_store.begin(
        "tx_nonspike", "doc_1", rec.revision, "fp_base", {}
    )
    cad_service.transaction_store.stage(
        "tx_nonspike", {"action_type": "show", "target": "ent_existing"}
    )

    with pytest.raises(FusionCadError) as exc:
        await cad_service.execute(
            {"node_id": "desk-1", "operation": "preview", "transaction_id": "tx_nonspike"},
            group="transaction",
        )
    assert exc.value.code == ErrorCode.CAPABILITY_DEGRADED
    assert mock_desktop_service.submit.call_count == 0


def test_task13_commit_native_hint_becomes_opaque_ref_only_after_terminal_success(
    mock_desktop_service: DesktopNodeService,
):
    cad_service = FusionCadService(mock_desktop_service)
    rec = cad_service.revision_tracker.observe("doc_1", "fp_base")
    cad_service.revision_tracker.begin_transaction(
        "tx_ref_1", "doc_1", rec.revision, "fp_base"
    )
    provenance = {
        "creator_tool": "bridge.fusion-cad-agent",
        "creator_operation": "fusion_style:text_create",
        "operation_id": "op_123456789abc",
        "transaction_id": "tx_ref_1",
        "logical_object_ref": "text_123456789abcdef0",
        "created_revision": "rev_2",
        "tags": [],
    }
    cad_service.transaction_store.begin(
        "tx_ref_1", "doc_1", rec.revision, "fp_base", {}
    )
    cad_service.transaction_store.stage(
        "tx_ref_1",
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "height_mm": 4.0,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
            "provenance": provenance,
        },
    )
    signature = {
        "plan_hash": cad_service.transaction_store.get("tx_ref_1").plan_hash,
        "structural_hash": "fp_after",
        "mutation_counts": {"sketches": 1},
        "provenance": {"identity": provenance, "persisted": provenance, "same_operation": True},
    }
    cad_service.transaction_store.begin_preview("tx_ref_1", "fp_base")
    cad_service.transaction_store.finish_preview(
        "tx_ref_1", preview={"replay_signature": signature}
    )
    cad_service.transaction_store.begin_commit("tx_ref_1", "fp_base")
    native = "native::text::secret"
    result = CadResult(
        status="succeeded",
        summary="Committed exact staged transaction plan",
        data={
            "transaction_id": "tx_ref_1",
            "operation": "commit",
            "applied": True,
            "fingerprint": "fp_after",
            "document_ref": "doc_1",
            "internal_ref_hints": [{"kind": "sketch_text", "native_token": native}],
            "provenance": provenance,
            "persisted_provenance": provenance,
            "replay_signature": signature,
        },
    )
    finalized = cad_service._finalize_completed_execution(
        result,
        effective_bundle_group="transaction",
        op="commit",
        payload={"transaction_id": "tx_ref_1", "document_ref": "doc_1"},
        node_id="desk-1",
    )
    assert isinstance(finalized, CadResult)
    assert len(finalized.changed_refs) == 1
    opaque = finalized.changed_refs[0]
    assert opaque.startswith("ent_")
    assert native not in finalized.model_dump_json()
    assert "internal_ref_hints" not in finalized.data
    stored = cad_service.ref_registry.get_internal_record(opaque, "doc_1")
    assert stored is not None
    assert stored.native_token == native
    assert cad_service.revision_tracker.get_transaction_baseline("tx_ref_1") is None

    failed_service = FusionCadService(mock_desktop_service)
    failed_rec = failed_service.revision_tracker.observe("doc_1", "fp_base")
    failed_service.revision_tracker.begin_transaction(
        "tx_ref_fail", "doc_1", failed_rec.revision, "fp_base"
    )
    failed_service.transaction_store.begin(
        "tx_ref_fail", "doc_1", failed_rec.revision, "fp_base", {}
    )
    failed_provenance = dict(provenance)
    failed_provenance["transaction_id"] = "tx_ref_fail"
    failed_service.transaction_store.stage(
        "tx_ref_fail",
        {
            "action_type": "text_create",
            "text": "ПЫТОК",
            "height_mm": 4.0,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0, "frame": {"space": "world"}},
            "provenance": failed_provenance,
        },
    )
    failed = CadResult(
        status="succeeded",
        summary="failed logical commit",
        data={
            "transaction_id": "tx_ref_fail",
            "operation": "commit",
            "applied": False,
            "fingerprint": "fp_after",
            "document_ref": "doc_1",
            "internal_ref_hints": [{"kind": "sketch_text", "native_token": native}],
            "provenance": failed_provenance,
            "persisted_provenance": failed_provenance,
        },
    )
    with pytest.raises(FusionCadError):
        failed_service._finalize_completed_execution(
            failed,
            effective_bundle_group="transaction",
            op="commit",
            payload={"transaction_id": "tx_ref_fail", "document_ref": "doc_1"},
            node_id="desk-1",
        )
    assert failed_service.ref_registry.get_internal_record("ent_missing", "doc_1") is None
    assert not failed_service.ref_registry.has_document("doc_1")


def test_task13_mismatching_commit_signature_fails_without_second_dispatch():
    mock_desktop_service = MagicMock(spec=DesktopNodeService)
    mock_desktop_service.call.call_count = 1  # the already-completed native commit dispatch
    service = FusionCadService(mock_desktop_service)
    rec = service.revision_tracker.observe("doc_1", "fp_base")
    service.revision_tracker.begin_transaction("tx_mismatch", "doc_1", rec.revision, "fp_base")
    service.transaction_store.begin("tx_mismatch", "doc_1", rec.revision, "fp_base", {})
    staged = service.transaction_store.stage("tx_mismatch", {"action_type": "text_create"})
    accepted = {"plan_hash": staged.plan_hash, "structural_hash": "preview-b", "mutation_counts": {"sketches": 1}, "provenance": {"identity": {"transaction_id": "tx_mismatch"}, "persisted": {"transaction_id": "tx_mismatch"}, "same_operation": True}}
    service.transaction_store.begin_preview("tx_mismatch", "fp_base")
    service.transaction_store.finish_preview("tx_mismatch", preview={"replay_signature": accepted})
    service.transaction_store.begin_commit("tx_mismatch", "fp_base")
    divergent = dict(accepted, structural_hash="commit-c-different")
    result = CadResult(status="succeeded", summary="native commit returned", data={"transaction_id": "tx_mismatch", "operation": "commit", "applied": True, "document_ref": "doc_1", "fingerprint": "fp_after", "replay_signature": divergent})

    with pytest.raises(FusionCadError) as exc:
        service._finalize_completed_execution(result, effective_bundle_group="transaction", op="commit", payload={"transaction_id": "tx_mismatch", "document_ref": "doc_1"}, node_id="desk-1")

    assert exc.value.code == ErrorCode.TRANSACTION_CONFLICT
    assert exc.value.details["applied"] is True
    assert mock_desktop_service.call.call_count == 1
    assert service.transaction_store.get("tx_mismatch").state is TransactionState.COMMITTING


@pytest.mark.asyncio
async def test_task13_commit_without_accepted_preview_fails_before_dispatch(
    mock_desktop_service: DesktopNodeService,
):
    service = FusionCadService(mock_desktop_service)
    service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(
                    name="transaction.preview_replay", state="supported"
                ),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        ),
    )
    rec = service.revision_tracker.observe("doc_1", "fp_base")
    service.revision_tracker.begin_transaction(
        "tx_no_preview", "doc_1", rec.revision, rec.fingerprint
    )
    service.transaction_store.begin(
        "tx_no_preview", "doc_1", rec.revision, rec.fingerprint, {}
    )
    service.transaction_store.stage(
        "tx_no_preview", {"action_type": "text_create"}
    )
    mock_desktop_service.submit = AsyncMock(
        return_value={"status": "queued", "operation_id": "op_must_not_dispatch"}
    )

    with pytest.raises(FusionCadError) as exc:
        await service.execute(
            {
                "node_id": "desk-1",
                "operation": "commit",
                "transaction_id": "tx_no_preview",
            },
            group="transaction",
        )

    assert exc.value.code == ErrorCode.TRANSACTION_CONFLICT
    assert mock_desktop_service.call.call_count == 0
    assert mock_desktop_service.submit.call_count == 0


@pytest.mark.asyncio
async def test_sync_externalized_domain_result_rewrites_raw_artifact_with_finalized_public_payload(
    mock_desktop_service: DesktopNodeService,
    monkeypatch,
):
    cad_service = FusionCadService(mock_desktop_service)
    raw_ref = {"external_result": {"result_id": "raw_result_12345678"}}
    raw_full = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Raw adapter result",
        "data": {"native_token": "native::must-not-leak"},
    }
    public = CadResult(
        status="succeeded",
        summary="Finalized public result",
        data={"safe": True},
    )
    mock_desktop_service.call = AsyncMock(return_value=raw_ref)
    mock_desktop_service.external_result = MagicMock(return_value=(raw_full, {}))
    mock_desktop_service.overwrite_external_result = MagicMock()
    mock_desktop_service.get_session_generation = MagicMock(return_value=1)
    monkeypatch.setattr(
        cad_service,
        "_finalize_completed_execution",
        MagicMock(return_value=public),
    )

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )

    assert result == raw_ref
    mock_desktop_service.overwrite_external_result.assert_called_once_with(
        raw_ref["external_result"],
        public.model_dump(mode="python", exclude_none=True),
    )


@pytest.mark.asyncio
async def test_externalized_capabilities_overlay_hands_and_persist_generation_bound_matrix(
    mock_desktop_service: DesktopNodeService,
):
    settings = BridgeSettings.model_validate({
        "fusion_cad": {
            "provider_routes": {
                "desk-1": {
                    "reference_node": "desk-1",
                    "rich_node": "rich-1",
                }
            }
        }
    })
    cad_service = FusionCadService(
        mock_desktop_service,
        provider_router=FusionCadProviderRouter(settings.fusion_cad),
    )
    raw_ref = {"external_result": {"result_id": "capabilities_external_12345678"}}
    raw_full = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Runtime capabilities probed",
        "data": {
            "application": "Autodesk Fusion",
            "fusion_version": "2.0.18000",
            "probe_facts": {
                "has_app": True,
                "has_design_access": True,
                "has_entity_token_resolver": True,
            },
        },
        "capabilities": [
            {"name": "design.access", "state": "supported"},
            {"name": "entity.token_resolver", "state": "supported"},
        ],
    }
    mock_desktop_service.call = AsyncMock(return_value=raw_ref)
    mock_desktop_service.external_result = MagicMock(return_value=(raw_full, {}))
    mock_desktop_service.overwrite_external_result = MagicMock()
    mock_desktop_service.get_session_generation = MagicMock(return_value=1)

    result = await cad_service.execute(
        {"node_id": "desk-1", "operation": "capabilities"}, group="read"
    )

    assert result == raw_ref
    rewritten = mock_desktop_service.overwrite_external_result.call_args.args[1]
    returned = {record["name"]: record for record in rewritten["capabilities"]}
    assert returned["hands.sketch"]["state"] == "degraded"
    assert returned["hands.feature"]["state"] == "degraded"
    saved = cad_service.get_node_capabilities("desk-1")
    assert saved is not None
    assert saved.get("hands.sketch").state == "degraded"
    assert saved.get("hands.feature").state == "degraded"


@pytest.mark.asyncio
async def test_task14_async_terminal_finalization_preserves_service_prepared_context(
    mock_desktop_service: DesktopNodeService,
):
    """Regression: durable queued mutations must retain the sanitized prepared payload
    needed to validate their later terminal result, not only routing identifiers."""
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="style.sketch_text", state="supported"),
                CapabilityRecord(name="design.access", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        ),
    )
    cad_service.revision_tracker.observe("doc_1", "fp_before")
    captured: dict[str, object] = {}

    async def queued_submit(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        return {"operation_id": "op_async_text_create", "status": "queued"}

    mock_desktop_service.submit = AsyncMock(side_effect=queued_submit)
    queued = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "text_create",
            "text": "Schedule",
            "height_mm": 4.0,
            "position": {
                "x": 10.0,
                "y": 20.0,
                "z": 0.0,
                "frame": {"space": "world"},
            },
            "expected_revision": "rev_1",
            "document_ref": "doc_1",
        },
        group="style",
    )
    assert queued == {"operation_id": "op_async_text_create", "status": "queued"}

    journal = captured["journal"]
    assert isinstance(journal, dict)
    checkpoint = journal["checkpoint"]
    assert isinstance(checkpoint, dict)
    context = checkpoint["finalization_payload"]
    assert isinstance(context, dict)
    assert context["logical_object_ref"].startswith("text_")
    assert context["style_semantic_contract"] == "task11.v1"
    assert isinstance(context["provenance"], dict)
    assert "native_token" not in repr(context)

    provenance = context["provenance"]
    logical_ref = context["logical_object_ref"]
    finalized = cad_service.finalize_terminal_operation(
        {
            **journal,
            "operation_id": "op_async_text_create",
            "node_id": "desk-1",
            "status": "succeeded",
        },
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Text created",
            "document": {"document_ref": "doc_1", "model_revision": "rev_2"},
            "data": {
                "fingerprint": "fp_after",
                "applied": True,
                "lineage": {
                    "logical_ref": logical_ref,
                    "generation": 1,
                    "is_current": True,
                    "text": "Schedule",
                    "font_requested": "Arial",
                    "font_used": "Arial",
                    "height_mm": 4.0,
                },
                "provenance": provenance,
                "persisted_provenance": provenance,
                "same_operation_provenance": True,
            },
        },
    )
    assert isinstance(finalized, CadResult)
    assert finalized.data["lineage"]["logical_ref"] == logical_ref
    assert finalized.data["same_operation_provenance"] is True


@pytest.mark.asyncio
async def test_transaction_preview_with_large_baseline_uses_bounded_finalization_checkpoint(
    real_desktop_service: DesktopNodeService,
):
    await real_desktop_service.register(
        "desk-1", [{"name": "fusion_mcp_execute"}], True
    )
    cad_service = FusionCadService(real_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [
                CapabilityRecord(name="transaction.preview_replay", state="supported"),
                CapabilityRecord(
                    name="revision.external_change_detection", state="supported"
                ),
            ]
        ),
    )
    baseline = {
        "structural_hash": "fp_large_baseline",
        "counts": {"bodies": 180},
        "bodies": [
            {"ref": f"ent_body_{index:04d}", "name": "Bracket-" + ("x" * 64)}
            for index in range(180)
        ],
    }
    assert len(json.dumps(baseline).encode("utf-8")) > 8192
    rec = cad_service.revision_tracker.observe("doc_1", "fp_large_baseline")
    cad_service.revision_tracker.begin_transaction(
        "tx_large_baseline", "doc_1", rec.revision, rec.fingerprint
    )
    cad_service.transaction_store.begin(
        "tx_large_baseline",
        "doc_1",
        rec.revision,
        rec.fingerprint,
        baseline,
    )
    cad_service.transaction_store.stage(
        "tx_large_baseline",
        {
            "action_type": "text_create",
            "text": "Schedule",
            "height_mm": 4.0,
            "position": {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "frame": {"space": "world"},
            },
        },
    )

    queued = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "preview",
            "transaction_id": "tx_large_baseline",
        },
        group="transaction",
    )
    status = real_desktop_service.operation_status(
        "desk-1", queued["operation_id"]
    )
    checkpoint = status["checkpoint"]
    assert "baseline_snapshot" not in checkpoint["finalization_payload"]
    assert len(json.dumps(checkpoint).encode("utf-8")) < 8192

    finalized = cad_service.finalize_terminal_operation(
        {**status, "status": "succeeded"},
        {
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Previewed transaction",
            "document": {"document_ref": "doc_1", "model_revision": "rev_1"},
            "data": {
                "operation": "preview",
                "transaction_id": "tx_large_baseline",
                "document_ref": "doc_1",
                "applied": False,
                    "fingerprint": "fp_large_baseline",
                    "replay_signature": {
                        "plan_hash": cad_service.transaction_store.get("tx_large_baseline").plan_hash,
                        "structural_hash": "fp_preview",
                        "mutation_counts": {"sketches": 1},
                        "provenance": {"identity": None, "persisted": None, "same_operation": True},
                    },
                },
                "validation": {
                    "document_ref": "doc_1", "features": [], "sketches": [],
                    "references": [], "bodies": [], "text_outputs": [],
                    "timeline": {"available": True, "rolled_back": False}, "limitations": [],
                },
            },
    )

    assert isinstance(finalized, CadResult)
    transaction = cad_service.transaction_store.get("tx_large_baseline")
    assert transaction.state.value == "STAGED"
    assert transaction.preview_evidence is not None
    assert transaction.preview_evidence["durable"] is False


@pytest.mark.asyncio
async def test_task14_async_full_snapshot_checkpoint_preserves_detail_option(
    mock_desktop_service: DesktopNodeService,
):
    """Regression: async reads must retain finalization options such as full snapshot detail."""
    cad_service = FusionCadService(mock_desktop_service)
    cad_service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [CapabilityRecord(name="design.access", state="supported")]
        ),
    )
    captured: dict[str, object] = {}

    async def queued_submit(node_id, tool_name, arguments, journal=None):
        captured["journal"] = journal
        return {"operation_id": "op_async_full_snapshot", "status": "queued"}

    mock_desktop_service.submit = AsyncMock(side_effect=queued_submit)
    queued = await cad_service.execute(
        {
            "node_id": "desk-1",
            "operation": "model_snapshot",
            "detail": "full",
            "document_ref": "doc_1",
        },
        group="read",
    )
    assert queued == {"operation_id": "op_async_full_snapshot", "status": "queued"}
    journal = captured["journal"]
    assert isinstance(journal, dict)
    checkpoint = journal["checkpoint"]
    assert isinstance(checkpoint, dict)
    context = checkpoint["finalization_payload"]
    assert context["detail"] == "full"
    assert context["operation"] == "model_snapshot"

@pytest.mark.asyncio
async def test_final_p0_commit_is_reserved_before_async_submit_and_duplicate_is_blocked(mock_desktop_service: DesktopNodeService):
    import asyncio
    service=FusionCadService(mock_desktop_service)
    service.set_node_capabilities('desk-1', CapabilityMatrix.from_records([
        CapabilityRecord(name='transaction.preview_replay',state='supported'),
        CapabilityRecord(name='revision.external_change_detection',state='supported'),
        CapabilityRecord(name='design.access',state='supported'),
    ]))
    cur=service.revision_tracker.observe('doc_1','fp_base')
    service.revision_tracker.begin_transaction('tx_reserve','doc_1',cur.revision,cur.fingerprint)
    service.transaction_store.begin('tx_reserve','doc_1',cur.revision,cur.fingerprint,{})
    staged=service.transaction_store.stage('tx_reserve',{'action_type':'text_create'})
    service.transaction_store.begin_preview('tx_reserve',cur.fingerprint)
    service.transaction_store.finish_preview('tx_reserve',preview={'replay_signature':{'plan_hash':staged.plan_hash}})
    entered=asyncio.Event(); release=asyncio.Event()
    async def delayed(*_a,**_kw):
        entered.set(); await release.wait()
        return {'status':'queued','operation_id':'op_first'}
    mock_desktop_service.submit=AsyncMock(side_effect=delayed)
    first=asyncio.create_task(service.execute({'node_id':'desk-1','operation':'commit','transaction_id':'tx_reserve'},group='transaction'))
    await asyncio.wait_for(entered.wait(),1.0)
    assert service.transaction_store.get('tx_reserve').state is TransactionState.COMMITTING
    with pytest.raises(FusionCadError) as exc:
        await service.execute({'node_id':'desk-1','operation':'commit','transaction_id':'tx_reserve'},group='transaction')
    assert exc.value.code==ErrorCode.TRANSACTION_CONFLICT
    assert mock_desktop_service.submit.await_count==1
    release.set(); assert await first=={'status':'queued','operation_id':'op_first'}
    assert service.transaction_store.get('tx_reserve').state is TransactionState.COMMITTING


def test_decode_domain_result_accepts_strict_fusion_mcp_exception_transport() -> None:
    import base64

    payload = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "transport ok",
        "data": {"probe": True},
        "changed_refs": [],
        "warnings": [],
        "artifacts": [],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    raw = {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "error": "Traceback (most recent call last):\nRuntimeError: BRIDGE_CAD_RESULT_V1:" + encoded + "\n",
                "success": False,
            }),
        }],
        "is_error": False,
        "result_type": "complete",
    }

    result = FusionCadService.decode_domain_result(raw)
    assert result.status == "succeeded"
    assert result.summary == "transport ok"
    assert result.data["probe"] is True

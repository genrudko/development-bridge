from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.capabilities import CapabilityMatrix
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.models import CapabilityRecord
from app.fusion_cad.providers import FusionCadProviderRoute
from app.fusion_cad.requests import FusionFeatureRequest, FusionSketchRequest
from app.fusion_cad.service import FusionCadService
from app.fusion_cad.snapshots import normalize_snapshot


GUARD_A = "a" * 64
GUARD_B = "b" * 64
GUARD_C = "c" * 64
PRIVATE_API_VERSION = "bridge.shimmer/v1"


class Router:
    def __init__(self, rich="rich-a"):
        self.rich = rich

    def route(self, logical_node):
        return FusionCadProviderRoute(logical_node, "reference-a", self.rich)

    def require(self, logical_node, role):
        node = getattr(self.route(logical_node), f"{role}_node")
        if node is None:
            from app.fusion_cad.providers import FusionCadProviderUnavailable
            raise FusionCadProviderUnavailable(logical_node, role)
        return node


class MultiRouter:
    def route(self, logical_node):
        rich = {"logical-a": "rich-a", "logical-b": "rich-b"}.get(logical_node)
        return FusionCadProviderRoute(logical_node, "reference-a", rich)

    def require(self, logical_node, role):
        node = getattr(self.route(logical_node), f"{role}_node")
        if node is None:
            from app.fusion_cad.providers import FusionCadProviderUnavailable
            raise FusionCadProviderUnavailable(logical_node, role)
        return node


class FakeDesktop:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []
        self.generations = {}

    async def call(
        self, node_id, tool_name, arguments, journal=None, expected_session_generation=None
    ):
        self.calls.append((node_id, tool_name, arguments, journal, expected_session_generation))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def get_session_generation(self, node_id):
        return self.generations.get(node_id, 1)


def _seed_hands_binding(service, revision, guard, *, generation=1, rich_node="rich-a"):
    key = (rich_node, "doc_a", revision)
    service._hands_provider_guards[key] = guard
    service._hands_provider_guard_sessions[key] = (rich_node, generation)


def _store_hands_snapshot(
    service, document_ref, fingerprint, *, sketches=(), bodies=(), components=(), features=()
):
    snapshot = normalize_snapshot(
        {
            "document_ref": document_ref,
            "model_revision": service.revision_tracker.current(document_ref).revision
            if service.revision_tracker.current(document_ref) is not None
            else "rev_1",
            "fingerprint": fingerprint,
            "components": list(components),
            "bodies": list(bodies),
            "sketches": list(sketches),
            "features": list(features),
            "parameters": [],
        },
        ref_registry=service.ref_registry,
    )
    service.snapshot_store.put(snapshot)
    return snapshot


@pytest.mark.asyncio
async def test_hands_bindings_for_same_document_revision_stay_independent_per_rich_provider(monkeypatch):
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
        _preview_receipt(guard=GUARD_A),
        _preview_receipt(guard=GUARD_B),
    ])
    service = FusionCadService(desktop, provider_router=MultiRouter())
    revision = service.revision_tracker.observe("doc_a", "1" * 64)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)

    await service.bind_hands_provider("logical-a", "doc_a")
    await service.bind_hands_provider("logical-b", "doc_a")

    first = await service.apply_hands_provider(
        "logical-a", "doc_a", expected_revision=revision.revision, mode="preview", operations=[]
    )
    second = await service.apply_hands_provider(
        "logical-b", "doc_a", expected_revision=revision.revision, mode="preview", operations=[]
    )

    assert first.data["baseline_restored"] is True
    assert second.data["baseline_restored"] is True
    assert [call[0] for call in desktop.calls] == [
        "rich-a", "rich-a", "rich-b", "rich-b", "rich-a", "rich-b"
    ]


@pytest.mark.asyncio
async def test_public_hands_binds_current_rich_provider_instead_of_consuming_other_route_binding(monkeypatch):
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
        _preview_receipt(guard=GUARD_B, effects=[{"op": "sketch.create"}]),
    ])
    service = FusionCadService(desktop, provider_router=MultiRouter())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, GUARD_A)
    _enable_hands_capability(service, "hands.sketch", monkeypatch)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-b",
            "document_ref": "doc_a",
            "operation": "create",
            "plane": "xy",
            "expected_revision": old.revision,
            "dry_run": True,
        },
    )

    result = await service.execute(request)

    assert result.data["baseline_restored"] is True
    assert [call[0] for call in desktop.calls] == ["rich-b", "rich-b", "rich-b"]


@pytest.mark.asyncio
async def test_guard_binding_requires_configured_rich_node():
    service = FusionCadService(FakeDesktop(), provider_router=Router(rich=None))
    with pytest.raises(FusionCadError) as exc_info:
        await service.bind_hands_provider("logical-a", "doc_a")
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_guard_binding_rejects_ab_mismatch(monkeypatch):
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    service.revision_tracker.observe("doc_a", "a" * 64)
    async def observe(_node, _document):
        return service.revision_tracker.current("doc_a")
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.bind_hands_provider("logical-a", "doc_a")

    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert service.get_hands_provider_guard("rich-a", "doc_a", "rev_1") is None


@pytest.mark.asyncio
async def test_apply_rejects_stale_revision_before_provider_call():
    desktop = FakeDesktop()
    service = FusionCadService(desktop, provider_router=Router())
    service.revision_tracker.observe("doc_a", "a" * 64)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision="rev_0", mode="commit", operations=[]
        )

    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert desktop.calls == []


@pytest.mark.asyncio
async def test_apply_rejects_opaque_ref_kind_mismatch_before_provider_call():
    desktop = FakeDesktop()
    service = FusionCadService(desktop, provider_router=Router())
    service.revision_tracker.observe("doc_a", "a" * 64)
    _seed_hands_binding(service, "rev_1", GUARD_A)
    ref = service.ref_registry.issue(document_ref="doc_a", kind="body", native_token="native-secret")

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision="rev_1", mode="commit",
            operations=[{"op": "fillet", "target": {"ref": ref.ref, "expected_kind": "edge"}}],
        )

    assert exc_info.value.code == ErrorCode.TYPE_MISMATCH
    assert desktop.calls == []


@pytest.mark.asyncio
async def test_preview_does_not_register_created_native_tokens():
    desktop = FakeDesktop([{
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "guard_before": GUARD_A, "guard_after": GUARD_A, "effects": [],
        "created": [{"native_token": "native-secret", "kind": "sketch"}], "changed": [],
        "committed": False, "baseline_restored": True,
    }])
    service = FusionCadService(desktop, provider_router=Router())
    service.revision_tracker.observe("doc_a", "a" * 64)
    _seed_hands_binding(service, "rev_1", GUARD_A)

    result = await service.apply_hands_provider(
        "logical-a", "doc_a", expected_revision="rev_1", mode="preview", operations=[]
    )

    assert result.changed_refs == ()
    assert service.ref_registry.get_internal_record("ent_missing", "doc_a") is None
    assert "native-secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_commit_registers_created_tokens_as_opaque_refs_only(monkeypatch):
    guard_a = "a" * 64
    guard_b = "b" * 64
    desktop = FakeDesktop([
        {
            "api_version": "bridge.shimmer/v1",
            "document_ref": "doc_a",
            "mode": "commit", "guard_before": guard_a, "guard_after": guard_b, "effects": [],
            "entities": {"created": [{"token": "native-secret", "kind": "sketch"}], "changed": []},
        },
        {"api_version": "bridge.shimmer/v1", "guard": guard_b, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, guard_a)

    async def post_observe(_node, document_ref):
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            sketches=[{"name": "HandsSketch", "entityToken": "native-secret"}],
        )
        return revision
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    result = await service.apply_hands_provider(
        "logical-a", "doc_a", expected_revision=old.revision, mode="commit", operations=[]
    )

    assert len(result.changed_refs) == 1
    assert result.changed_refs[0].startswith("ent_")
    assert "native-secret" not in result.model_dump_json()
    record = service.ref_registry.get_internal_record(result.changed_refs[0], "doc_a")
    assert record is not None and record.native_token == "native-secret"


@pytest.mark.asyncio
async def test_guard_binding_observes_revision_bearing_model_snapshot(monkeypatch):
    guard = "a" * 64
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "guard": guard, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": guard, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    service.revision_tracker.observe("doc_a", "1" * 64)
    seen = []

    async def observe(request, group=None):
        seen.append((request, group))
        if request.get("operation") != "model_snapshot":
            raise AssertionError("Hands coherence must use revision-bearing model_snapshot")
        return type("R", (), {})()

    monkeypatch.setattr(service, "execute", observe)
    evidence = await service.bind_hands_provider("logical-a", "doc_a")
    assert evidence.guard == guard
    assert seen and seen[0][0]["operation"] == "model_snapshot"


@pytest.mark.asyncio
async def test_commit_waits_for_authoritative_post_readback_before_registering_refs(monkeypatch):
    guard_a = "a" * 64
    guard_b = "b" * 64
    token = "provider-native-token"
    desktop = FakeDesktop([
        {
            "api_version": PRIVATE_API_VERSION,
            "document_ref": "doc_a",
            "mode": "commit",
            "guard_before": guard_a,
            "guard_after": guard_b,
            "effects": [],
            "entities": {"created": [{"token": token, "kind": "sketch"}], "changed": []},
        },
        {"api_version": PRIVATE_API_VERSION, "guard": guard_b, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, guard_a)
    observed = []

    async def post_observe(reference_node, document_ref):
        assert reference_node == "reference-a"
        assert document_ref == "doc_a"
        # Native token must not be registered before authoritative observation.
        assert (document_ref, token) not in service.ref_registry._token_to_ref
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            sketches=[{"name": "HandsSketch", "entityToken": token}],
        )
        observed.append(True)
        return revision

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)
    result = await service.apply_hands_provider(
        "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
        operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
    )

    assert observed == [True]
    assert result.document is not None and result.document.model_revision == "rev_2"
    assert len(result.changed_refs) == 1
    assert service.get_hands_provider_guard("rich-a", "doc_a", "rev_2") == guard_b
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_committed_provider_without_authoritative_post_readback_is_uncertain_and_registers_no_refs(monkeypatch):
    guard_a = "a" * 64
    guard_b = "b" * 64
    token = "provider-native-token"
    desktop = FakeDesktop([{
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "mode": "commit", "guard_before": guard_a, "guard_after": guard_b,
        "effects": [], "entities": {"created": [{"token": token, "kind": "sketch"}], "changed": []},
    }])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, guard_a)

    async def fail_observe(_node, _document):
        raise FusionCadError(ErrorCode.FUSION_API_ERROR)
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", fail_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )
    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    assert ("doc_a", token) not in service.ref_registry._token_to_ref
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_committed_provider_requires_post_read_guard_to_match_commit_guard(monkeypatch):
    guard_a = "a" * 64
    guard_b = "b" * 64
    guard_c = "c" * 64
    token = "provider-native-token"
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "document_ref": "doc_a", "mode": "commit", "guard_before": guard_a, "guard_after": guard_b,
         "effects": [], "entities": {"created": [{"token": token, "kind": "sketch"}], "changed": []}},
        {"api_version": PRIVATE_API_VERSION, "guard": guard_c, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, guard_a)

    async def post_observe(_node, document_ref):
        return service.revision_tracker.observe(document_ref, "2" * 64)
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )
    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    assert ("doc_a", token) not in service.ref_registry._token_to_ref
    assert service.get_hands_provider_guard("rich-a", "doc_a", "rev_2") is None


@pytest.mark.asyncio
async def test_commit_ref_publication_preflights_all_output_kinds_atomically(monkeypatch):
    guard_a = "a" * 64
    guard_b = "b" * 64
    new_token = "new-provider-token"
    conflicting_token = "existing-provider-token"
    desktop = FakeDesktop([
        {
            "api_version": PRIVATE_API_VERSION,
            "document_ref": "doc_a",
            "mode": "commit", "guard_before": guard_a, "guard_after": guard_b,
            "effects": [],
            "entities": {
                "created": [
                    {"token": new_token, "kind": "sketch"},
                    {"token": conflicting_token, "kind": "sketch"},
                ],
                "changed": [],
            },
        },
        {"api_version": PRIVATE_API_VERSION, "guard": guard_b, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, guard_a)
    service.ref_registry.issue(
        document_ref="doc_a", kind="body", native_token=conflicting_token
    )

    attested = {}

    async def post_observe(_node, document_ref):
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            bodies=[{"name": "ExistingBody", "entityToken": conflicting_token}],
            sketches=[{"name": "NewSketch", "entityToken": new_token}],
        )
        issued = service.ref_registry.get_internal_record_by_native_token(document_ref, new_token)
        assert issued is not None
        attested["ref"] = issued.ref
        return revision
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )
    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    record = service.ref_registry.get_internal_record_by_native_token("doc_a", new_token)
    assert record is not None and record.ref == attested["ref"] and record.kind == "sketch"


@pytest.mark.asyncio
async def test_commit_conflicting_provider_kinds_after_commit_are_uncertain(monkeypatch):
    token = "provider-conflicting-token"
    desktop = FakeDesktop([
        {
            "api_version": PRIVATE_API_VERSION,
            "document_ref": "doc_a",
            "mode": "commit",
            "guard_before": GUARD_A,
            "guard_after": GUARD_B,
            "effects": [],
            "entities": {
                "created": [
                    {"token": token, "kind": "sketch"},
                    {"token": token, "kind": "body"},
                ],
                "changed": [],
            },
        },
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, GUARD_A)

    async def post_observe(_node, document_ref):
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            sketches=[{"name": "CurrentSketch", "entityToken": token}],
        )
        return revision

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN


@pytest.mark.asyncio
async def test_commit_accepts_sketch_evidence_after_authoritative_snapshot_normalization(monkeypatch):
    """A sketch present on Fusion's timeline must stay canonically a sketch end-to-end."""
    overlay_path = (
        Path(__file__).resolve().parents[2]
        / "ops/fusion_shimmer_overlay/addin_bridge_cad.py"
    )
    spec = importlib.util.spec_from_file_location("hands_overlay_kind_regression", overlay_path)
    assert spec is not None and spec.loader is not None
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)

    token = "shared-sketch-token"
    sketch = SimpleNamespace(entityToken=token, revisionId="sketch-rev-1")
    component = SimpleNamespace(
        entityToken="component-token",
        revisionId="component-rev-1",
        bRepBodies=[],
        sketches=[sketch],
    )
    design = SimpleNamespace(
        allComponents=[component],
        rootComponent=SimpleNamespace(allOccurrences=[]),
        timeline=[SimpleNamespace(entity=sketch)],
    )
    provider_kind = overlay._entity_inventory(
        SimpleNamespace(design=lambda: design)
    )[token]["kind"]

    desktop = FakeDesktop([
        {
            "api_version": PRIVATE_API_VERSION,
            "document_ref": "doc_a",
            "mode": "commit",
            "guard_before": GUARD_A,
            "guard_after": GUARD_B,
            "effects": [],
            "entities": {"created": [{"token": token, "kind": provider_kind}], "changed": []},
        },
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, GUARD_A)

    # Exercise the real authoritative snapshot normalizer: it canonically
    # registers this native token as kind=sketch before commit evidence arrives.
    normalize_snapshot(
        {
            "document_ref": "doc_a",
            "model_revision": old.revision,
            "components": [],
            "bodies": [],
            "sketches": [{"name": "HandsSketch", "entityToken": token}],
            "features": [],
            "parameters": [],
        },
        ref_registry=service.ref_registry,
    )

    async def post_observe(_node, document_ref):
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            sketches=[{"name": "HandsSketch", "entityToken": token}],
        )
        return revision

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)
    result = await service.apply_hands_provider(
        "logical-a",
        "doc_a",
        expected_revision=old.revision,
        mode="commit",
        operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
    )

    assert provider_kind == "sketch"
    record = service.ref_registry.get_internal_record_by_native_token("doc_a", token)
    assert record is not None and record.kind == "sketch"
    assert result.changed_refs == (record.ref,)


def _hands_matrix(capability):
    return CapabilityMatrix.from_records(
        [
            CapabilityRecord(name=capability, state="supported", implementation="test-qualified-hands"),
            CapabilityRecord(
                name="revision.external_change_detection",
                state="supported",
                implementation="authoritative-fingerprint-guard",
            ),
        ]
    )


def _enable_hands_capability(service, capability, monkeypatch):
    matrix = _hands_matrix(capability)
    monkeypatch.setattr(service, "get_node_capabilities", lambda _node_id: matrix)


def _preview_receipt(*, guard=GUARD_A, effects=(), created=(), changed=()):
    return {
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "mode": "preview",
        "guard_before": guard,
        "guard_after": guard,
        "effects": list(effects),
        "entities": {"created": list(created), "changed": list(changed)},
        "committed": False,
        "baseline_restored": True,
    }


def _commit_receipt(*, created=(), changed=()):
    return {
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "mode": "commit",
        "guard_before": GUARD_A,
        "guard_after": GUARD_B,
        "effects": [],
        "entities": {"created": list(created), "changed": list(changed)},
        "committed": True,
        "baseline_restored": False,
    }


def _typed(alias, payload):
    return TypeAdapter(alias).validate_python(payload)


@pytest.mark.asyncio
async def test_public_sketch_create_commit_routes_through_guarded_rich_provider(monkeypatch):
    desktop = FakeDesktop(
        [
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            _commit_receipt(created=[{"token": "new-sketch-token", "kind": "sketch"}]),
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
        ]
    )
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _enable_hands_capability(service, "hands.sketch", monkeypatch)
    observations = 0

    async def observe(_node, document_ref):
        nonlocal observations
        observations += 1
        if observations == 1:
            return service.revision_tracker.current(document_ref)
        revision = service.revision_tracker.observe(document_ref, "2" * 64)
        _store_hands_snapshot(
            service,
            document_ref,
            revision.fingerprint,
            sketches=[{"name": "HandsSketch", "entityToken": "new-sketch-token"}],
        )
        return revision

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "create",
            "plane": "xy",
            "name": "HandsSketch",
            "expected_revision": old.revision,
        },
    )

    result = await service.execute(request)

    assert result.document is not None
    assert result.document.model_revision == "rev_2"
    assert len(result.changed_refs) == 1 and result.changed_refs[0].startswith("ent_")
    assert [call[1] for call in desktop.calls] == [
        "_bridge_cad_guard",
        "_bridge_cad_guard",
        "_bridge_cad_apply",
        "_bridge_cad_guard",
    ]
    apply_args = desktop.calls[2][2]
    assert apply_args["mode"] == "commit"
    assert apply_args["operations"] == [
        {
            "op": "sketch.create",
            "params": {"plane": "xy", "name": "HandsSketch"},
        }
    ]


@pytest.mark.asyncio
async def test_public_sketch_batch_dry_run_compiles_symbolic_action_refs_without_advancing_revision(monkeypatch):
    desktop = FakeDesktop(
        [
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            _preview_receipt(effects=[{"op": "sketch.line"}, {"op": "sketch.line"}, {"op": "sketch.dimension"}]),
        ]
    )
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    sketch_ref = service.ref_registry.issue(
        document_ref="doc_a", kind="sketch", native_token="sketch-token"
    ).ref
    _enable_hands_capability(service, "hands.sketch", monkeypatch)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "batch",
            "sketch": sketch_ref,
            "actions": [
                {"id": "l1", "type": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0},
                {"id": "l2", "type": "line", "x1": 0, "y1": 5, "x2": 10, "y2": 5},
                {
                    "id": "gap",
                    "type": "dimension",
                    "kind": "distance",
                    "entity_one": {"source": "action", "action_id": "l1"},
                    "entity_two": {"source": "action", "action_id": "l2"},
                    "value": 5,
                },
            ],
            "expected_revision": old.revision,
            "dry_run": True,
        },
    )

    result = await service.execute(request)

    assert result.changed_refs == ()
    assert service.revision_tracker.current("doc_a").revision == old.revision
    assert result.data["mode"] == "preview"
    assert result.data["baseline_restored"] is True
    apply_args = desktop.calls[2][2]
    assert apply_args["mode"] == "preview"
    assert apply_args["operations"] == [
        {
            "op": "sketch.line",
            "action_id": "l1",
            "params": {
                "sketch": {"token": "sketch-token", "kind": "sketch"},
                "x1": 0.0,
                "y1": 0.0,
                "x2": 10.0,
                "y2": 0.0,
            },
        },
        {
            "op": "sketch.line",
            "action_id": "l2",
            "params": {
                "sketch": {"token": "sketch-token", "kind": "sketch"},
                "x1": 0.0,
                "y1": 5.0,
                "x2": 10.0,
                "y2": 5.0,
            },
        },
        {
            "op": "sketch.dimension",
            "action_id": "gap",
            "params": {
                "sketch": {"token": "sketch-token", "kind": "sketch"},
                "type": "distance",
                "entity_one": {
                    "__bridge_action_ref__": {"action_id": "l1", "element": "curve", "index": 0}
                },
                "entity_two": {
                    "__bridge_action_ref__": {"action_id": "l2", "element": "curve", "index": 0}
                },
                "value": 5.0,
            },
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("feature", "expected_operation"),
    [
        (
            {"kind": "extrude", "sketch": "SKETCH_REF", "distance_mm": 12.0, "profile_index": 0},
            {
                "op": "feature.extrude",
                "params": {
                    "sketch": {"token": "sketch-token", "kind": "sketch"},
                    "distance": 12.0,
                    "profile": 0,
                    "operation": "new",
                    "direction": "positive",
                },
            },
        ),
        (
            {"kind": "fillet", "body": "BODY_REF", "edges": ["EDGE_REF"], "radius_mm": 1.25},
            {
                "op": "feature.fillet",
                "params": {
                    "body": {"token": "body-token", "kind": "body"},
                    "edges": [{"token": "edge-token", "kind": "edge"}],
                    "radius": 1.25,
                },
            },
        ),
    ],
)
async def test_public_feature_dry_run_compiles_exact_shimmer_allowlisted_operation(monkeypatch, feature, expected_operation):
    desktop = FakeDesktop(
        [
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            _preview_receipt(),
        ]
    )
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    sketch_ref = service.ref_registry.issue(document_ref="doc_a", kind="sketch", native_token="sketch-token").ref
    body_ref = service.ref_registry.issue(document_ref="doc_a", kind="body", native_token="body-token").ref
    edge_ref = service.ref_registry.issue(document_ref="doc_a", kind="edge", native_token="edge-token").ref
    replacements = {"SKETCH_REF": sketch_ref, "BODY_REF": body_ref, "EDGE_REF": edge_ref}
    concrete = {}
    for key, value in feature.items():
        if isinstance(value, str):
            concrete[key] = replacements.get(value, value)
        elif isinstance(value, list):
            concrete[key] = [replacements.get(item, item) for item in value]
        else:
            concrete[key] = value
    _enable_hands_capability(service, "hands.feature", monkeypatch)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionFeatureRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "create",
            "feature": concrete,
            "expected_revision": old.revision,
            "dry_run": True,
        },
    )

    await service.execute(request)

    assert desktop.calls[2][2]["operations"] == [expected_operation]
    assert desktop.calls[2][2]["mode"] == "preview"


@pytest.mark.asyncio
async def test_public_hands_stale_provider_guard_is_not_replayed_and_binding_is_invalidated(monkeypatch):
    desktop = FakeDesktop(
        [
            {
                "api_version": PRIVATE_API_VERSION,
                "ok": False,
                "error": {"code": "REVISION_CONFLICT", "applied": False},
            }
        ]
    )
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)
    _enable_hands_capability(service, "hands.sketch", monkeypatch)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "create",
            "plane": "xy",
            "expected_revision": old.revision,
        },
    )

    with pytest.raises(FusionCadError) as exc_info:
        await service.execute(request)

    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert [call[1] for call in desktop.calls] == ["_bridge_cad_apply"]
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_public_hands_uncertain_apply_is_not_replayed_and_binding_is_invalidated(monkeypatch):
    desktop = FakeDesktop(
        [
            BridgeError(
                ErrorCode.DESKTOP_NODE_TIMEOUT,
                "timeout",
                retryable=False,
                details={"status": "uncertain"},
            )
        ]
    )
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)
    _enable_hands_capability(service, "hands.sketch", monkeypatch)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "create",
            "plane": "xy",
            "expected_revision": old.revision,
        },
    )

    with pytest.raises(FusionCadError) as exc_info:
        await service.execute(request)

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    assert [call[1] for call in desktop.calls] == ["_bridge_cad_apply"]
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_public_hands_rebinds_after_rich_provider_session_generation_changes(monkeypatch):
    desktop = FakeDesktop(
        [
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
            _preview_receipt(),
        ]
    )
    desktop.generations["rich-a"] = 2
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)
    _enable_hands_capability(service, "hands.sketch", monkeypatch)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "create",
            "plane": "xy",
            "expected_revision": old.revision,
            "dry_run": True,
        },
    )

    await service.execute(request)

    assert [call[1] for call in desktop.calls] == [
        "_bridge_cad_guard",
        "_bridge_cad_guard",
        "_bridge_cad_apply",
    ]
    assert service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] == ("rich-a", 2)

@pytest.mark.asyncio
async def test_hands_binding_fails_closed_when_rich_session_generation_cannot_be_read():
    class UnknownGenerationDesktop(FakeDesktop):
        def get_session_generation(self, node_id):
            raise BridgeError(ErrorCode.DESKTOP_NODE_NOT_FOUND, "generation unavailable")

    desktop = UnknownGenerationDesktop([_preview_receipt()])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a",
            "doc_a",
            expected_revision=old.revision,
            mode="preview",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.REVISION_CONFLICT
    assert desktop.calls == []
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_hands_binding_fails_closed_if_rich_session_changes_between_lookup_and_dispatch():
    class ChangingGenerationDesktop(FakeDesktop):
        def __init__(self):
            super().__init__([_preview_receipt()])
            self.reads = [1]

        def get_session_generation(self, node_id):
            return self.reads.pop(0) if self.reads else 2

        async def call(
            self, node_id, tool_name, arguments, journal=None, expected_session_generation=None
        ):
            if expected_session_generation != 2:
                raise BridgeError(
                    ErrorCode.DESKTOP_NODE_OFFLINE,
                    "session changed before dispatch",
                    retryable=True,
                    details={"status": "session_changed"},
                )
            return await super().call(
                node_id, tool_name, arguments, journal, expected_session_generation
            )

    desktop = ChangingGenerationDesktop()
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a",
            "doc_a",
            expected_revision=old.revision,
            mode="preview",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.DESKTOP_NODE_OFFLINE
    assert desktop.calls == []
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_commit_is_uncertain_if_rich_session_changes_after_apply(monkeypatch):
    class ChangingGenerationDesktop(FakeDesktop):
        def __init__(self):
            super().__init__([
                _commit_receipt(),
                {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
            ])
            self.reads = [1, 1, 2]

        def get_session_generation(self, node_id):
            return self.reads.pop(0) if self.reads else 2

    desktop = ChangingGenerationDesktop()
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)

    async def post_observe(_node, document_ref):
        return service.revision_tracker.observe(document_ref, "2" * 64)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a",
            "doc_a",
            expected_revision=old.revision,
            mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    assert service.get_hands_provider_guard("rich-a", "doc_a", old.revision) is None


@pytest.mark.asyncio
async def test_commit_does_not_publish_provider_token_missing_from_authoritative_post_snapshot(monkeypatch):
    token = "fabricated-provider-token"
    desktop = FakeDesktop([
        _commit_receipt(created=[{"token": token, "kind": "sketch"}]),
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    service._hands_provider_guards[("rich-a", "doc_a", old.revision)] = GUARD_A
    service._hands_provider_guard_sessions[("rich-a", "doc_a", old.revision)] = ("rich-a", 1)

    async def post_observe(_node, document_ref):
        # Authoritative provider advances revision but does NOT attest the rich-provider token.
        return service.revision_tracker.observe(document_ref, "2" * 64)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a",
            "doc_a",
            expected_revision=old.revision,
            mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    assert service.ref_registry.get_internal_record_by_native_token("doc_a", token) is None


@pytest.mark.asyncio
async def test_commit_rejects_stale_registry_token_absent_from_exact_post_snapshot(monkeypatch):
    token = "stale-old-sketch-token"
    desktop = FakeDesktop([
        _commit_receipt(created=[{"token": token, "kind": "sketch"}]),
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_B, "document_ref": "doc_a"},
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    _seed_hands_binding(service, old.revision, GUARD_A)

    # Historical registry state contains the token, but the exact authoritative
    # post-commit snapshot below does not. Persistent registry membership alone
    # must not attest this commit's provider evidence.
    stale = service.ref_registry.issue(
        document_ref="doc_a", kind="sketch", native_token=token
    )

    async def post_observe(_node, document_ref):
        snapshot = normalize_snapshot(
            {
                "document_ref": document_ref,
                "model_revision": "rev_2",
                "components": [],
                "bodies": [],
                "sketches": [
                    {"name": "DifferentSketch", "entityToken": "current-sketch-token"}
                ],
                "features": [],
                "parameters": [],
            },
            ref_registry=service.ref_registry,
        )
        service.snapshot_store.put(snapshot)
        return service.revision_tracker.observe(document_ref, "2" * 64)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a",
            "doc_a",
            expected_revision=old.revision,
            mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN
    # Historical identity may remain in the registry, but it must not be accepted
    # as output evidence for this commit.
    assert service.ref_registry.get_internal_record_by_native_token("doc_a", token).ref == stale.ref


@pytest.mark.asyncio
async def test_public_coincident_accepts_two_opaque_sketch_point_refs(monkeypatch):
    desktop = FakeDesktop([
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
        _preview_receipt(effects=[{"op": "sketch.constrain"}]),
    ])
    service = FusionCadService(desktop, provider_router=Router())
    old = service.revision_tracker.observe("doc_a", "1" * 64)
    sketch_ref = service.ref_registry.issue(
        document_ref="doc_a", kind="sketch", native_token="sketch-token"
    ).ref
    p1 = service.ref_registry.issue(
        document_ref="doc_a", kind="sketch_point", native_token="p1-token"
    ).ref
    p2 = service.ref_registry.issue(
        document_ref="doc_a", kind="sketch_point", native_token="p2-token"
    ).ref
    _enable_hands_capability(service, "hands.sketch", monkeypatch)

    async def observe(_node, document_ref):
        return service.revision_tracker.current(document_ref)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", observe)
    request = _typed(
        FusionSketchRequest,
        {
            "node_id": "logical-a",
            "document_ref": "doc_a",
            "operation": "batch",
            "sketch": sketch_ref,
            "actions": [
                {
                    "id": "join",
                    "type": "constraint",
                    "kind": "coincident",
                    "entity_one": {"source": "entity", "ref": p1},
                    "entity_two": {"source": "entity", "ref": p2},
                }
            ],
            "expected_revision": old.revision,
            "dry_run": True,
        },
    )

    result = await service.execute(request)

    assert result.data["mode"] == "preview"
    apply_args = desktop.calls[2][2]
    assert apply_args["operations"] == [
        {
            "op": "sketch.constrain",
            "action_id": "join",
            "params": {
                "sketch": {"token": "sketch-token", "kind": "sketch"},
                "type": "coincident",
                "entity_one": {"token": "p1-token", "kind": "sketch_point"},
                "entity_two": {"token": "p2-token", "kind": "sketch_point"},
            },
        }
    ]

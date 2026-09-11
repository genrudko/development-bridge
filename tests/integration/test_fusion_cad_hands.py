from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.providers import FusionCadProviderRoute
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


class FakeDesktop:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []

    async def call(self, node_id, tool_name, arguments, journal=None):
        self.calls.append((node_id, tool_name, arguments, journal))
        return self.replies.pop(0)


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
    assert service.get_hands_provider_guard("doc_a", "rev_1") is None


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
    service._hands_provider_guards[("doc_a", "rev_1")] = GUARD_A
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
    service._hands_provider_guards[("doc_a", "rev_1")] = GUARD_A

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
    service._hands_provider_guards[("doc_a", old.revision)] = guard_a

    async def post_observe(_node, document_ref):
        return service.revision_tracker.observe(document_ref, "2" * 64)
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
    service._hands_provider_guards[("doc_a", old.revision)] = guard_a
    observed = []

    async def post_observe(reference_node, document_ref):
        assert reference_node == "reference-a"
        assert document_ref == "doc_a"
        # Native token must not be registered before authoritative observation.
        assert (document_ref, token) not in service.ref_registry._token_to_ref
        observed.append(True)
        return service.revision_tracker.observe(document_ref, "2" * 64)

    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)
    result = await service.apply_hands_provider(
        "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
        operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
    )

    assert observed == [True]
    assert result.document is not None and result.document.model_revision == "rev_2"
    assert len(result.changed_refs) == 1
    assert service.get_hands_provider_guard("doc_a", "rev_2") == guard_b
    assert service.get_hands_provider_guard("doc_a", old.revision) is None


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
    service._hands_provider_guards[("doc_a", old.revision)] = guard_a

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
    assert service.get_hands_provider_guard("doc_a", old.revision) is None


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
    service._hands_provider_guards[("doc_a", old.revision)] = guard_a

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
    assert service.get_hands_provider_guard("doc_a", "rev_2") is None


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
    service._hands_provider_guards[("doc_a", old.revision)] = guard_a
    service.ref_registry.issue(
        document_ref="doc_a", kind="body", native_token=conflicting_token
    )

    async def post_observe(_node, document_ref):
        return service.revision_tracker.observe(document_ref, "2" * 64)
    monkeypatch.setattr(service, "_observe_authoritative_for_hands", post_observe)

    with pytest.raises(FusionCadError) as exc_info:
        await service.apply_hands_provider(
            "logical-a", "doc_a", expected_revision=old.revision, mode="commit",
            operations=[{"op": "sketch.create", "params": {"plane": "xy"}}],
        )
    assert exc_info.value.code == ErrorCode.TYPE_MISMATCH
    assert ("doc_a", new_token) not in service.ref_registry._token_to_ref


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
    service._hands_provider_guards[("doc_a", old.revision)] = GUARD_A

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
        return service.revision_tracker.observe(document_ref, "2" * 64)

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


from __future__ import annotations

import hashlib
import importlib.util
import json
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "ops" / "fusion_shimmer_overlay"
DOC_REF = "doc_unsaved_fixture"


def _load(filename: str, module_name: str):
    path = OVERLAY / filename
    if not path.exists():
        pytest.fail(f"missing overlay production module: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCollection:
    def __init__(self, items=()):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]

    def append(self, item):
        self._items.append(item)


class FakeMatrix:
    def __init__(self, values):
        self._values = tuple(values)

    def asArray(self):
        return self._values


class FakeApp:
    def __init__(self, state):
        self.state = state
        self.commands = []
        self.activeDocument = SimpleNamespace(
            name="Disposable", dataFile=None, dataId=None, savedVersion=None, creationId="fixture"
        )

    def executeTextCommand(self, command):
        self.commands.append(command)
        if command.startswith("PTransaction.Start"):
            self.state["tx_snapshot"] = self.state["value"]
            return "1"
        if command == "PTransaction.Abort":
            self.state["value"] = self.state["tx_snapshot"]
            return "1"
        if command == "PTransaction.Commit":
            return "1"
        raise AssertionError(command)


class FakeCtx:
    def __init__(self, state=None):
        self.state = state or {"value": 0}
        self.app = FakeApp(self.state)
        self._component = SimpleNamespace(
            name="Root",
            entityToken="component-token",
            revisionId="component-rev-1",
            attributes=FakeCollection(),
            bRepBodies=FakeCollection(),
            sketches=FakeCollection(),
        )
        self._occurrence = SimpleNamespace(
            name="Part:1",
            fullPathName="Part:1",
            entityToken="occ-token",
            isGrounded=False,
            isLightBulbOn=True,
            transform2=FakeMatrix(range(16)),
        )
        self._parameter = SimpleNamespace(
            name="width", expression="40 mm", value=4.0, unit="mm"
        )
        self._design = SimpleNamespace(
            rootComponent=SimpleNamespace(allOccurrences=FakeCollection([self._occurrence])),
            allComponents=FakeCollection([self._component]),
            allParameters=FakeCollection([self._parameter]),
            attributes=FakeCollection(),
            timeline=FakeCollection(),
        )

    def design(self):
        return self._design


def _mutating_registry(state):
    def rectangle(ctx, params):
        state["value"] += int(params.get("delta", 1))
        ctx._component.revisionId = f"component-rev-{state['value'] + 1}"
        return {"sketch_index": 0, "sketch_name": "Sketch1", "profiles": 1}

    def exploding(ctx, params):
        state["value"] += 1
        ctx._component.revisionId = "component-rev-exploded"
        raise RuntimeError("boom")

    return {"sketch.rectangle": rectangle, "feature.extrude": rectangle, "test.explode": exploding}


def test_provider_guard_changes_for_each_guarded_state_class():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_guard")
    base = module.compute_provider_guard(FakeCtx())["guard"]

    mutations = [
        lambda ctx: setattr(ctx._component, "revisionId", "component-rev-2"),
        lambda ctx: setattr(ctx._occurrence, "transform2", FakeMatrix([99, *range(1, 16)])),
        lambda ctx: setattr(ctx._occurrence, "isGrounded", True),
        lambda ctx: setattr(ctx._occurrence, "isLightBulbOn", False),
        lambda ctx: setattr(ctx._parameter, "expression", "41 mm"),
    ]
    for mutate in mutations:
        ctx = FakeCtx()
        before = module.compute_provider_guard(ctx)["guard"]
        mutate(ctx)
        assert module.compute_provider_guard(ctx)["guard"] != before
    assert base == module.compute_provider_guard(FakeCtx())["guard"]


def test_guard_mismatch_rejects_before_transaction_or_delegation():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_mismatch")
    ctx = FakeCtx()
    called = []
    registry = {"sketch.rectangle": lambda ctx, params: called.append(True)}

    result = module.execute_guarded(
        ctx,
        {"document_ref": DOC_REF, "expected_guard": "0" * 64, "mode": "commit", "operations": [{"op": "sketch.rectangle", "params": {}}]},
        registry,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "REVISION_CONFLICT"
    assert result["error"]["applied"] is False
    assert called == []
    assert ctx.app.commands == []


def test_disallowed_operation_rejects_before_transaction():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_allowlist")
    ctx = FakeCtx()
    guard = module.compute_provider_guard(ctx)["guard"]

    result = module.execute_guarded(
        ctx,
        {"document_ref": DOC_REF, "expected_guard": guard, "mode": "commit", "operations": [{"op": "document.save", "params": {}}]},
        {"document.save": lambda ctx, params: pytest.fail("must not delegate")},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["applied"] is False
    assert ctx.app.commands == []


def test_commit_uses_one_ptransaction_start_then_commit_and_returns_effects():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_commit")
    ctx = FakeCtx()
    guard = module.compute_provider_guard(ctx)["guard"]

    result = module.execute_guarded(
        ctx,
        {"document_ref": DOC_REF, "expected_guard": guard, "mode": "commit", "operations": [{"op": "sketch.rectangle", "params": {"delta": 2}}]},
        _mutating_registry(ctx.state),
    )

    assert result["ok"] is True
    assert result["mode"] == "commit"
    assert result["effects"][0]["op"] == "sketch.rectangle"
    assert ctx.state["value"] == 2
    assert ctx.app.commands == ['PTransaction.Start "bridge_cad_shimmer"', "PTransaction.Commit"]
    assert result["guard_after"] != guard


def test_preview_aborts_and_requires_guard_restoration():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_preview")
    ctx = FakeCtx()
    guard = module.compute_provider_guard(ctx)["guard"]
    original = ctx._component.revisionId

    # Simulate Fusion transaction rollback restoring both model value and component revision id.
    original_execute = ctx.app.executeTextCommand
    def execute(command):
        value = original_execute(command)
        if command == "PTransaction.Abort":
            ctx._component.revisionId = original
        return value
    ctx.app.executeTextCommand = execute

    result = module.execute_guarded(
        ctx,
        {"document_ref": DOC_REF, "expected_guard": guard, "mode": "preview", "operations": [{"op": "feature.extrude", "params": {}}]},
        _mutating_registry(ctx.state),
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert ctx.state["value"] == 0
    assert ctx.app.commands == ['PTransaction.Start "bridge_cad_shimmer"', "PTransaction.Abort"]
    assert result["guard_after"] == guard


def test_exception_after_start_aborts_when_abort_is_proven():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_exception")
    ctx = FakeCtx()
    guard = module.compute_provider_guard(ctx)["guard"]
    original = ctx._component.revisionId
    original_execute = ctx.app.executeTextCommand
    def execute(command):
        value = original_execute(command)
        if command == "PTransaction.Abort":
            ctx._component.revisionId = original
        return value
    ctx.app.executeTextCommand = execute

    result = module.execute_guarded(
        ctx,
        {"document_ref": DOC_REF, "expected_guard": guard, "mode": "commit", "operations": [{"op": "test.explode", "params": {}}]},
        {**_mutating_registry(ctx.state)},
        allowed_ops={"test.explode"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "FUSION_API_ERROR"
    assert result["error"]["applied"] is False
    assert ctx.state["value"] == 0
    assert ctx.app.commands == ['PTransaction.Start "bridge_cad_shimmer"', "PTransaction.Abort"]


def test_commit_returns_private_created_entity_token_evidence():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_addin_entities")
    ctx = FakeCtx()
    guard = module.compute_provider_guard(ctx)["guard"]

    def create_sketch(inner_ctx, params):
        sketch = SimpleNamespace(
            name="HandsSketch",
            entityToken="sketch-token-new",
            attributes=FakeCollection(),
        )
        inner_ctx._component.sketches.append(sketch)
        inner_ctx._component.revisionId = "component-rev-2"
        return {"sketch_name": "HandsSketch"}

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [{"op": "sketch.create", "params": {}}],
        },
        {"sketch.create": create_sketch},
    )

    assert result["ok"] is True
    assert result["entities"]["created"] == [
        {"kind": "sketch", "token": "sketch-token-new"}
    ]


def test_server_overlay_exposes_only_two_bridge_tools():
    module = _load("server_bridge_cad.py", "fusion_shimmer_overlay_server")
    registered = {}

    class FakeMcp:
        def tool(self, **kwargs):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn
            return deco

    client = SimpleNamespace(call=lambda op, params=None: {"op": op, "params": params or {}})
    module.register(FakeMcp(), client)

    assert set(registered) == {"_bridge_cad_guard", "_bridge_cad_apply"}
    assert registered["_bridge_cad_guard"](DOC_REF) == {
        "op": "bridge.cad_guard", "params": {"document_ref": DOC_REF}
    }


def test_installer_fails_closed_before_writes_on_wrong_upstream_sha(tmp_path):
    module = _load("install.py", "fusion_shimmer_overlay_install_sha")
    repo = tmp_path / "shimmer"
    repo.mkdir()
    sentinel = repo / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    with pytest.raises(module.OverlayInstallError, match="upstream"):
        module.apply_overlay(repo, expected_upstream_sha="deadbeef")

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(repo.rglob("bridge_cad.py")) == []


def test_installer_expected_sha_cannot_override_manifest_pin(tmp_path):
    module = _load("install.py", "fusion_shimmer_overlay_install_no_pin_override")
    repo = tmp_path / "shimmer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    with pytest.raises(module.OverlayInstallError, match="pinned upstream"):
        module.apply_overlay(repo, expected_upstream_sha=head)


def test_installer_fails_closed_on_registration_preimage_hash_mismatch(tmp_path):
    module = _load("install.py", "fusion_shimmer_overlay_install_hash")
    repo = tmp_path / "shimmer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    target = repo / "registration.py"
    target.write_text("unexpected preimage\n", encoding="utf-8")
    subprocess.run(["git", "add", "registration.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    manifest = {
        "upstream_sha": head,
        "targets": {
            "addin_ops_init": {
                "path": "registration.py",
                "sha256_before": hashlib.sha256(b"expected preimage\n").hexdigest(),
            }
        },
    }

    with pytest.raises(module.OverlayInstallError, match="hash"):
        module.apply_overlay(repo, manifest=manifest)

    assert target.read_text(encoding="utf-8") == "unexpected preimage\n"
    assert list(repo.rglob("bridge_cad.py")) == []


def test_installer_applies_overlay_to_verified_shimmer_layout(tmp_path):
    module = _load("install.py", "fusion_shimmer_overlay_install_happy")
    repo = tmp_path / "shimmer"
    addin_init = repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py"
    server_init = repo / "server/fusion_mcp/tools/__init__.py"
    addin_init.parent.mkdir(parents=True)
    server_init.parent.mkdir(parents=True)

    # Minimal exact registration anchors make this test hermetic; the separate
    # pinned-manifest gate proves the real upstream preimage hashes.
    addin_bytes = b"from . import (\n    api,\n    assembly,\n)\n"
    server_bytes = (
        b"from fusion_mcp.tools import (\n        api,\n        assembly,\n)\n\n"
        b"def register_all(mcp, client):\n"
        b"    # Read-only generic-API helpers (introspect/docs) are always available.\n"
        b"    api.register(mcp, client)\n"
    )
    addin_init.write_bytes(addin_bytes)
    server_init.write_bytes(server_bytes)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    manifest = {
        "upstream_sha": head,
        "targets": {
            "addin_ops_init": {
                "path": "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py",
                "sha256_before": hashlib.sha256(addin_bytes).hexdigest(),
            },
            "server_tools_init": {
                "path": "server/fusion_mcp/tools/__init__.py",
                "sha256_before": hashlib.sha256(server_bytes).hexdigest(),
            },
        },
    }

    result = module.apply_overlay(repo, manifest=manifest)

    assert result["status"] == "installed"
    assert (repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/bridge_cad.py").read_bytes() == (OVERLAY / "addin_bridge_cad.py").read_bytes()
    assert (repo / "server/fusion_mcp/tools/bridge_cad.py").read_bytes() == (OVERLAY / "server_bridge_cad.py").read_bytes()
    assert "bridge_cad," in addin_init.read_text(encoding="utf-8")
    server_text = server_init.read_text(encoding="utf-8")
    assert "bridge_cad," in server_text
    assert "bridge_cad.register(mcp, client)" in server_text


def test_installer_rolls_back_all_targets_if_a_late_write_fails(tmp_path, monkeypatch):
    module = _load("install.py", "fusion_shimmer_overlay_install_rollback")
    repo = tmp_path / "shimmer"
    addin_init = repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py"
    server_init = repo / "server/fusion_mcp/tools/__init__.py"
    addin_init.parent.mkdir(parents=True)
    server_init.parent.mkdir(parents=True)
    addin_bytes = b"from . import (\n    api,\n    assembly,\n)\n"
    server_bytes = (
        b"from fusion_mcp.tools import (\n        api,\n        assembly,\n)\n\n"
        b"def register_all(mcp, client):\n"
        b"    # Read-only generic-API helpers (introspect/docs) are always available.\n"
        b"    api.register(mcp, client)\n"
    )
    addin_init.write_bytes(addin_bytes)
    server_init.write_bytes(server_bytes)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    manifest = {
        "upstream_sha": head,
        "targets": {
            "addin_ops_init": {
                "path": "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py",
                "sha256_before": hashlib.sha256(addin_bytes).hexdigest(),
            },
            "server_tools_init": {
                "path": "server/fusion_mcp/tools/__init__.py",
                "sha256_before": hashlib.sha256(server_bytes).hexdigest(),
            },
        },
    }
    fail_path = repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/bridge_cad.py"
    original_write = Path.write_bytes
    failed = False

    def flaky_write(self, data):
        nonlocal failed
        if self == fail_path and not failed:
            failed = True
            raise OSError("injected late write failure")
        return original_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write)
    with pytest.raises(module.OverlayInstallError, match="write"):
        module.apply_overlay(repo, manifest=manifest)

    assert addin_init.read_bytes() == addin_bytes
    assert server_init.read_bytes() == server_bytes
    assert not (repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/bridge_cad.py").exists()
    assert not (repo / "server/fusion_mcp/tools/bridge_cad.py").exists()


def test_manifest_pins_exact_upstream_and_registration_preimages():
    manifest_path = OVERLAY / "manifest.json"
    if not manifest_path.exists():
        pytest.fail("missing overlay manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["upstream_sha"] == "97a06e76c289420a721590ddcab334f5f3dc3178"
    assert manifest["targets"]["addin_ops_init"]["sha256_before"] == "7373d22eb6e4f212f88df8972bf55a71aa33b25b38b12beb0fd6b8009ee82510"
    assert manifest["targets"]["server_tools_init"]["sha256_before"] == "b33e6fac165b98d304014fa60a3c55c7b7d6177d9c52f80ff6f32a557a06fc60"



def test_provider_guard_reports_p0_normalized_document_ref():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_doc_identity")
    ctx = FakeCtx()
    ctx.app.activeDocument = SimpleNamespace(
        name="Disposable", dataFile=SimpleNamespace(id="urn:adsk.wipprod:dm.lineage:abc-123")
    )
    evidence = module.compute_provider_guard(ctx)
    assert evidence["document_ref"] == "doc_urn_adsk.wipprod_dm.lineage_abc-123"


def test_guard_and_apply_reject_wrong_document_before_transaction_or_delegation():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_wrong_doc")
    ctx = FakeCtx()
    ctx.app.activeDocument = SimpleNamespace(
        name="Disposable", dataFile=SimpleNamespace(id="actual-doc")
    )
    active = module.compute_provider_guard(ctx)

    guard_result = module.guard_for_document(ctx, {"document_ref": "doc_other-doc"})
    assert guard_result["ok"] is False
    assert guard_result["error"]["code"] == "WRONG_DOCUMENT"

    apply_result = module.execute_guarded(
        ctx,
        {
            "document_ref": "doc_other-doc",
            "expected_guard": active["guard"],
            "mode": "commit",
            "operations": [{"op": "sketch.rectangle", "params": {"delta": 1}}],
        },
        _mutating_registry(ctx.state),
    )
    assert apply_result["ok"] is False
    assert apply_result["error"]["code"] == "WRONG_DOCUMENT"
    assert ctx.app.commands == []
    assert ctx.state["value"] == 0


def test_server_overlay_private_tools_require_and_forward_document_ref():
    module = _load("server_bridge_cad.py", "fusion_shimmer_overlay_server_doc")
    registered = {}
    calls = []

    class FakeMcp:
        def tool(self, **kwargs):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn
            return deco

    client = SimpleNamespace(call=lambda op, params=None: calls.append((op, params)) or {"ok": True})
    module.register(FakeMcp(), client)

    guard_sig = inspect.signature(registered["_bridge_cad_guard"])
    apply_sig = inspect.signature(registered["_bridge_cad_apply"])
    assert tuple(guard_sig.parameters) == ("document_ref",)
    assert tuple(apply_sig.parameters) == ("document_ref", "expected_guard", "mode", "operations")

    registered["_bridge_cad_guard"]("doc_a")
    registered["_bridge_cad_apply"]("doc_a", "a" * 64, "preview", [{"op": "sketch.create", "params": {}}])
    assert calls == [
        ("bridge.cad_guard", {"document_ref": "doc_a"}),
        ("bridge.cad_apply", {
            "document_ref": "doc_a", "expected_guard": "a" * 64,
            "mode": "preview", "operations": [{"op": "sketch.create", "params": {}}],
        }),
    ]


def test_entity_inventory_preserves_sketch_kind_when_same_entity_is_on_timeline():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_sketch_kind")
    ctx = FakeCtx()
    sketch = SimpleNamespace(
        name="HandsSketch",
        entityToken="shared-sketch-token",
        revisionId="sketch-rev-1",
        attributes=FakeCollection(),
    )
    ctx._component.sketches.append(sketch)
    ctx._design.timeline = FakeCollection([SimpleNamespace(entity=sketch)])

    inventory = module._entity_inventory(ctx)

    assert inventory["shared-sketch-token"]["kind"] == "sketch"


def _hands_token_ctx():
    ctx = FakeCtx()
    sketch_points = FakeCollection()
    sketch_curves = FakeCollection()
    sketch = SimpleNamespace(
        name="HandsSketch",
        objectType="adsk::fusion::Sketch",
        entityToken="sketch-token",
        revisionId="sketch-rev-1",
        attributes=FakeCollection(),
        sketchCurves=sketch_curves,
        sketchPoints=sketch_points,
    )
    body = SimpleNamespace(
        name="HandsBody",
        objectType="adsk::fusion::BRepBody",
        entityToken="body-token",
        attributes=FakeCollection(),
        faces=FakeCollection(),
        edges=FakeCollection(),
    )
    face = SimpleNamespace(
        objectType="adsk::fusion::BRepFace",
        entityToken="face-token",
        body=body,
    )
    edge = SimpleNamespace(
        objectType="adsk::fusion::BRepEdge",
        entityToken="edge-token",
        body=body,
    )
    body.faces.append(face)
    body.edges.append(edge)
    ctx._component.bRepBodies.append(body)
    ctx._component.sketches.append(sketch)
    ctx._design.rootComponent = SimpleNamespace(allOccurrences=FakeCollection([ctx._occurrence]))
    by_token = {
        "sketch-token": sketch,
        "body-token": body,
        "face-token": face,
        "edge-token": edge,
    }
    ctx._design.findEntityByToken = lambda token: by_token.get(token)
    ctx.target = lambda: ctx._component
    ctx.get_sketch = lambda ref: ctx._component.sketches.item(ref) if isinstance(ref, int) else None
    return ctx, sketch, body, face, edge, by_token


def _entity_marker(token, kind):
    return {"token": token, "kind": kind}


def _action_marker(action_id, element="curve", index=0):
    return {"__bridge_action_ref__": {"action_id": action_id, "element": element, "index": index}}


def test_guarded_delegate_resolves_body_and_edge_tokens_to_shimmer_indices():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_private_body_edge")
    ctx, _sketch, _body, _face, _edge, _by_token = _hands_token_ctx()
    guard = module.compute_provider_guard(ctx)["guard"]
    seen = []

    def fillet(_ctx, params):
        seen.append(dict(params))
        ctx._component.revisionId = "component-rev-2"
        return {"feature": "fillet"}

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [{
                "op": "feature.fillet",
                "params": {
                    "body": _entity_marker("body-token", "body"),
                    "edges": [_entity_marker("edge-token", "edge")],
                    "radius": 1.0,
                },
            }],
        },
        {"feature.fillet": fillet},
        allowed_ops={"feature.fillet"},
    )

    assert result["ok"] is True
    assert seen == [{"body": 0, "edges": [0], "radius": 1.0}]


def test_guarded_delegate_resolves_face_token_to_shimmer_plane_body_face_indices():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_private_face_plane")
    ctx, _sketch, _body, _face, _edge, _by_token = _hands_token_ctx()
    guard = module.compute_provider_guard(ctx)["guard"]
    seen = []

    def create(_ctx, params):
        seen.append(dict(params))
        ctx._component.revisionId = "component-rev-2"
        return {"sketch_index": 1}

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [{
                "op": "sketch.create",
                "params": {"plane": _entity_marker("face-token", "face"), "name": "OnFace"},
            }],
        },
        {"sketch.create": create},
        allowed_ops={"sketch.create"},
    )

    assert result["ok"] is True
    assert seen == [{"plane": {"body": 0, "face": 0}, "name": "OnFace"}]


@pytest.mark.parametrize(
    ("resolved", "declared_kind", "expected_code"),
    [
        (None, "body", "REF_STALE"),
        ([SimpleNamespace(objectType="adsk::fusion::BRepBody"), SimpleNamespace(objectType="adsk::fusion::BRepBody")], "body", "REF_SPLIT"),
        ("body", "sketch", "TYPE_MISMATCH"),
    ],
)
def test_private_token_resolution_fails_closed_before_transaction(resolved, declared_kind, expected_code):
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_private_token_errors_" + expected_code)
    ctx, _sketch, body, _face, _edge, by_token = _hands_token_ctx()
    if resolved == "body":
        resolved = body
    ctx._design.findEntityByToken = lambda token: resolved
    guard = module.compute_provider_guard(ctx)["guard"]
    called = []

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [{
                "op": "feature.fillet",
                "params": {"body": _entity_marker("body-token", declared_kind), "edges": "all", "radius": 1.0},
            }],
        },
        {"feature.fillet": lambda _ctx, _params: called.append(True)},
        allowed_ops={"feature.fillet"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == expected_code
    assert result["error"]["applied"] is False
    assert called == []
    assert ctx.app.commands == []


def test_symbolic_action_refs_resolve_to_curves_created_earlier_in_same_transaction():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_symbolic_refs")
    ctx, sketch, _body, _face, _edge, _by_token = _hands_token_ctx()
    guard = module.compute_provider_guard(ctx)["guard"]
    seen_dimensions = []

    def line(_ctx, params):
        idx = sketch.sketchCurves.count
        start = SimpleNamespace(objectType="adsk::fusion::SketchPoint", entityToken=f"p{idx}s")
        end = SimpleNamespace(objectType="adsk::fusion::SketchPoint", entityToken=f"p{idx}e")
        sketch.sketchPoints.append(start)
        sketch.sketchPoints.append(end)
        curve = SimpleNamespace(
            objectType="adsk::fusion::SketchLine",
            entityToken=f"curve-{idx}",
            startSketchPoint=start,
            endSketchPoint=end,
        )
        sketch.sketchCurves.append(curve)
        ctx._component.revisionId = f"component-rev-{idx + 2}"
        return {"sketch_index": 0}

    def dimension(_ctx, params):
        seen_dimensions.append(dict(params))
        return {"dimension": params["type"]}

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [
                {"op": "sketch.line", "action_id": "l1", "params": {"sketch": _entity_marker("sketch-token", "sketch"), "x1": 0, "y1": 0, "x2": 10, "y2": 0}},
                {"op": "sketch.line", "action_id": "l2", "params": {"sketch": _entity_marker("sketch-token", "sketch"), "x1": 0, "y1": 5, "x2": 10, "y2": 5}},
                {"op": "sketch.dimension", "params": {"sketch": _entity_marker("sketch-token", "sketch"), "type": "distance", "entity_one": _action_marker("l1"), "entity_two": _action_marker("l2"), "value": 5.0}},
            ],
        },
        {"sketch.line": line, "sketch.dimension": dimension},
        allowed_ops={"sketch.line", "sketch.dimension"},
    )

    assert result["ok"] is True
    assert seen_dimensions == [{"sketch": 0, "type": "distance", "entity_one": 0, "entity_two": 1, "value": 5.0}]


def test_symbolic_coincident_resolves_end_and_start_as_two_sketch_points():
    module = _load("addin_bridge_cad.py", "fusion_shimmer_overlay_symbolic_coincident_points")
    ctx, sketch, _body, _face, _edge, _by_token = _hands_token_ctx()
    guard = module.compute_provider_guard(ctx)["guard"]
    seen_constraints = []

    def line(_ctx, params):
        idx = sketch.sketchCurves.count
        start = SimpleNamespace(
            objectType="adsk::fusion::SketchPoint", entityToken=f"p{idx}s"
        )
        end = SimpleNamespace(
            objectType="adsk::fusion::SketchPoint", entityToken=f"p{idx}e"
        )
        sketch.sketchPoints.append(start)
        sketch.sketchPoints.append(end)
        curve = SimpleNamespace(
            objectType="adsk::fusion::SketchLine",
            entityToken=f"curve-{idx}",
            startSketchPoint=start,
            endSketchPoint=end,
        )
        sketch.sketchCurves.append(curve)
        ctx._component.revisionId = f"component-rev-{idx + 2}"
        return {"sketch_index": 0}

    def constrain(_ctx, params):
        seen_constraints.append(dict(params))
        return {"constraint": params["type"]}

    result = module.execute_guarded(
        ctx,
        {
            "document_ref": DOC_REF,
            "expected_guard": guard,
            "mode": "commit",
            "operations": [
                {
                    "op": "sketch.line",
                    "action_id": "l1",
                    "params": {
                        "sketch": _entity_marker("sketch-token", "sketch"),
                        "x1": 0, "y1": 0, "x2": 10, "y2": 0,
                    },
                },
                {
                    "op": "sketch.line",
                    "action_id": "l2",
                    "params": {
                        "sketch": _entity_marker("sketch-token", "sketch"),
                        "x1": 10, "y1": 5, "x2": 20, "y2": 5,
                    },
                },
                {
                    "op": "sketch.constrain",
                    "params": {
                        "sketch": _entity_marker("sketch-token", "sketch"),
                        "type": "coincident",
                        "entity_one": _action_marker("l1", "end"),
                        "entity_two": _action_marker("l2", "start"),
                    },
                },
            ],
        },
        {"sketch.line": line, "sketch.constrain": constrain},
        allowed_ops={"sketch.line", "sketch.constrain"},
    )

    assert result["ok"] is True
    assert seen_constraints == [
        {
            "sketch": 0,
            "type": "coincident",
            "entity_one": 1,
            "entity_two": 2,
        }
    ]

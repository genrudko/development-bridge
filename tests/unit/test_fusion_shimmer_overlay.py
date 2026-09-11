from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "ops" / "fusion_shimmer_overlay"


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
        self.activeDocument = SimpleNamespace(name="Disposable", dataFile=None)

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
        {"expected_guard": "0" * 64, "mode": "commit", "operations": [{"op": "sketch.rectangle", "params": {}}]},
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
        {"expected_guard": guard, "mode": "commit", "operations": [{"op": "document.save", "params": {}}]},
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
        {"expected_guard": guard, "mode": "commit", "operations": [{"op": "sketch.rectangle", "params": {"delta": 2}}]},
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
        {"expected_guard": guard, "mode": "preview", "operations": [{"op": "feature.extrude", "params": {}}]},
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
        {"expected_guard": guard, "mode": "commit", "operations": [{"op": "test.explode", "params": {}}]},
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
    assert registered["_bridge_cad_guard"]() == {"op": "bridge.cad_guard", "params": {}}


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

    source_repo = Path("/tmp/fusion-reuse-audit2/shimmer")
    addin_bytes = (source_repo / "addin/Fusion360MCP/fusion_mcp_addin/ops/__init__.py").read_bytes()
    server_bytes = (source_repo / "server/fusion_mcp/tools/__init__.py").read_bytes()
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


def test_manifest_pins_exact_upstream_and_registration_preimages():
    manifest_path = OVERLAY / "manifest.json"
    if not manifest_path.exists():
        pytest.fail("missing overlay manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["upstream_sha"] == "97a06e76c289420a721590ddcab334f5f3dc3178"
    assert manifest["targets"]["addin_ops_init"]["sha256_before"] == "7373d22eb6e4f212f88df8972bf55a71aa33b25b38b12beb0fd6b8009ee82510"
    assert manifest["targets"]["server_tools_init"]["sha256_before"] == "b33e6fac165b98d304014fa60a3c55c7b7d6177d9c52f80ff6f32a557a06fc60"

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager
from typing import Any

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.models import ImmutableMapping
from app.fusion_cad.requests import ModelSnapshotRequest
from app.fusion_cad.scripts import FusionCadScriptBundle


def test_bundle_embeds_utf8_payload_as_json_not_python_source():
    bundle = FusionCadScriptBundle()
    script = bundle.build("read", {"operation": "echo", "text": "ПЫТОК 😈"})
    compile(script, "<fusion-cad>", "exec")
    assert "ПЫТОК 😈" in script
    assert "fusion.cad/v1" in script


def test_bundle_rejects_raw_string_and_non_serializable():
    bundle = FusionCadScriptBundle()
    with pytest.raises(BridgeError) as exc:
        bundle.build("read", "import os; os.system('rm -rf /')")  # type: ignore[arg-type]
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(BridgeError) as exc:
        bundle.build("read", {"bad": object()})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_bundle_rejects_invalid_group():
    bundle = FusionCadScriptBundle()
    with pytest.raises(BridgeError) as exc:
        bundle.build("../../secret", {"operation": "test"})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT

    with pytest.raises(BridgeError) as exc:
        bundle.build("invalid-group!", {"operation": "test"})
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


def test_bundle_accepts_pydantic_model():
    bundle = FusionCadScriptBundle()
    req = ModelSnapshotRequest(node_id="desk-1", operation="model_snapshot")
    script = bundle.build("read", req)
    compile(script, "<fusion-cad>", "exec")
    assert "model_snapshot" in script
    assert "desk-1" in script


def test_bundle_accepts_immutable_mapping():
    bundle = FusionCadScriptBundle()
    mapping = ImmutableMapping({"operation": "echo", "nested": {"key": "val"}})
    script = bundle.build("read", mapping)
    compile(script, "<fusion-cad>", "exec")
    assert "nested" in script


def test_bundle_classmethod_call():
    script = FusionCadScriptBundle.build(
        "read",
        {"operation": "echo", "text": "classmethod test"},
    )
    compile(script, "<fusion-cad>", "exec")
    assert "classmethod test" in script


def test_bundle_requires_existing_group_fragment_and_fails_closed():
    bundle = FusionCadScriptBundle()
    with pytest.raises(BridgeError) as exc:
        bundle.build("nonexistent_group_xyz", {"operation": "test"})
    assert exc.value.code in (ErrorCode.INVALID_ARGUMENT, ErrorCode.INTERNAL_ERROR)


def test_bundle_group_fragment_defines_run_before_execution(tmp_path):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        "import json\n"
        'API_VERSION = "fusion.cad/v1"\n'
        "PAYLOAD_RAW = __PAYLOAD_JSON__\n"
        "PAYLOAD = json.loads(PAYLOAD_RAW) if isinstance(PAYLOAD_RAW, str) else PAYLOAD_RAW\n"
        "# __GROUP_SCRIPT__\n"
        'if __name__ == "__main__" or True:\n'
        "    _output = run()\n",
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text(
        "def run():\n"
        '    return {"group_run_executed": True, "op": PAYLOAD.get("operation")}\n',
        encoding="utf-8",
    )
    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    rendered = bundle.build("custom", {"operation": "custom_op"})
    compile(rendered, "<fusion-cad>", "exec")
    scope: dict = {}
    exec(rendered, scope)  # noqa: S102
    assert scope.get("_output") == {"group_run_executed": True, "op": "custom_op"}


def test_bundle_fails_on_missing_group_script_marker(tmp_path):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        "import json\n"
        'API_VERSION = "fusion.cad/v1"\n'
        "PAYLOAD_RAW = __PAYLOAD_JSON__\n"
        'if __name__ == "__main__":\n'
        "    _output = run()\n",
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert "missing required '# __GROUP_SCRIPT__' marker" in exc.value.message


def test_bundle_fails_on_duplicate_group_script_marker(tmp_path):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        "import json\n"
        'API_VERSION = "fusion.cad/v1"\n'
        "PAYLOAD_RAW = __PAYLOAD_JSON__\n"
        "# __GROUP_SCRIPT__\n"
        "# __GROUP_SCRIPT__\n"
        'if __name__ == "__main__":\n'
        "    _output = run()\n",
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert "duplicate '# __GROUP_SCRIPT__' markers" in exc.value.message


def test_bundle_fails_on_missing_payload_json_marker(tmp_path):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        "import json\n"
        'API_VERSION = "fusion.cad/v1"\n'
        "# __GROUP_SCRIPT__\n"
        'if __name__ == "__main__":\n'
        "    _output = run()\n",
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert "missing '__PAYLOAD_JSON__' marker" in exc.value.message


def test_bundle_fails_on_duplicate_payload_json_marker(tmp_path):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        "import json\n"
        'API_VERSION = "fusion.cad/v1"\n'
        "PAYLOAD_RAW = __PAYLOAD_JSON__\n"
        "PAYLOAD_COPY = __PAYLOAD_JSON__\n"
        "# __GROUP_SCRIPT__\n"
        'if __name__ == "__main__":\n'
        "    _output = run()\n",
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert "duplicate '__PAYLOAD_JSON__' markers" in exc.value.message


@pytest.mark.parametrize(
    "group", ["read", "inspect", "view", "mutate", "validate", "transaction"]
)
def test_all_builtin_script_groups_compile_and_execute(group: str):
    bundle = FusionCadScriptBundle()
    script = bundle.build(group, {"operation": "test_op"})
    compiled = compile(script, f"<fusion-cad-{group}>", "exec")
    assert compiled is not None

    scope: dict = {}
    exec(compiled, scope)  # noqa: S102
    assert "_output" in scope
    assert scope["_output"]["api_version"] == "fusion.cad/v1"
    assert scope["_output"]["status"] == "succeeded"
    assert scope["_output"]["summary"] == f"Executed {group}:test_op"


@pytest.mark.parametrize(
    "extended_payload_line",
    [
        "PAYLOAD_RAW = __PAYLOAD_JSON__EXTRA",
        "PAYLOAD_RAW = PREFIX___PAYLOAD_JSON__",
        "PAYLOAD_RAW = __PAYLOAD_JSON_V2__",
        "PAYLOAD_RAW = MY__PAYLOAD_JSON__",
    ],
)
def test_bundle_rejects_extended_superset_payload_marker(
    tmp_path, extended_payload_line: str
):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        f'import json\nAPI_VERSION = "fusion.cad/v1"\n{extended_payload_line}\n# __GROUP_SCRIPT__\nif __name__ == "__main__":\n    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert (
        "invalid or extended payload markers" in exc.value.message
        or "missing '__PAYLOAD_JSON__' marker" in exc.value.message
    )


@pytest.mark.parametrize(
    "extended_group_line",
    [
        "# __GROUP_SCRIPT___V2",
        "# __GROUP_SCRIPT__ extra_tokens",
        "x = 1 # __GROUP_SCRIPT__",
        "# __GROUP_SCRIPTS__",
        "def foo(): # __GROUP_SCRIPT__",
    ],
)
def test_bundle_rejects_extended_superset_group_marker(
    tmp_path, extended_group_line: str
):
    custom_scripts = tmp_path / "fusion_scripts"
    custom_scripts.mkdir()
    common_path = custom_scripts / "common.py.txt"
    common_path.write_text(
        f'import json\nAPI_VERSION = "fusion.cad/v1"\nPAYLOAD_RAW = __PAYLOAD_JSON__\n{extended_group_line}\nif __name__ == "__main__":\n    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text("def run(): return {}\n", encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert (
        "invalid or extended group marker line" in exc.value.message
        or "missing required '# __GROUP_SCRIPT__' marker" in exc.value.message
    )


def test_bundle_builds_and_compiles_read_entity_script() -> None:
    bundle = FusionCadScriptBundle()
    script = bundle.build(
        "read",
        {
            "operation": "entity",
            "ref": "ent_test_123",
            "native_token": "tok_native_abc",
            "document_ref": "doc_active_doc",
        },
    )
    compiled = compile(script, "<fusion-cad-read-entity>", "exec")
    assert "resolve_fusion_entity" in script
    assert "ent_test_123" in script

    # Execution without active design fails closed with NO_ACTIVE_DESIGN
    scope: dict = {}
    exec(compiled, scope)  # noqa: S102
    assert "_output" in scope
    out = scope["_output"]
    assert out["status"] == "failed"
    assert out["error"]["code"] == "NO_ACTIVE_DESIGN"


class _FakeCollection:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    @property
    def count(self) -> int:
        return len(self._items)

    def item(self, idx: int) -> Any:
        return self._items[idx]


class _FakeEntity:
    def __init__(
        self,
        name: str,
        entity_token: str,
        object_type: str = "adsk::fusion::BRepBody",
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.entityToken = entity_token
        self.objectType = object_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeOccurrence:
    def __init__(self, name: str, component: Any) -> None:
        self.name = name
        self.component = component


class _FakeComponent:
    def __init__(
        self,
        name: str,
        bodies: list[Any] | None = None,
        occurrences: list[Any] | None = None,
        sketches: list[Any] | None = None,
    ) -> None:
        self.name = name
        self.bRepBodies = _FakeCollection(bodies or [])
        self.occurrences = _FakeCollection(occurrences or [])
        self.sketches = _FakeCollection(sketches or [])


@contextmanager
def _mock_adsk_env(
    doc_id: str = "test_doc",
    find_token_fn: Any = None,
    root_component: Any = None,
):
    adsk = types.ModuleType("adsk")
    adsk_core = types.ModuleType("adsk.core")
    adsk_fusion = types.ModuleType("adsk.fusion")

    class FakeDesign:
        def __init__(self) -> None:
            self.rootComponent = root_component

        def findEntityByToken(self, token: str) -> Any:
            if find_token_fn:
                return find_token_fn(token)
            return None

    fake_design = FakeDesign()

    class FakeDoc:
        def __init__(self) -> None:
            self.creationId = doc_id
            self.products = self

        def itemByClass(self, cls_name: str) -> Any:
            if cls_name == "adsk::fusion::Design":
                return fake_design
            return None

    fake_doc = FakeDoc()

    class FakeApp:
        def __init__(self) -> None:
            self.activeDocument = fake_doc

        @classmethod
        def get(cls) -> Any:
            return cls._instance

    FakeApp._instance = FakeApp()
    adsk_core.Application = FakeApp
    adsk.core = adsk_core
    adsk.fusion = adsk_fusion

    saved = {
        "adsk": sys.modules.get("adsk"),
        "adsk.core": sys.modules.get("adsk.core"),
        "adsk.fusion": sys.modules.get("adsk.fusion"),
    }
    sys.modules["adsk"] = adsk
    sys.modules["adsk.core"] = adsk_core
    sys.modules["adsk.fusion"] = adsk_fusion

    try:
        yield fake_design
    finally:
        for mod, val in saved.items():
            if val is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = val


def test_resolve_fusion_entity_candidates_never_leak_native_tokens() -> None:
    secret_token = "SECRET_NATIVE_TOKEN_XYZ_123"
    fake_body = _FakeEntity("Bracket", secret_token, "adsk::fusion::BRepBody")
    root = _FakeComponent("Root", bodies=[fake_body])

    def find_tok(tok: str) -> Any:
        if tok == secret_token:
            return fake_body
        return None

    with _mock_adsk_env(doc_id="doc1", find_token_fn=find_tok, root_component=root):
        bundle = FusionCadScriptBundle()
        script = bundle.build(
            "read",
            {
                "operation": "entity",
                "ref": "ent_test_1",
                "native_token": secret_token,
                "document_ref": "doc_doc1",
            },
        )
        scope: dict = {}
        exec(compile(script, "<test-leak>", "exec"), scope)  # noqa: S102

        # 1. Exact match via findEntityByToken
        res_exact = scope["resolve_fusion_entity"](
            {
                "ref": "ent_test_1",
                "native_token": secret_token,
                "document_ref": "doc_doc1",
            }
        )
        assert res_exact["outcome"] == "exact"
        assert len(res_exact["candidates"]) == 1
        cand = res_exact["candidates"][0]
        assert "native_token" not in cand
        assert "entityToken" not in cand
        assert secret_token not in json.dumps(res_exact["candidates"])

        # 2. Contextual match without native token
        # 2a. Root/name-only without component_path and geometry_signature MUST NOT produce exact
        res_name_only = scope["resolve_fusion_entity"](
            {
                "ref": "ent_test_3",
                "kind": "body",
                "name": "Bracket",
                "document_ref": "doc_doc1",
            }
        )
        assert res_name_only["outcome"] == "ambiguous"
        assert len(res_name_only["candidates"]) == 1
        assert "native_token" not in res_name_only["candidates"][0]
        assert "entityToken" not in res_name_only["candidates"][0]
        assert secret_token not in json.dumps(res_name_only["candidates"])

        # 2b. Complete contextual match with complete component_path and geometry_signature -> exact
        fake_body.volume = 100.0
        res_ctx = scope["resolve_fusion_entity"](
            {
                "ref": "ent_test_3",
                "kind": "body",
                "name": "Bracket",
                "component_path": ("Root",),
                "geometry_signature": {"volume": 100.0},
                "document_ref": "doc_doc1",
            }
        )
        assert res_ctx["outcome"] == "exact"
        assert len(res_ctx["candidates"]) == 1
        assert "native_token" not in res_ctx["candidates"][0]
        assert "entityToken" not in res_ctx["candidates"][0]
        assert secret_token not in json.dumps(res_ctx["candidates"])

        # 3. read:entity script execution summary must not leak native token
        out = scope["run"]()
        assert out["status"] == "succeeded"
        assert secret_token not in out["summary"]
        assert secret_token not in json.dumps(out["data"]["candidates"])

    # 4. Split match via token
    secret_tok_a = "SECRET_SPLIT_TOKEN_A"
    secret_tok_b = "SECRET_SPLIT_TOKEN_B"
    split_cand_a = _FakeEntity("SplitA", secret_tok_a)
    split_cand_b = _FakeEntity("SplitB", secret_tok_b)
    split_coll = _FakeCollection([split_cand_a, split_cand_b])

    with _mock_adsk_env(
        doc_id="doc1", find_token_fn=lambda t: split_coll, root_component=root
    ):
        res_split = scope["resolve_fusion_entity"](
            {
                "ref": "ent_test_2",
                "native_token": "tok_split",
                "document_ref": "doc_doc1",
            }
        )
        assert res_split["outcome"] == "split"
        assert len(res_split["candidates"]) == 2
        for c in res_split["candidates"]:
            assert "native_token" not in c
            assert "entityToken" not in c
        assert secret_tok_a not in json.dumps(res_split["candidates"])
        assert secret_tok_b not in json.dumps(res_split["candidates"])


def test_contextual_resolver_fails_closed_on_missing_or_partial_component_path() -> (
    None
):
    child_body = _FakeEntity("ChildBody", "tok_child")
    child_body.volume = 50.0
    sub_comp = _FakeComponent("SubComp", bodies=[child_body])
    occ_sub1 = _FakeOccurrence("Sub1", sub_comp)
    root = _FakeComponent("Root", occurrences=[occ_sub1])

    with _mock_adsk_env(doc_id="doc1", root_component=root):
        bundle = FusionCadScriptBundle()
        script = bundle.build("read", {"operation": "echo"})
        scope: dict = {}
        exec(compile(script, "<test-path>", "exec"), scope)  # noqa: S102

        # Complete matching path with usable geometry signature: ("Root", "Sub1") -> exact
        res_ok = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "ChildBody",
                "component_path": ("Root", "Sub1"),
                "geometry_signature": {"volume": 50.0},
                "document_ref": "doc_doc1",
            }
        )
        assert res_ok["outcome"] == "exact"
        assert len(res_ok["candidates"]) == 1

        # Complete matching path WITHOUT geometry signature -> fails closed to ambiguous, NEVER exact!
        res_no_sig = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "ChildBody",
                "component_path": ("Root", "Sub1"),
                "document_ref": "doc_doc1",
            }
        )
        assert res_no_sig["outcome"] == "ambiguous"
        assert len(res_no_sig["candidates"]) == 1

        # Missing / partial path segment: Sub2 does not exist under Sub1
        # Must FAIL CLOSED (outcome='stale', candidates=[]), never continue from Sub1!
        res_fail = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "ChildBody",
                "component_path": ("Root", "Sub1", "MissingSub2"),
                "geometry_signature": {"volume": 50.0},
                "document_ref": "doc_doc1",
            }
        )
        assert res_fail["outcome"] == "stale"
        assert res_fail["candidates"] == []

        # Unknown root occurrence segment: NonExistent
        res_fail_root = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "ChildBody",
                "component_path": ("Root", "NonExistent"),
                "geometry_signature": {"volume": 50.0},
                "document_ref": "doc_doc1",
            }
        )
        assert res_fail_root["outcome"] == "stale"
        assert res_fail_root["candidates"] == []


def test_contextual_resolver_geometry_signature_participates_in_matching() -> None:
    b1 = _FakeEntity("Bracket", "tok_b1", volume=100.0, is_solid=True)
    b1.faces = _FakeCollection([object()] * 6)
    b2 = _FakeEntity("Bracket", "tok_b2", volume=200.0, is_solid=True)
    b2.faces = _FakeCollection([object()] * 8)
    root = _FakeComponent("Root", bodies=[b1, b2])

    with _mock_adsk_env(doc_id="doc1", root_component=root):
        bundle = FusionCadScriptBundle()
        script = bundle.build("read", {"operation": "echo"})
        scope: dict = {}
        exec(compile(script, "<test-geom>", "exec"), scope)  # noqa: S102

        # 1. Exactly one candidate matches geometry signature WITH complete component_path -> exact
        res_exact = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "Bracket",
                "component_path": ("Root",),
                "geometry_signature": {"volume": 100.0, "faces_count": 6},
                "document_ref": "doc_doc1",
            }
        )
        assert res_exact["outcome"] == "exact"
        assert len(res_exact["candidates"]) == 1

        # 2. Geometry signature matches BUT component_path absent -> fails closed to ambiguous, NEVER exact!
        res_no_path = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "Bracket",
                "geometry_signature": {"volume": 100.0, "faces_count": 6},
                "document_ref": "doc_doc1",
            }
        )
        assert res_no_path["outcome"] == "ambiguous"
        assert len(res_no_path["candidates"]) == 1

        # 3. Zero candidates match geometry signature -> stale
        res_stale = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "Bracket",
                "component_path": ("Root",),
                "geometry_signature": {"volume": 999.0},
                "document_ref": "doc_doc1",
            }
        )
        assert res_stale["outcome"] == "stale"
        assert res_stale["candidates"] == []

        # 4. Multiple plausible candidates match geometry signature -> ambiguous, never guess!
        b3 = _FakeEntity("Bracket", "tok_b3", volume=100.0, is_solid=True)
        b3.faces = _FakeCollection([object()] * 6)
        root.bRepBodies = _FakeCollection([b1, b2, b3])

        res_ambiguous = scope["resolve_fusion_entity"](
            {
                "ref": "ent_1",
                "kind": "body",
                "name": "Bracket",
                "component_path": ("Root",),
                "geometry_signature": {"volume": 100.0, "faces_count": 6},
                "document_ref": "doc_doc1",
            }
        )
        assert res_ambiguous["outcome"] == "ambiguous"
        assert len(res_ambiguous["candidates"]) == 2


def test_common_design_context_supports_real_products_item_by_product_type(monkeypatch) -> None:
    import types

    product = types.SimpleNamespace(rootComponent=types.SimpleNamespace())

    class Products:
        def itemByProductType(self, product_type: str) -> Any:
            assert product_type == "DesignProductType"
            return product

    doc = types.SimpleNamespace(products=Products())
    app = types.SimpleNamespace(activeDocument=doc, activeProduct=None)

    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: app)
    fusion.Design = types.SimpleNamespace(cast=lambda value: value if value is product else None)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    script = FusionCadScriptBundle.build("read", {"operation": "echo", "text": "probe"})
    scope = {"__name__": "__main__"}
    exec(compile(script, "<fusion-design-context>", "exec"), scope)  # noqa: S102

    helper = scope["_fusion_design_from_context"]
    assert helper(app, doc) is product


def test_common_design_context_fails_closed_when_design_cast_rejects_product(monkeypatch) -> None:
    import types

    product = types.SimpleNamespace(rootComponent=types.SimpleNamespace())

    class Products:
        def itemByProductType(self, product_type: str) -> Any:
            assert product_type == "DesignProductType"
            return product

    doc = types.SimpleNamespace(products=Products())
    app = types.SimpleNamespace(activeDocument=doc, activeProduct=product)

    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: app)
    fusion.Design = types.SimpleNamespace(cast=lambda _value: None)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    script = FusionCadScriptBundle.build("read", {"operation": "echo", "text": "probe"})
    scope = {"__name__": "__main__"}
    exec(compile(script, "<fusion-design-cast-reject>", "exec"), scope)  # noqa: S102

    helper = scope["_fusion_design_from_context"]
    assert helper(app, doc) is None


def test_model_snapshot_accepts_empty_falsey_fusion_collections(monkeypatch) -> None:
    import types

    class Collection:
        def __init__(self, items=()):
            self._items = list(items)

        @property
        def count(self) -> int:
            return len(self._items)

        def item(self, index: int) -> Any:
            return self._items[index]

        def __bool__(self) -> bool:
            return bool(self._items)

    empty_attrs = lambda: Collection([])  # noqa: E731
    root = types.SimpleNamespace(
        name="Root",
        id="root",
        entityToken="root-token",
        allOccurrences=Collection([]),
        bRepBodies=Collection([]),
        sketches=Collection([]),
        attributes=empty_attrs(),
    )
    design = types.SimpleNamespace(
        rootComponent=root,
        timeline=Collection([]),
        allComponents=Collection([root]),
        allParameters=Collection([]),
    )

    class Products:
        def itemByProductType(self, product_type: str) -> Any:
            assert product_type == "DesignProductType"
            return design

    doc = types.SimpleNamespace(
        creationId="empty-design",
        dataId=None,
        dataFile=None,
        name="Untitled",
        isModified=False,
        savedVersion=None,
        products=Products(),
        attributes=empty_attrs(),
    )
    app = types.SimpleNamespace(activeDocument=doc, activeProduct=design)

    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: app)
    fusion.Design = types.SimpleNamespace(cast=lambda value: value if value is design else None)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    script = FusionCadScriptBundle.build("read", {"operation": "model_snapshot", "detail": "compact"})
    scope = {"__name__": "__main__"}
    exec(compile(script, "<fusion-empty-model-snapshot>", "exec"), scope)  # noqa: S102

    result = scope["_output"]
    assert result["status"] == "succeeded"
    assert result["document"]["document_ref"] == "doc_empty-design"
    assert result["data"]["fingerprint"]


def test_model_snapshot_uses_timeline_entity_as_stable_identity(monkeypatch) -> None:
    import types

    class Collection:
        def __init__(self, items=()):
            self._items = list(items)

        @property
        def count(self) -> int:
            return len(self._items)

        def item(self, index: int) -> Any:
            return self._items[index]

        def __bool__(self) -> bool:
            return bool(self._items)

    feature = types.SimpleNamespace(
        entityToken="feature-token-1",
        id=None,
        objectType="adsk::fusion::BaseFeature",
        name="Feature1",
        attributes=Collection([]),
    )
    timeline_item = types.SimpleNamespace(
        index=0,
        name="Feature1",
        isSuppressed=False,
        isRolledBack=False,
        isValid=True,
        healthStatus=None,
        entity=feature,
        isGroup=False,
    )
    root = types.SimpleNamespace(
        name="Root",
        id="root",
        entityToken="root-token",
        allOccurrences=Collection([]),
        bRepBodies=Collection([]),
        sketches=Collection([]),
        attributes=Collection([]),
    )
    design = types.SimpleNamespace(
        rootComponent=root,
        timeline=Collection([timeline_item]),
        allComponents=Collection([root]),
        allParameters=Collection([]),
    )

    class Products:
        def itemByProductType(self, product_type: str) -> Any:
            assert product_type == "DesignProductType"
            return design

    doc = types.SimpleNamespace(
        creationId="timeline-design",
        dataId=None,
        dataFile=None,
        name="Untitled",
        isModified=False,
        savedVersion=None,
        products=Products(),
        attributes=Collection([]),
    )
    app = types.SimpleNamespace(activeDocument=doc, activeProduct=design)

    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: app)
    fusion.Design = types.SimpleNamespace(cast=lambda value: value if value is design else None)
    adsk.core = core
    adsk.fusion = fusion
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", fusion)

    script = FusionCadScriptBundle.build(
        "read", {"operation": "model_snapshot", "detail": "compact"}
    )
    scope = {"__name__": "__main__"}
    exec(compile(script, "<fusion-timeline-entity-identity>", "exec"), scope)  # noqa: S102

    result = scope["_output"]
    assert result["status"] == "succeeded"
    assert result["data"]["features"][0]["id"] == "feature-token-1"


def test_p0_rendered_bundles_fit_default_desktop_argument_limit() -> None:
    """Default desktop relay must carry every static P0 Fusion script bundle."""
    import json

    from app.settings import DesktopNodeSettings

    bundle = FusionCadScriptBundle()
    payloads = (
        ("read", {"operation": "model_snapshot", "document_ref": "doc_x"}),
        ("inspect", {"operation": "describe", "target": {"ref": "ent_x", "native_token": "tok", "kind": "body"}}),
        ("view", {"operation": "camera_read", "document_ref": "doc_x"}),
        ("mutate", {"operation": "set", "target": {"ref": "ent_x", "native_token": "tok", "kind": "body"}, "name": "k", "value": "v", "expected_revision": "rev_1"}),
        ("transaction", {"operation": "begin", "transaction_id": "tx_x"}),
    )
    sizes = {
        group: len(json.dumps({"script": bundle.build(group, payload)}, separators=(",", ":")).encode("utf-8"))
        for group, payload in payloads
    }
    assert max(sizes.values()) <= DesktopNodeSettings().max_arguments_bytes, sizes

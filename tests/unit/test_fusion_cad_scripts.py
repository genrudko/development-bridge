from __future__ import annotations

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
        'import json\n'
        'API_VERSION = "fusion.cad/v1"\n'
        'PAYLOAD_RAW = __PAYLOAD_JSON__\n'
        'PAYLOAD = json.loads(PAYLOAD_RAW) if isinstance(PAYLOAD_RAW, str) else PAYLOAD_RAW\n'
        '# __GROUP_SCRIPT__\n'
        'if __name__ == "__main__" or True:\n'
        '    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text(
        'def run():\n'
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
        'import json\n'
        'API_VERSION = "fusion.cad/v1"\n'
        'PAYLOAD_RAW = __PAYLOAD_JSON__\n'
        'if __name__ == "__main__":\n'
        '    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text('def run(): return {}\n', encoding="utf-8")

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
        'import json\n'
        'API_VERSION = "fusion.cad/v1"\n'
        'PAYLOAD_RAW = __PAYLOAD_JSON__\n'
        '# __GROUP_SCRIPT__\n'
        '# __GROUP_SCRIPT__\n'
        'if __name__ == "__main__":\n'
        '    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text('def run(): return {}\n', encoding="utf-8")

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
        'import json\n'
        'API_VERSION = "fusion.cad/v1"\n'
        '# __GROUP_SCRIPT__\n'
        'if __name__ == "__main__":\n'
        '    _output = run()\n',
        encoding="utf-8",
    )
    group_path = custom_scripts / "custom.py.txt"
    group_path.write_text('def run(): return {}\n', encoding="utf-8")

    bundle = FusionCadScriptBundle(scripts_dir=custom_scripts)
    with pytest.raises(BridgeError) as exc:
        bundle.build("custom", {"operation": "test"})
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert "missing '__PAYLOAD_JSON__' marker" in exc.value.message

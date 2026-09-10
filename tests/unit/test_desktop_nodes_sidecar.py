"""Task 8 regression tests: desktop-node external-result sidecar recovery.

The sidecar written next to an external result JSON must never let a crafted
file register (and therefore expose/resolve) binary resources that the result
does not own. These tests pin the fail-closed recovery contract:

* containment and result-ownership of every recovered resource path;
* exact supported sidecar schema/version (v2, plus explicit legacy v1 upgrade);
* strict validation of every descriptor field;
* verification of the recovered file's real size and SHA-256;
* preserved parent/result binding, stable resource URI and TTL cleanup;
* generic JSON exports keep their process-local, short-lived export tokens.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time

import pytest

from app.api.errors import BridgeError
from app.desktop_nodes import DesktopNodeService
from app.settings import DesktopNodeSettings

PUBLIC_BASE_URL = "https://bridge.example"
PNG = b"\x89PNG\r\n\x1a\nsidecar-probe-image"
TTL_SECONDS = 3600


def configured(**updates):
    return DesktopNodeSettings.model_validate({"token": "secret", **updates})


def _value(png=PNG):
    return {
        "content": [{
            "type": "image",
            "data": base64.b64encode(png).decode("ascii"),
            "mimeType": "image/png",
        }],
        "isError": False,
    }


def _service(tmp_path, ttl=TTL_SECONDS):
    return DesktopNodeService(
        configured(result_artifact_directory=tmp_path, result_artifact_ttl_seconds=ttl),
        public_base_url=PUBLIC_BASE_URL,
        endpoint="/mcp",
    )


def _store(tmp_path, png=PNG):
    """Store a sanitized screenshot result; return (result_id, sidecar document)."""
    service = _service(tmp_path)
    reference = service.store_external_result(
        "desk-1", _value(png), sanitize_binary=True
    )["external_result"]
    result_id = reference["result_id"]
    sidecar = json.loads((tmp_path / f"{result_id}.resources.json").read_text("utf-8"))
    return result_id, sidecar


def _write_sidecar(tmp_path, result_id, sidecar):
    (tmp_path / f"{result_id}.resources.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )


def _recover(tmp_path, result_id):
    """Recover the stored result in a fresh process and return (service, metadata)."""
    service = _service(tmp_path)
    _, metadata = service.external_result({"result_id": result_id})
    return service, metadata


def _assert_no_resources(service, metadata, result_id):
    assert metadata["resources"] == []
    assert service._external_resources == {}
    # No stable binary resource URI may resolve, even with a guessed capability.
    assert service.resolve_external_export(f"r1.{result_id}.{'a' * 43}") is None


# ---------------------------------------------------------------------------
# 1. Containment: absolute paths and ../ traversal never resolve.
# ---------------------------------------------------------------------------


def test_sidecar_absolute_path_name_is_rejected(tmp_path):
    result_id, sidecar = _store(tmp_path)
    outside = tmp_path.parent / f"{result_id}-escape.png"
    outside.write_bytes(PNG)
    sidecar["resources"][0]["path_name"] = str(outside)
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)
    assert outside.read_bytes() == PNG


def test_sidecar_parent_traversal_path_name_is_rejected(tmp_path):
    result_id, sidecar = _store(tmp_path)
    outside = tmp_path.parent / f"{result_id}-escape.png"
    outside.write_bytes(PNG)
    sidecar["resources"][0]["path_name"] = f"../{result_id}-escape.png"
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)
    assert outside.read_bytes() == PNG


def test_sidecar_symlink_escape_is_rejected(tmp_path):
    result_id, sidecar = _store(tmp_path)
    outside = tmp_path.parent / f"{result_id}-escape.png"
    outside.write_bytes(PNG)
    link = tmp_path / f"{result_id}-res-0.png"
    link.unlink()
    link.symlink_to(outside)
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)
    assert outside.read_bytes() == PNG


# ---------------------------------------------------------------------------
# 2. Top-level schema/version and resources list shape.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["[]", "[1, 2]", "null", "3", '"sidecar"', "{"])
def test_sidecar_non_dict_top_level_fails_closed_without_exception(tmp_path, payload):
    result_id, _ = _store(tmp_path)
    (tmp_path / f"{result_id}.resources.json").write_text(payload, encoding="utf-8")

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"resources": []},
        {"resources": [{"version": 2}]},
        {"version": 3, "resources": []},
        {"version": 1.0, "resources": []},
        {"version": "2", "resources": []},
        {"version": True, "resources": []},
        {"version": None, "resources": []},
    ],
)
def test_sidecar_unsupported_version_or_missing_schema_fails_closed(tmp_path, document):
    result_id, _ = _store(tmp_path)
    _write_sidecar(tmp_path, result_id, document)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


@pytest.mark.parametrize("resources", [{}, "resources", 7, None, [[]], [1], ["x"]])
def test_sidecar_resources_list_shape_is_enforced(tmp_path, resources):
    result_id, sidecar = _store(tmp_path)
    sidecar["resources"] = resources
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


# ---------------------------------------------------------------------------
# 3. Descriptor fields are strictly validated and bounded.
# ---------------------------------------------------------------------------


def _mutations():
    return {
        "resource_id_missing": lambda d: d.pop("resource_id"),
        "resource_id_not_string": lambda d: d.update(resource_id=123456789012),
        "resource_id_too_short": lambda d: d.update(resource_id="short"),
        "resource_id_bad_chars": lambda d: d.update(resource_id="a" * 16 + "/../x"),
        "path_name_missing": lambda d: d.pop("path_name"),
        "path_name_wrong_index": lambda d: d.update(
            path_name=d["path_name"].replace("-res-0", "-res-1")
        ),
        "path_name_wrong_extension": lambda d: d.update(
            path_name=d["path_name"].replace(".png", ".txt")
        ),
        "path_name_separator": lambda d: d.update(
            path_name=f"sub/{d['path_name']}"
        ),
        "mime_type_missing": lambda d: d.pop("mime_type"),
        "mime_type_text": lambda d: d.update(mime_type="text/plain"),
        "mime_type_garbage": lambda d: d.update(mime_type="not a mime"),
        "mime_type_not_string": lambda d: d.update(mime_type={"image/png": True}),
        "file_name_missing": lambda d: d.pop("file_name"),
        "file_name_traversal": lambda d: d.update(file_name="../../etc/passwd.png"),
        "file_name_separator": lambda d: d.update(file_name="sub/dir.png"),
        "file_name_extension_mismatch": lambda d: d.update(file_name="payload.txt"),
        "file_name_not_string": lambda d: d.update(file_name=["x.png"]),
        "size_bytes_missing": lambda d: d.pop("size_bytes"),
        "size_bytes_zero": lambda d: d.update(size_bytes=0),
        "size_bytes_negative": lambda d: d.update(size_bytes=-1),
        "size_bytes_bool": lambda d: d.update(size_bytes=True),
        "size_bytes_huge": lambda d: d.update(size_bytes=2**40),
        "size_bytes_not_int": lambda d: d.update(size_bytes="1024"),
        "sha256_missing": lambda d: d.pop("sha256"),
        "sha256_uppercase": lambda d: d.update(sha256=d["sha256"].upper()),
        "sha256_short": lambda d: d.update(sha256="0" * 63),
        "sha256_not_string": lambda d: d.update(sha256=0),
        "created_at_missing": lambda d: d.pop("created_at"),
        "created_at_negative": lambda d: d.update(created_at=-1.0),
        "created_at_far_future": lambda d: d.update(created_at=time.time() + 10_000),
        "created_at_not_number": lambda d: d.update(created_at="soon"),
        "created_at_nan": lambda d: d.update(created_at=float("nan")),
        "stable_capability_missing": lambda d: d.pop("stable_capability"),
        "stable_capability_short": lambda d: d.update(stable_capability="a" * 31),
        "stable_capability_dotted": lambda d: d.update(
            stable_capability="a" * 20 + "." + "b" * 12
        ),
        "stable_capability_not_string": lambda d: d.update(stable_capability=42),
        "unknown_extra_key": lambda d: d.update(extra="nope"),
    }


def test_sidecar_descriptor_fields_are_strictly_validated(tmp_path):
    result_id, template = _store(tmp_path)
    for name, mutate in _mutations().items():
        sidecar = json.loads(json.dumps(template))
        mutate(sidecar["resources"][0])
        _write_sidecar(tmp_path, result_id, sidecar)
        service, metadata = _recover(tmp_path, result_id)
        try:
            _assert_no_resources(service, metadata, result_id)
        except AssertionError as exc:
            raise AssertionError(f"sidecar mutation accepted: {name}") from exc


def test_sidecar_duplicate_resource_ids_fail_closed(tmp_path):
    png = b"\x89PNG\r\n\x1a\nsecond-image-bytes"
    value = _value()
    value["content"].append({
        "type": "image",
        "data": base64.b64encode(png).decode("ascii"),
        "mimeType": "image/png",
    })
    service = _service(tmp_path)
    reference = service.store_external_result("desk-1", value, sanitize_binary=True)[
        "external_result"
    ]
    result_id = reference["result_id"]
    sidecar = json.loads((tmp_path / f"{result_id}.resources.json").read_text("utf-8"))
    assert len(sidecar["resources"]) == 2
    sidecar["resources"][1]["resource_id"] = sidecar["resources"][0]["resource_id"]
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


# ---------------------------------------------------------------------------
# 4. Recovered file must really be what the sidecar claims.
# ---------------------------------------------------------------------------


def test_sidecar_size_mismatch_fails_closed(tmp_path):
    result_id, sidecar = _store(tmp_path)
    resource_path = tmp_path / sidecar["resources"][0]["path_name"]
    resource_path.write_bytes(PNG[:-1])

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


def test_sidecar_sha256_mismatch_fails_closed(tmp_path):
    result_id, sidecar = _store(tmp_path)
    resource_path = tmp_path / sidecar["resources"][0]["path_name"]
    tampered = b"\x89PNG\r\n\x1a\nsidecar-probe-imagE"  # same length, different bytes
    assert len(tampered) == len(PNG)
    resource_path.write_bytes(tampered)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


def test_sidecar_resource_file_missing_fails_closed(tmp_path):
    result_id, sidecar = _store(tmp_path)
    (tmp_path / sidecar["resources"][0]["path_name"]).unlink()

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


# ---------------------------------------------------------------------------
# 5. Valid v2 sidecar: binding, stable URI, resolvable, deterministic rewrite.
# ---------------------------------------------------------------------------


def test_valid_v2_sidecar_recovers_identical_stable_uri_after_restart(tmp_path):
    result_id, sidecar = _store(tmp_path)
    first = _service(tmp_path)
    _, first_metadata = first.external_result({"result_id": result_id})
    first_resource = first_metadata["resources"][0]
    descriptor = sidecar["resources"][0]

    service, metadata = _recover(tmp_path, result_id)
    resource = metadata["resources"][0]

    assert resource["uri"] == first_resource["uri"]
    assert resource["file_name"] == descriptor["file_name"]
    assert resource["mime_type"] == descriptor["mime_type"]
    assert resource["size_bytes"] == descriptor["size_bytes"]
    assert resource["sha256"] == descriptor["sha256"]

    token = resource["uri"].rsplit("/", 1)[-1]
    resolved = service.resolve_external_export(token)
    assert resolved is not None
    path, item = resolved
    assert path.parent == tmp_path.resolve()
    assert path.name == descriptor["path_name"]
    assert path.read_bytes() == PNG
    assert item["mime_type"] == "image/png"
    assert item["sha256"] == descriptor["sha256"]


def test_recovered_resource_keeps_parent_result_binding(tmp_path):
    result_id, sidecar = _store(tmp_path)
    descriptor = sidecar["resources"][0]

    service, metadata = _recover(tmp_path, result_id)

    resource_id = descriptor["resource_id"]
    resource = service._external_resources.get(resource_id)
    assert resource is not None
    assert resource["parent_result_id"] == result_id
    assert service._external_results[result_id]["resource_ids"] == [resource_id]
    assert metadata["resources"][0]["uri"] == (
        f"{PUBLIC_BASE_URL}/mcp/desktop-results/exports/"
        f"r1.{result_id}.{descriptor['stable_capability']}"
    )
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,128}", descriptor["stable_capability"])


def test_recovered_v2_sidecar_is_rewritten_deterministically(tmp_path):
    result_id, sidecar = _store(tmp_path)
    _recover(tmp_path, result_id)

    sidecar_after = (tmp_path / f"{result_id}.resources.json").read_text("utf-8")
    assert json.loads(sidecar_after) == sidecar
    assert json.loads(sidecar_after)["version"] == 2


# ---------------------------------------------------------------------------
# 6. Legacy v1 sidecar: explicit, validated, deterministic upgrade only.
# ---------------------------------------------------------------------------


def test_legacy_v1_sidecar_upgrades_deterministically_to_v2(tmp_path):
    result_id, sidecar = _store(tmp_path)
    for descriptor in sidecar["resources"]:
        descriptor.pop("stable_capability")
    sidecar["version"] = 1
    _write_sidecar(tmp_path, result_id, sidecar)

    _unused_service, metadata = _recover(tmp_path, result_id)
    resource = metadata["resources"][0]
    assert len(metadata["resources"]) == 1
    assert resource["mime_type"] == "image/png"
    assert resource["uri"].startswith(f"{PUBLIC_BASE_URL}/mcp/desktop-results/exports/r1.")
    capability = resource["uri"].rsplit(".", 1)[-1]
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,128}", capability)

    upgraded = json.loads(
        (tmp_path / f"{result_id}.resources.json").read_text("utf-8")
    )
    assert upgraded["version"] == 2
    assert upgraded["resources"][0]["stable_capability"] == capability

    # The migrated capability is stable across a further restart.
    _, second_metadata = _recover(tmp_path, result_id)
    assert second_metadata["resources"][0]["uri"] == resource["uri"]


def test_malformed_v2_sidecar_is_not_treated_as_legacy(tmp_path):
    result_id, sidecar = _store(tmp_path)
    sidecar["resources"][0].pop("stable_capability")  # v2 requires it; v1 never had it
    sidecar_text = json.dumps(sidecar)
    (tmp_path / f"{result_id}.resources.json").write_text(sidecar_text, encoding="utf-8")

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)
    # The malformed sidecar is left untouched, never silently upgraded.
    assert (tmp_path / f"{result_id}.resources.json").read_text("utf-8") == sidecar_text


def test_legacy_v1_sidecar_with_v2_only_field_fails_closed(tmp_path):
    result_id, sidecar = _store(tmp_path)
    sidecar["version"] = 1  # v1 shape must not carry a stable capability
    _write_sidecar(tmp_path, result_id, sidecar)

    service, metadata = _recover(tmp_path, result_id)

    _assert_no_resources(service, metadata, result_id)


# ---------------------------------------------------------------------------
# 7. Generic JSON export stays a short-lived, process-local capability.
# ---------------------------------------------------------------------------


def test_generic_json_export_token_remains_process_local(tmp_path):
    result_id, _ = _store(tmp_path)
    reference = {"result_id": result_id}
    _, first_metadata = _service(tmp_path).external_result(reference)
    first_url = first_metadata["export_url"]
    first_token = first_url.rsplit("/", 1)[-1]

    service, second_metadata = _recover(tmp_path, result_id)

    second_token = second_metadata["export_url"].rsplit("/", 1)[-1]
    assert first_token != second_token
    assert not first_token.startswith("r1.")
    assert service.resolve_external_export(first_token) is None
    # The JSON result itself is still served through the fresh process-local token.
    resolved = service.resolve_external_export(second_token)
    assert resolved is not None
    assert json.loads(resolved[0].read_text("utf-8")) == json.loads(
        (tmp_path / f"{result_id}.json").read_text("utf-8")
    )


# ---------------------------------------------------------------------------
# 8. TTL cleanup is preserved for recovered results.
# ---------------------------------------------------------------------------


def test_expired_recovered_result_removes_sidecar_and_resources(tmp_path):
    result_id, sidecar = _store(tmp_path)
    old = time.time() - 120
    for path in tmp_path.iterdir():
        os.utime(path, (old, old))

    service = _service(tmp_path, ttl=60)
    with pytest.raises(BridgeError, match="unavailable"):
        service.external_result({"result_id": result_id})

    assert not (tmp_path / f"{result_id}.json").exists()
    assert not (tmp_path / f"{result_id}.resources.json").exists()
    assert not (tmp_path / sidecar["resources"][0]["path_name"]).exists()
    assert service._external_resources == {}


# ---------------------------------------------------------------------------
# 9. Direct contract checks for the dedicated sidecar parser helper.
# ---------------------------------------------------------------------------


def test_sidecar_parser_accepts_generated_v2_document():
    from app.desktop_nodes.service import parse_resource_sidecar

    descriptor = {
        "resource_id": "a" * 24,
        "path_name": "abcdefghijklmnopqrstuvwx-res-0.png",
        "mime_type": "image/png",
        "file_name": "screenshot_b64.png",
        "size_bytes": len(PNG),
        "sha256": hashlib.sha256(PNG).hexdigest(),
        "created_at": time.time(),
        "stable_capability": "c" * 43,
    }
    parsed = parse_resource_sidecar(
        {"version": 2, "resources": [descriptor]},
        result_id="abcdefghijklmnopqrstuvwx",
        max_resource_bytes=1_048_576,
        now=time.time(),
    )
    assert parsed == [descriptor]


def test_sidecar_parser_rejects_unsupported_documents():
    from app.desktop_nodes.service import parse_resource_sidecar

    now = time.time()
    result_id = "abcdefghijklmnopqrstuvwx"
    rejects = [
        None,
        [],
        "sidecar",
        {"version": 2},
        {"version": 2, "resources": {}},
        {"version": 3, "resources": []},
        {"version": True, "resources": []},
        {"version": 1, "resources": [{"stable_capability": "c" * 43}]},
    ]
    for document in rejects:
        assert parse_resource_sidecar(
            document, result_id=result_id, max_resource_bytes=1_048_576, now=now
        ) is None, document

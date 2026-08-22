from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.jobs import INLINE_VISUAL_LIMIT_BYTES, JobArtifact, read_visual_artifact


def artifact_for(path, data: bytes, *, media_type: str = "image/png") -> JobArtifact:
    return JobArtifact(
        job_id="job_" + "1" * 32,
        artifact_id="screenshot",
        path="screenshot.png",
        media_type=media_type,
        required=True,
        available=True,
        size_bytes=len(data),
        sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        storage_path=str(path),
    )


def test_png_snapshot_is_read(tmp_path):
    data = b"\x89PNG\r\n\x1a\nsmall-snapshot"
    path = tmp_path / "screenshot"
    path.write_bytes(data)

    assert read_visual_artifact(artifact_for(path, data), path) == data


def test_unsupported_media_type_is_rejected(tmp_path):
    data = b"<svg/>"
    path = tmp_path / "screenshot"
    path.write_bytes(data)

    with pytest.raises(BridgeError) as raised:
        read_visual_artifact(artifact_for(path, data, media_type="image/svg+xml"), path)

    assert raised.value.code is ErrorCode.POLICY_VIOLATION


def test_oversized_inline_artifact_is_rejected(tmp_path):
    path = tmp_path / "screenshot"
    path.write_bytes(b"")
    artifact = replace(
        artifact_for(path, b""), size_bytes=INLINE_VISUAL_LIMIT_BYTES + 1
    )

    with pytest.raises(BridgeError) as raised:
        read_visual_artifact(artifact, path)

    assert raised.value.code is ErrorCode.POLICY_VIOLATION
    assert raised.value.details == {
        "size_bytes": INLINE_VISUAL_LIMIT_BYTES + 1,
        "limit": INLINE_VISUAL_LIMIT_BYTES,
    }


@pytest.mark.parametrize("corruption", ["size", "digest"])
def test_snapshot_size_or_digest_mismatch_is_not_found(tmp_path, corruption):
    data = b"\x89PNG\r\n\x1a\nsmall-snapshot"
    path = tmp_path / "screenshot"
    path.write_bytes(data)
    artifact = artifact_for(path, data)
    if corruption == "size":
        artifact = replace(artifact, size_bytes=len(data) - 1)
    else:
        artifact = replace(artifact, sha256="sha256:" + "0" * 64)

    with pytest.raises(BridgeError) as raised:
        read_visual_artifact(artifact, path)

    assert raised.value.code is ErrorCode.ARTIFACT_NOT_FOUND

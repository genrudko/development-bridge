from __future__ import annotations

import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.capabilities import CapabilityMatrix
from app.fusion_cad.models import CadResult, CapabilityRecord
from app.fusion_cad.service import FusionCadService


@pytest.mark.asyncio
async def test_read_entity_dispatches_registered_document_bound_native_hint() -> None:
    captured: dict[str, object] = {}
    script_bundle = MagicMock()

    def build(group: str, payload: dict[str, object]) -> str:
        captured["group"] = group
        captured["payload"] = dict(payload)
        return "# captured test script"

    script_bundle.build.side_effect = build
    desktop = MagicMock(spec=DesktopNodeService)
    desktop.call = AsyncMock()
    desktop.submit = AsyncMock()
    desktop.store_external_result = MagicMock()

    service = FusionCadService(desktop, script_bundle=script_bundle)
    service.set_node_capabilities(
        "desk-1",
        CapabilityMatrix.from_records(
            [CapabilityRecord(name="entity.token_resolver", state="supported")]
        ),
    )
    service.revision_tracker.observe("doc_1", "fp_before")
    issued = service.ref_registry.issue(
        document_ref="doc_1",
        kind="body",
        name="Body1",
        native_token="native_body_token",
    )
    desktop.call.return_value = {
        "api_version": "fusion.cad/v1",
        "status": "succeeded",
        "summary": "Resolved entity",
        "data": {
            "outcome": "exact",
            "ref": issued.ref,
            "candidates": [],
            "document_ref": "doc_1",
        },
    }

    result = await service.execute(
        {
            "node_id": "desk-1",
            "document_ref": "doc_1",
            "operation": "entity",
            "ref": issued.ref,
        },
        group="read",
    )

    assert isinstance(result, CadResult)
    assert captured["group"] == "read"
    dispatched = captured["payload"]
    assert isinstance(dispatched, dict)
    assert dispatched["ref"] == issued.ref
    assert dispatched["native_token"] == "native_body_token"
    assert dispatched["kind"] == "body"
    assert dispatched["name"] == "Body1"


def test_pyproject_packages_fusion_runtime_script_templates() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text("utf-8"))
    setuptools_config = pyproject["tool"]["setuptools"]
    package_data = setuptools_config.get("package-data", {})
    patterns = package_data.get("app.fusion_cad", [])

    assert "fusion_scripts/*.py.txt" in patterns
    templates = sorted(
        path.name
        for path in (repo_root / "app" / "fusion_cad" / "fusion_scripts").glob("*.py.txt")
    )
    assert "common.py.txt" in templates
    assert "read.py.txt" in templates
    assert "transaction.py.txt" in templates


@pytest.mark.asyncio
async def test_implicit_document_context_is_scoped_to_desktop_node() -> None:
    captured: dict[str, object] = {}
    script_bundle = MagicMock()

    def build(group: str, payload: dict[str, object]) -> str:
        captured["group"] = group
        captured["payload"] = dict(payload)
        return "# captured test script"

    script_bundle.build.side_effect = build
    desktop = MagicMock(spec=DesktopNodeService)
    desktop.call = AsyncMock(
        return_value={
            "api_version": "fusion.cad/v1",
            "status": "succeeded",
            "summary": "Resolved entity",
            "data": {"document_ref": "doc_a"},
        }
    )
    desktop.submit = AsyncMock()
    desktop.store_external_result = MagicMock()
    service = FusionCadService(desktop, script_bundle=script_bundle)
    matrix = CapabilityMatrix.from_records(
        [CapabilityRecord(name="entity.token_resolver", state="supported")]
    )
    service.set_node_capabilities("node-a", matrix)
    service.set_node_capabilities("node-b", matrix)

    service._finalize_completed_execution(
        CadResult(
            status="succeeded",
            summary="Observed A",
            document={"document_ref": "doc_a", "model_revision": "rev_1"},
            data={"fingerprint": "fp_a"},
        ),
        effective_bundle_group="read",
        op="echo",
        payload={"operation": "echo", "document_ref": "doc_a"},
        node_id="node-a",
    )
    service._finalize_completed_execution(
        CadResult(
            status="succeeded",
            summary="Observed B",
            document={"document_ref": "doc_b", "model_revision": "rev_1"},
            data={"fingerprint": "fp_b"},
        ),
        effective_bundle_group="read",
        op="echo",
        payload={"operation": "echo", "document_ref": "doc_b"},
        node_id="node-b",
    )
    issued = service.ref_registry.issue(
        document_ref="doc_a",
        kind="body",
        name="Body A",
        native_token="native_a",
    )

    await service.execute(
        {"node_id": "node-a", "operation": "entity", "ref": issued.ref},
        group="read",
    )

    assert captured["group"] == "read"
    dispatched = captured["payload"]
    assert isinstance(dispatched, dict)
    assert dispatched["document_ref"] == "doc_a"
    assert dispatched["native_token"] == "native_a"

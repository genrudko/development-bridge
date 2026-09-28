# Fusion Desktop Image Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** View a retained Fusion desktop image directly as MCP `ImageContent`, without copying it through a job artifact.

**Architecture:** Reuse `DesktopNodeService` as authority for `desktop-results` capability URIs/files. Add one service resolver for supported image resources and one hidden `fusion_result_view` MCP adapter using the same `Image(...).to_image_content()` path as `job_artifact_view`.

**Tech Stack:** Python, MCP SDK, pytest.

**Spec:** `docs/research/fusion-cad-agent-operational-roadmap-2026-09-11.md`

## Global Constraints
- Reuse existing storage/export semantics; no new store, fetcher, transport, or CV pipeline.
- Accept only Bridge-issued desktop-result resource URIs and `image/png`, `image/jpeg`, `image/webp`.
- No network fetch; read the retained local resource file.
- Existing `fusion_call`/domain behavior stays unchanged.

---

### Task 1: Resolve retained desktop images
**Files:** Modify `app/desktop_nodes/service.py`; test `tests/unit/test_desktop_nodes.py`.
**Produces:** `DesktopNodeService.external_image_resource(uri: str) -> tuple[bytes, dict[str, Any]]`.

- [x] Write RED tests: valid emitted PNG URI returns exact bytes/metadata; foreign URI, JSON export URI, unsupported MIME, stale/unknown capability fail with `INVALID_ARGUMENT`.
- [x] Run `PYTHONPATH=$WT $PY -m pytest -q tests/unit/test_desktop_nodes.py -k external_image_resource`; expect missing-method failure.
- [x] Implement URI validation against the configured public `desktop-results/exports` prefix, URL-decode only the capability token, delegate to `resolve_external_export`, require supported image MIME, then return bytes plus `uri/file_name/mime_type/size_bytes/sha256`.
- [x] Re-run focused service tests plus existing external-image-resource tests; expect PASS.

### Task 2: Expose hidden `fusion_result_view`
**Files:** Modify `app/tools/fusion.py`, `tests/contract/test_tool_surface.py`, `tests/unit/test_fusion_tool_external_result.py`.
**Consumes:** `{ "resource_uri": "<Bridge-issued image ResourceLink URI>" }`.
**Produces:** normal success text plus exactly one MCP `ImageContent`.

- [x] Write RED tool/contract tests for strict schema and returned image content.
- [x] Run focused tests; expect tool-absent failure.
- [x] Implement handler calling `external_image_resource`, map MIME to `png/jpeg/webp`, append `Image(...).to_image_content()`, and register the strict hidden tool.
- [x] Run focused viewer/service tests, affected contract tests, and `git diff --check`; expect PASS.

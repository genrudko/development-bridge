from __future__ import annotations

import json

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.shimmer import ShimmerHandsAdapter


GUARD_A = "a" * 64
GUARD_B = "b" * 64
GUARD_C = "c" * 64
PRIVATE_API_VERSION = "bridge.shimmer/v1"


class FakeDesktop:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def call(self, node_id, tool_name, arguments, journal=None):
        self.calls.append((node_id, tool_name, arguments, journal))
        return self.replies.pop(0)


@pytest.mark.asyncio
async def test_adapter_calls_only_private_guard_tool_and_parses_evidence():
    desktop = FakeDesktop([{"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"}])

    evidence = await ShimmerHandsAdapter(desktop).guard("rich-a", "doc_a")

    assert evidence.guard == GUARD_A
    assert desktop.calls[0][:3] == (
        "rich-a",
        "_bridge_cad_guard",
        {"document_ref": "doc_a"},
    )


@pytest.mark.asyncio
async def test_adapter_maps_provider_errors_without_leaking_payload_or_token():
    secret = "token::provider-secret"
    desktop = FakeDesktop([{
        "api_version": PRIVATE_API_VERSION,
        "isError": True,
        "error": {"code": "TYPE_MISMATCH", "applied": False, "message": secret, "details": {"token": secret}},
    }])

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).apply(
            "rich-a", "doc_a", mode="commit", expected_guard=GUARD_A, operations=[]
        )

    assert exc_info.value.code == ErrorCode.TYPE_MISMATCH
    assert secret not in str(exc_info.value)
    assert secret not in json.dumps(exc_info.value.details)


@pytest.mark.asyncio
async def test_adapter_provider_error_without_applied_false_after_dispatch_is_uncertain():
    desktop = FakeDesktop([{
        "api_version": PRIVATE_API_VERSION,
        "ok": False,
        "error": {"code": "TYPE_MISMATCH"},
    }])

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).apply(
            "rich-a", "doc_a", mode="commit", expected_guard=GUARD_A, operations=[]
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN


@pytest.mark.asyncio
async def test_adapter_rejects_malformed_success_evidence():
    desktop = FakeDesktop([{"api_version": PRIVATE_API_VERSION, "guard_before": GUARD_A, "effects": []}])

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).apply(
            "rich-a", "doc_a", mode="preview", expected_guard=GUARD_A, operations=[]
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN


@pytest.mark.asyncio
async def test_adapter_committed_receipt_with_mismatched_guard_before_is_uncertain():
    desktop = FakeDesktop([{
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "mode": "commit",
        "guard_before": GUARD_C,
        "guard_after": GUARD_B,
        "effects": [],
        "entities": {"created": [], "changed": []},
        "committed": True,
    }])

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).apply(
            "rich-a", "doc_a", mode="commit", expected_guard=GUARD_A,
            operations=[{"op": "sketch.create", "params": {}}],
        )

    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN


@pytest.mark.asyncio
async def test_adapter_rejects_wrong_private_api_version():
    desktop = FakeDesktop([{
        "api_version": "wrong/v0",
        "guard": "a" * 64,
        "document_ref": "doc_a",
    }])
    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).guard("rich-a", "doc_a")
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR


@pytest.mark.asyncio
async def test_adapter_rejects_non_sha256_provider_guard():
    desktop = FakeDesktop([{
        "api_version": "bridge.shimmer/v1",
        "guard": "not-a-sha256-guard",
        "document_ref": "doc_a",
    }])
    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).guard("rich-a", "doc_a")
    assert exc_info.value.code == ErrorCode.FUSION_API_ERROR



@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["commit", "preview"])
async def test_adapter_malformed_apply_receipt_after_dispatch_is_uncertain(mode):
    desktop = FakeDesktop([{
        "api_version": "wrong/v0",
        "mode": mode,
        "guard_before": GUARD_A,
        "guard_after": GUARD_B if mode == "commit" else GUARD_A,
        "effects": [],
    }])
    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(desktop).apply(
            "rich-a", "doc_a", mode=mode, expected_guard=GUARD_A,
            operations=[{"op": "sketch.create", "params": {}}],
        )
    assert exc_info.value.code == ErrorCode.OPERATION_UNCERTAIN

@pytest.mark.asyncio
async def test_preview_waits_for_post_undo_guard_before_reporting_restored():
    desktop = FakeDesktop([
        {
            "api_version": PRIVATE_API_VERSION,
            "document_ref": "doc_a",
            "mode": "preview",
            "guard_before": GUARD_A,
            "preview_guard": GUARD_B,
            "effects": [],
            "entities": {"created": [], "changed": []},
            "committed": False,
            "rollback_pending": True,
        },
        {"api_version": PRIVATE_API_VERSION, "guard": GUARD_A, "document_ref": "doc_a"},
    ])

    evidence = await ShimmerHandsAdapter(desktop).apply(
        "rich-a", "doc_a", mode="preview", expected_guard=GUARD_A,
        operations=[{"op": "sketch.create", "params": {}}],
    )

    assert evidence.baseline_restored is True
    assert evidence.guard_after == GUARD_A
    assert [call[1] for call in desktop.calls] == ["_bridge_cad_apply", "_bridge_cad_guard"]


@pytest.mark.asyncio
async def test_adapter_resolves_externalized_apply_receipt_before_private_decode():
    payload = {
        "api_version": PRIVATE_API_VERSION,
        "document_ref": "doc_a",
        "mode": "preview",
        "guard_before": GUARD_A,
        "guard_after": GUARD_A,
        "effects": [],
        "entities": {"created": [], "changed": []},
        "committed": False,
        "baseline_restored": True,
    }

    class ExternalDesktop(FakeDesktop):
        def __init__(self):
            super().__init__([{"external_result": {"result_id": "result-1"}}])
            self.external_calls = []

        def external_result(self, reference):
            self.external_calls.append(reference)
            return payload, {"size_bytes": 123, "sha256": "0" * 64}

    desktop = ExternalDesktop()
    evidence = await ShimmerHandsAdapter(desktop).apply(
        "rich-a",
        "doc_a",
        mode="preview",
        expected_guard=GUARD_A,
        operations=[{"op": "sketch.create", "params": {}}],
    )

    assert evidence.mode == "preview"
    assert evidence.baseline_restored is True
    assert desktop.external_calls == [{"result_id": "result-1"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        ErrorCode.DESKTOP_NODE_NOT_CONFIGURED,
        ErrorCode.DESKTOP_NODE_NOT_FOUND,
        ErrorCode.DESKTOP_NODE_OFFLINE,
        ErrorCode.DESKTOP_NODE_BUSY,
    ],
)
async def test_adapter_preserves_proven_predispatch_desktop_failures(code):
    class RaisingDesktop:
        async def call(self, node_id, tool_name, arguments, journal=None):
            raise BridgeError(code, "private transport failure", retryable=True)

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(RaisingDesktop()).apply(
            "rich-a",
            "doc_a",
            mode="commit",
            expected_guard=GUARD_A,
            operations=[{"op": "sketch.create", "params": {}}],
        )

    assert exc_info.value.code == code
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("timed_out", ErrorCode.DESKTOP_NODE_TIMEOUT),
        ("uncertain", ErrorCode.OPERATION_UNCERTAIN),
    ],
)
async def test_adapter_uses_desktop_timeout_claim_state_for_mutation_uncertainty(status, expected_code):
    class TimeoutDesktop:
        async def call(self, node_id, tool_name, arguments, journal=None):
            raise BridgeError(
                ErrorCode.DESKTOP_NODE_TIMEOUT,
                "private timeout",
                retryable=False,
                details={"status": status},
            )

    with pytest.raises(FusionCadError) as exc_info:
        await ShimmerHandsAdapter(TimeoutDesktop()).apply(
            "rich-a",
            "doc_a",
            mode="commit",
            expected_guard=GUARD_A,
            operations=[{"op": "sketch.create", "params": {}}],
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False

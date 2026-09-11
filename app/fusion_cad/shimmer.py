from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.api.errors import BridgeError, ErrorCode
from app.desktop_nodes.service import DesktopNodeService
from app.fusion_cad.errors import FusionCadError

PRIVATE_API_VERSION = "bridge.shimmer/v1"
_PROVIDER_GUARD_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_PROVEN_PREDISPATCH_CODES = frozenset(
    {
        ErrorCode.INVALID_ARGUMENT,
        ErrorCode.DESKTOP_NODE_NOT_CONFIGURED,
        ErrorCode.DESKTOP_NODE_NOT_FOUND,
        ErrorCode.DESKTOP_NODE_OFFLINE,
        ErrorCode.DESKTOP_NODE_BUSY,
    }
)


class _ShimmerProviderRejected(FusionCadError):
    """A well-formed overlay rejection that proves a classified provider outcome."""


@dataclass(frozen=True, slots=True)
class ProviderGuardEvidence:
    guard: str


@dataclass(frozen=True, slots=True)
class HandsEntityEvidence:
    kind: str
    native_token: str


@dataclass(frozen=True, slots=True)
class HandsApplyEvidence:
    mode: Literal["commit", "preview"]
    guard_before: str
    guard_after: str
    effects: tuple[Mapping[str, Any], ...]
    created: tuple[HandsEntityEvidence, ...]
    changed: tuple[HandsEntityEvidence, ...]
    committed: bool
    baseline_restored: bool


class ShimmerHandsAdapter:
    """Private adapter for the pinned Shimmer Hands overlay."""

    def __init__(self, desktop_nodes: DesktopNodeService) -> None:
        self._desktop_nodes = desktop_nodes

    @staticmethod
    def _payload(raw: Any) -> Mapping[str, Any]:
        if not isinstance(raw, Mapping):
            raise FusionCadError(ErrorCode.FUSION_API_ERROR)
        if "content" in raw:
            blocks = raw.get("content")
            if not isinstance(blocks, list):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            candidate = None
            for block in blocks:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    try:
                        candidate = json.loads(str(block.get("text", "")))
                    except (TypeError, ValueError):
                        raise FusionCadError(ErrorCode.FUSION_API_ERROR) from None
                    break
            if not isinstance(candidate, Mapping):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            raw = candidate
        if raw.get("api_version") != PRIVATE_API_VERSION:
            raise FusionCadError(ErrorCode.FUSION_API_ERROR)
        if raw.get("isError") is True or raw.get("ok") is False or "error" in raw:
            error = raw.get("error")
            code_value = error.get("code") if isinstance(error, Mapping) else raw.get("code")
            try:
                code = ErrorCode(str(code_value))
            except ValueError:
                code = ErrorCode.FUSION_API_ERROR
            raise _ShimmerProviderRejected(code)
        return raw

    async def _call(
        self,
        node_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        expected_session_generation: int | None = None,
    ) -> Mapping[str, Any]:
        mutation = tool_name == "_bridge_cad_apply"
        call_kwargs: dict[str, Any] = {
            "journal": {
                "mutation": mutation,
                "summary": "Private Fusion CAD provider operation",
            }
        }
        if expected_session_generation is not None:
            call_kwargs["expected_session_generation"] = expected_session_generation
        try:
            raw = await self._desktop_nodes.call(
                node_id, tool_name, arguments, **call_kwargs
            )
        except FusionCadError:
            raise
        except BridgeError as exc:
            code = exc.code if isinstance(exc.code, ErrorCode) else ErrorCode.FUSION_API_ERROR
            if mutation:
                timed_out_before_claim = (
                    code == ErrorCode.DESKTOP_NODE_TIMEOUT
                    and isinstance(exc.details, Mapping)
                    and exc.details.get("status") == "timed_out"
                )
                if code in _PROVEN_PREDISPATCH_CODES or timed_out_before_claim:
                    raise FusionCadError(code, retryable=exc.retryable) from None
                raise FusionCadError(ErrorCode.OPERATION_UNCERTAIN) from None
            raise FusionCadError(code, retryable=exc.retryable) from None

        external = raw.get("external_result") if isinstance(raw, Mapping) else None
        if isinstance(external, Mapping):
            try:
                raw, _metadata = self._desktop_nodes.external_result(dict(external))
            except Exception:
                raise FusionCadError(
                    ErrorCode.OPERATION_UNCERTAIN if mutation else ErrorCode.FUSION_API_ERROR
                ) from None
        return self._payload(raw)

    async def guard(
        self,
        rich_node: str,
        document_ref: str,
        *,
        expected_session_generation: int | None = None,
    ) -> ProviderGuardEvidence:
        raw = await self._call(
            rich_node,
            "_bridge_cad_guard",
            {"document_ref": document_ref},
            expected_session_generation=expected_session_generation,
        )
        guard = raw.get("guard")
        if not isinstance(guard, str) or _PROVIDER_GUARD_RE.fullmatch(guard) is None:
            raise FusionCadError(ErrorCode.FUSION_API_ERROR)
        returned_doc = raw.get("document_ref")
        if returned_doc != document_ref:
            raise FusionCadError(ErrorCode.WRONG_DOCUMENT)
        return ProviderGuardEvidence(guard=guard)

    @staticmethod
    def _entities(raw: Any) -> tuple[HandsEntityEvidence, ...]:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise FusionCadError(ErrorCode.FUSION_API_ERROR)
        result = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            kind = item.get("kind")
            token = item.get("token") or item.get("native_token")
            if not isinstance(kind, str) or not kind or not isinstance(token, str) or not token:
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            result.append(HandsEntityEvidence(kind=kind, native_token=token))
        return tuple(result)

    async def apply(
        self,
        rich_node: str,
        document_ref: str,
        *,
        mode: Literal["commit", "preview"],
        expected_guard: str,
        operations: Sequence[Mapping[str, Any]],
        expected_session_generation: int | None = None,
    ) -> HandsApplyEvidence:
        if _PROVIDER_GUARD_RE.fullmatch(expected_guard) is None:
            raise FusionCadError(ErrorCode.REVISION_CONFLICT)

        try:
            raw = await self._call(
                rich_node,
                "_bridge_cad_apply",
                {
                    "document_ref": document_ref,
                    "expected_guard": expected_guard,
                    "mode": mode,
                    "operations": list(operations),
                },
                expected_session_generation=expected_session_generation,
            )
            if raw.get("document_ref") != document_ref:
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            if raw.get("mode") not in (None, mode):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            before, after, effects = (
                raw.get("guard_before"),
                raw.get("guard_after"),
                raw.get("effects"),
            )
            if (
                not isinstance(before, str)
                or _PROVIDER_GUARD_RE.fullmatch(before) is None
                or not isinstance(after, str)
                or _PROVIDER_GUARD_RE.fullmatch(after) is None
                or not isinstance(effects, list)
                or any(not isinstance(effect, Mapping) for effect in effects)
            ):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            if before != expected_guard:
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            entities = (
                raw.get("entities")
                if isinstance(raw.get("entities"), Mapping)
                else raw
            )
            created = self._entities(entities.get("created", []))
            changed = self._entities(entities.get("changed", []))
            committed = raw.get("committed", mode == "commit")
            restored = raw.get(
                "baseline_restored", mode == "preview" and after == before
            )
            if mode == "commit" and committed is not True:
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
            if mode == "preview" and (restored is not True or after != before):
                raise FusionCadError(ErrorCode.FUSION_API_ERROR)
        except _ShimmerProviderRejected as exc:
            # Overlay errors are structured evidence. In particular its
            # FUSION_API_ERROR is emitted only before mutation or after a proven
            # abort; OPERATION_UNCERTAIN remains uncertain.
            raise FusionCadError(exc.code) from None
        except FusionCadError as exc:
            # Once apply has been dispatched, any non-structured/malformed
            # receipt cannot prove whether commit or preview abort completed.
            # Preserve only failures that the transport itself proved happened
            # before provider execution; everything else is non-retryable.
            if (
                exc.code in _PROVEN_PREDISPATCH_CODES
                or exc.code in (
                    ErrorCode.DESKTOP_NODE_TIMEOUT,
                    ErrorCode.REVISION_CONFLICT,
                    ErrorCode.TYPE_MISMATCH,
                    ErrorCode.OPERATION_UNCERTAIN,
                )
            ):
                raise
            raise FusionCadError(ErrorCode.OPERATION_UNCERTAIN) from None

        return HandsApplyEvidence(
            mode=mode,
            guard_before=before,
            guard_after=after,
            effects=tuple(dict(effect) for effect in effects),
            created=created,
            changed=changed,
            committed=bool(committed),
            baseline_restored=bool(restored),
        )

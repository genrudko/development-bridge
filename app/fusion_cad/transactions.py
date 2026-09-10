"""P0 in-memory staged-transaction state and replay evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError


class TransactionState(StrEnum):
    NEW = "NEW"
    STAGED = "STAGED"
    PREVIEWED = "PREVIEWED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    transaction_id: str
    document_ref: str
    baseline_revision: str
    baseline_fingerprint: str
    baseline_snapshot: Mapping[str, Any]
    state: TransactionState = TransactionState.NEW
    plan: tuple[Mapping[str, Any], ...] = ()
    plan_hash: str = ""
    preview_evidence: Mapping[str, Any] | None = None
    commit_evidence: Mapping[str, Any] | None = None


def _clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _plan_hash(plan: tuple[Mapping[str, Any], ...]) -> str:
    raw = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


class TransactionStore:
    def __init__(self) -> None:
        self._records: dict[str, TransactionRecord] = {}

    def get(self, transaction_id: str) -> TransactionRecord:
        record = self._records.get(transaction_id)
        if record is None:
            raise FusionCadError(
                ErrorCode.INVALID_ARGUMENT, "Transaction does not exist"
            )
        return _clone(record)

    def find(self, transaction_id: str) -> TransactionRecord | None:
        record = self._records.get(transaction_id)
        return _clone(record) if record is not None else None

    def begin(
        self,
        transaction_id: str,
        document_ref: str,
        baseline_revision: str,
        baseline_fingerprint: str,
        baseline_snapshot: Mapping[str, Any],
    ) -> TransactionRecord:
        if transaction_id in self._records:
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction already exists"
            )
        self._records[transaction_id] = TransactionRecord(
            transaction_id,
            document_ref,
            baseline_revision,
            baseline_fingerprint,
            _clone(dict(baseline_snapshot)),
        )
        return self.get(transaction_id)

    def stage(
        self, transaction_id: str, action: Mapping[str, Any]
    ) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state not in (TransactionState.NEW, TransactionState.STAGED):
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT,
                "Transaction is terminal or preview is active",
            )
        plan = record.plan + (_clone(dict(action)),)
        self._records[transaction_id] = replace(
            record, state=TransactionState.STAGED, plan=plan, plan_hash=_plan_hash(plan)
        )
        return self.get(transaction_id)

    def _assert_fresh(self, record: TransactionRecord, fingerprint: str) -> None:
        if fingerprint != record.baseline_fingerprint:
            raise FusionCadError(
                ErrorCode.REVISION_CONFLICT,
                "Transaction baseline is stale",
                details={
                    "transaction_id": record.transaction_id,
                    "expected_fingerprint": record.baseline_fingerprint,
                    "current_fingerprint": fingerprint,
                    "applied": False,
                },
            )

    def begin_preview(self, transaction_id: str, fingerprint: str) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state is not TransactionState.STAGED or not record.plan:
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction is not staged"
            )
        self._assert_fresh(record, fingerprint)
        self._records[transaction_id] = replace(
            record, state=TransactionState.PREVIEWED
        )
        return self.get(transaction_id)

    def finish_preview(
        self, transaction_id: str, *, preview: Mapping[str, Any]
    ) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state is not TransactionState.PREVIEWED:
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction preview is not active"
            )
        evidence = _clone(dict(preview))
        evidence["durable"] = False
        self._records[transaction_id] = replace(
            record, state=TransactionState.STAGED, preview_evidence=evidence
        )
        return self.get(transaction_id)

    def begin_commit(self, transaction_id: str, fingerprint: str) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state is not TransactionState.STAGED or not record.plan:
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction cannot be committed"
            )
        self._assert_fresh(record, fingerprint)
        return record

    def finish_commit(
        self, transaction_id: str, evidence: Mapping[str, Any]
    ) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state is not TransactionState.STAGED:
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction cannot be committed"
            )
        preview_signature = (record.preview_evidence or {}).get("replay_signature")
        commit_signature = evidence.get("replay_signature")
        if not isinstance(preview_signature, Mapping) or not isinstance(commit_signature, Mapping) or dict(preview_signature) != dict(commit_signature):
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT,
                "Committed replay is not semantically equivalent to the accepted preview",
                details={"transaction_id": transaction_id, "applied": True, "replayed": False},
            )
        self._records[transaction_id] = replace(
            record,
            state=TransactionState.COMMITTED,
            commit_evidence=_clone(dict(evidence)),
        )
        return self.get(transaction_id)

    def rollback(self, transaction_id: str) -> TransactionRecord:
        record = self.get(transaction_id)
        if record.state in (TransactionState.COMMITTED, TransactionState.ABORTED):
            raise FusionCadError(
                ErrorCode.TRANSACTION_CONFLICT, "Transaction is terminal"
            )
        self._records[transaction_id] = replace(record, state=TransactionState.ABORTED)
        return self.get(transaction_id)

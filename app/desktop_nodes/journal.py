from __future__ import annotations

import json
import os
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any


class OperationJournal:
    """Bounded in-memory operation index with optional durable JSONL snapshots."""

    def __init__(self, path: Path | None, history_limit: int, max_bytes: int) -> None:
        self.path = path.expanduser().resolve() if path is not None else None
        self.history_limit = history_limit
        self.max_bytes = max_bytes
        self._operations: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._command_index: dict[str, str] = {}
        if self.path is not None:
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        if not self.path.exists():
            return
        recent: deque[str] = deque(maxlen=max(self.history_limit * 4, 100))
        try:
            with self.path.open('r', encoding='utf-8') as handle:
                for line in handle:
                    if line.strip():
                        recent.append(line)
        except OSError:
            return
        for line in recent:
            try:
                snapshot = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(snapshot, dict):
                continue
            operation_id = snapshot.get('operation_id')
            command_id = snapshot.get('command_id')
            if not isinstance(operation_id, str) or not isinstance(command_id, str):
                continue
            self._operations.pop(operation_id, None)
            self._operations[operation_id] = snapshot
            self._command_index[command_id] = operation_id
        self._trim_memory()

    def create(self, snapshot: dict[str, Any]) -> None:
        operation_id = snapshot['operation_id']
        if operation_id in self._operations:
            raise ValueError('operation id already exists')
        self._operations[operation_id] = dict(snapshot)
        self._command_index[snapshot['command_id']] = operation_id
        self._append(self._operations[operation_id])
        self._trim_memory()

    def update(self, operation_id: str, **updates: Any) -> dict[str, Any] | None:
        snapshot = self._operations.get(operation_id)
        if snapshot is None:
            return None
        snapshot = {**snapshot, **updates}
        self._operations.pop(operation_id, None)
        self._operations[operation_id] = snapshot
        command_id = snapshot.get('command_id')
        if isinstance(command_id, str):
            self._command_index[command_id] = operation_id
        self._append(snapshot)
        self._trim_memory()
        return dict(snapshot)

    def by_command(self, command_id: str) -> dict[str, Any] | None:
        operation_id = self._command_index.get(command_id)
        if operation_id is None:
            return None
        snapshot = self._operations.get(operation_id)
        return dict(snapshot) if snapshot is not None else None

    def get(self, operation_id: str) -> dict[str, Any] | None:
        snapshot = self._operations.get(operation_id)
        return dict(snapshot) if snapshot is not None else None

    def recent(self, node_id: str, limit: int = 10) -> list[dict[str, Any]]:
        matches = [dict(item) for item in self._operations.values() if item.get('node_id') == node_id]
        return matches[-limit:]

    def uncertain(self, node_id: str, limit: int = 20) -> list[dict[str, Any]]:
        matches = [
            dict(item)
            for item in self._operations.values()
            if item.get('node_id') == node_id and item.get('status') == 'uncertain'
        ]
        return matches[-limit:]

    def incomplete(self) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self._operations.values()
            if item.get('status') in {'queued', 'claimed'}
        ]

    def _append(self, snapshot: dict[str, Any]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed()
        line = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    def _rotate_if_needed(self) -> None:
        assert self.path is not None
        try:
            if self.path.stat().st_size < self.max_bytes:
                return
        except FileNotFoundError:
            return
        temp = self.path.with_suffix(self.path.suffix + '.tmp')
        with temp.open('w', encoding='utf-8') as handle:
            for snapshot in list(self._operations.values())[-self.history_limit:]:
                handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
        os.replace(temp, self.path)

    def _trim_memory(self) -> None:
        while len(self._operations) > self.history_limit:
            operation_id, snapshot = self._operations.popitem(last=False)
            command_id = snapshot.get('command_id')
            if isinstance(command_id, str) and self._command_index.get(command_id) == operation_id:
                self._command_index.pop(command_id, None)

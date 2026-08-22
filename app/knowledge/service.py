from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.api.errors import BridgeError, ErrorCode

from .store import KnowledgeStore


def _json(value: str | None) -> Any:
    return None if value is None else json.loads(value)


class KnowledgeService:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self.store.initialize()

    def source_list(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT s.source_id, s.platform, s.title, s.source_url,
                          COUNT(m.id) AS message_count, MIN(m.timestamp) AS oldest_timestamp,
                          MAX(m.timestamp) AS newest_timestamp,
                          s.imported_at AS last_imported_timestamp
                   FROM sources s LEFT JOIN messages m ON m.source_fk=s.id
                   GROUP BY s.id ORDER BY s.source_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        source_ids: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query or len(query) > 1000:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "query must contain 1 to 1000 characters")
        if not 1 <= limit <= 100:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "limit must be between 1 and 100")
        start = self._date(date_from, "date_from")
        end = self._date(date_to, "date_to", end_of_day=True)
        if start and end and start > end:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "date_from must not be after date_to")
        filters: list[str] = []
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "query must contain searchable text")
        fts_query = " AND ".join(f'"{term}"' for term in terms)
        values: list[Any] = [fts_query]
        if source_ids is not None:
            if not source_ids or len(source_ids) > 100 or any(not value for value in source_ids):
                raise BridgeError(ErrorCode.INVALID_ARGUMENT, "source_ids must contain 1 to 100 non-empty values")
            filters.append("s.source_id IN (%s)" % ",".join("?" for _ in source_ids))
            values.extend(source_ids)
        if start:
            filters.append("m.timestamp >= ?")
            values.append(start)
        if end:
            filters.append("m.timestamp <= ?")
            values.append(end)
        where = " AND " + " AND ".join(filters) if filters else ""
        values.append(limit)
        try:
            with self.store.connect() as connection:
                rows = connection.execute(
                    f"""SELECT s.source_id, s.platform, m.platform_message_id AS message_id,
                               m.timestamp, a.display_name AS author,
                               a.platform_author_id AS author_id, m.text,
                               snippet(messages_fts, 0, '[', ']', ' … ', 24) AS snippet,
                               m.reply_to_message_id, m.topic_json, m.permalink,
                               bm25(messages_fts) AS rank
                        FROM messages_fts
                        JOIN messages m ON m.id=messages_fts.rowid
                        JOIN sources s ON s.id=m.source_fk
                        LEFT JOIN authors a ON a.id=m.author_fk
                        WHERE messages_fts MATCH ?{where}
                        ORDER BY rank, m.timestamp LIMIT ?""",
                    values,
                ).fetchall()
        except sqlite3.OperationalError as error:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Invalid full-text query") from error
        return [self._search_row(row) for row in rows]

    def message(self, source_id: str, message_id: str, *, neighborhood: int = 2) -> dict[str, Any]:
        if not 0 <= neighborhood <= 10:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "neighborhood must be between 0 and 10")
        with self.store.connect() as connection:
            source_fk = self._source_fk(connection, source_id)
            row = self._message_row(connection, source_fk, message_id)
            if row is None:
                raise BridgeError(ErrorCode.KNOWLEDGE_MESSAGE_NOT_FOUND, "Knowledge message not found")
            message = self._full_row(connection, row)
            platform = connection.execute(
                "SELECT platform FROM sources WHERE id=?", (source_fk,)
            ).fetchone()["platform"]
            message.update(
                {
                    "source_id": source_id,
                    "platform": platform,
                    "reference": f"{platform}:{source_id}:{message_id}",
                }
            )
            parent = None
            if row["reply_to_message_id"]:
                parent_row = self._message_row(connection, source_fk, row["reply_to_message_id"])
                parent = self._summary_row(parent_row) if parent_row else {
                    "message_id": row["reply_to_message_id"], "missing": True
                }
            before = connection.execute(
                """SELECT m.*, a.display_name AS author,
                          a.platform_author_id AS author_id FROM messages m
                   LEFT JOIN authors a ON a.id=m.author_fk
                   WHERE m.source_fk=? AND (m.timestamp < ? OR (m.timestamp=? AND m.id < ?))
                   ORDER BY m.timestamp DESC, m.id DESC LIMIT ?""",
                (source_fk, row["timestamp"], row["timestamp"], row["id"], neighborhood),
            ).fetchall()[::-1]
            after = connection.execute(
                """SELECT m.*, a.display_name AS author,
                          a.platform_author_id AS author_id FROM messages m
                   LEFT JOIN authors a ON a.id=m.author_fk
                   WHERE m.source_fk=? AND (m.timestamp > ? OR (m.timestamp=? AND m.id > ?))
                   ORDER BY m.timestamp, m.id LIMIT ?""",
                (source_fk, row["timestamp"], row["timestamp"], row["id"], neighborhood),
            ).fetchall()
        message["reply_parent"] = parent
        message["neighborhood"] = {
            "before": [self._summary_row(item) for item in before],
            "after": [self._summary_row(item) for item in after],
        }
        return message

    def thread(self, source_id: str, message_id: str, *, limit: int = 50, depth: int = 10) -> dict[str, Any]:
        if not 1 <= limit <= 100 or not 0 <= depth <= 50:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "limit/depth are outside allowed bounds")
        with self.store.connect() as connection:
            source_fk = self._source_fk(connection, source_id)
            platform = connection.execute(
                "SELECT platform FROM sources WHERE id=?", (source_fk,)
            ).fetchone()["platform"]
            root = self._message_row(connection, source_fk, message_id)
            if root is None:
                raise BridgeError(ErrorCode.KNOWLEDGE_MESSAGE_NOT_FOUND, "Knowledge message not found")
            ancestors: list[dict[str, Any]] = []
            seen = {str(root["platform_message_id"])}
            current = root
            for _ in range(depth):
                parent_id = current["reply_to_message_id"]
                if not parent_id or parent_id in seen:
                    break
                seen.add(parent_id)
                parent = self._message_row(connection, source_fk, parent_id)
                if parent is None:
                    ancestors.append({"message_id": parent_id, "missing": True})
                    break
                ancestors.append(self._summary_row(parent))
                current = parent
            descendants: list[dict[str, Any]] = []
            queue = deque([(str(root["platform_message_id"]), 1)])
            while queue and len(descendants) < limit:
                parent_id, level = queue.popleft()
                if level > depth:
                    continue
                replies = connection.execute(
                    """SELECT m.*, a.display_name AS author,
                              a.platform_author_id AS author_id FROM messages m
                       LEFT JOIN authors a ON a.id=m.author_fk
                       WHERE m.source_fk=? AND m.reply_to_message_id=?
                       ORDER BY m.timestamp, m.id LIMIT ?""",
                    (source_fk, parent_id, limit - len(descendants)),
                ).fetchall()
                for reply in replies:
                    reply_id = str(reply["platform_message_id"])
                    if reply_id in seen:
                        continue
                    seen.add(reply_id)
                    item = self._summary_row(reply)
                    item["depth"] = level
                    descendants.append(item)
                    queue.append((reply_id, level + 1))
                    if len(descendants) >= limit:
                        break
            root_message = self._full_row(connection, root)
            root_message.update(
                {
                    "source_id": source_id,
                    "platform": platform,
                    "reference": f"{platform}:{source_id}:{message_id}",
                }
            )
        return {
            "source_id": source_id,
            "topic": _json(root["topic_json"]),
            "ancestors": list(reversed(ancestors)),
            "message": root_message,
            "descendants": descendants,
        }

    @staticmethod
    def _date(value: str | None, label: str, *, end_of_day: bool = False) -> str | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            if len(value) == 10 and end_of_day:
                parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
            return parsed.astimezone(UTC).isoformat()
        except ValueError as error:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"{label} must be an ISO date or timestamp") from error

    @staticmethod
    def _source_fk(connection, source_id: str) -> int:
        row = connection.execute("SELECT id FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if row is None:
            raise BridgeError(ErrorCode.KNOWLEDGE_SOURCE_NOT_FOUND, "Knowledge source not found")
        return row[0]

    @staticmethod
    def _message_row(connection, source_fk: int, message_id: str):
        return connection.execute(
            """SELECT m.*, a.display_name AS author,
                      a.platform_author_id AS author_id FROM messages m
               LEFT JOIN authors a ON a.id=m.author_fk
               WHERE m.source_fk=? AND m.platform_message_id=?""",
            (source_fk, str(message_id)),
        ).fetchone()

    @staticmethod
    def _summary_row(row) -> dict[str, Any]:
        return {
            "message_id": str(row["platform_message_id"]),
            "timestamp": row["timestamp"], "author": row["author"],
            "author_id": row["author_id"], "text": row["text"],
            "reply_to_message_id": row["reply_to_message_id"],
            "topic": _json(row["topic_json"]), "permalink": row["permalink"],
        }

    def _full_row(self, connection, row) -> dict[str, Any]:
        result = self._summary_row(row)
        result.update({
            "message_type": row["message_type"], "edited_timestamp": row["edited_timestamp"],
            "original_text": _json(row["original_text_json"]),
            "metadata": _json(row["metadata_json"]),
            "attachments": [
                {"type": item["attachment_type"], "exported_path": item["exported_path"], "metadata": _json(item["metadata_json"])}
                for item in connection.execute("SELECT * FROM attachments WHERE message_fk=? ORDER BY id", (row["id"],))
            ],
        })
        return result

    @staticmethod
    def _search_row(row) -> dict[str, Any]:
        return {
            "source_id": row["source_id"], "platform": row["platform"],
            "message_id": str(row["message_id"]), "timestamp": row["timestamp"],
            "author": row["author"], "author_id": row["author_id"],
            "text": row["text"], "snippet": row["snippet"],
            "reply_to_message_id": row["reply_to_message_id"],
            "topic": _json(row["topic_json"]), "permalink": row["permalink"],
            "reference": f"{row['platform']}:{row['source_id']}:{row['message_id']}",
        }

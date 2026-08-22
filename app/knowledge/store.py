from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT,
    imported_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    source_fk INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    author_key TEXT NOT NULL,
    platform_author_id TEXT,
    display_name TEXT NOT NULL,
    UNIQUE(source_fk, author_key)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    source_fk INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    platform_message_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    edited_timestamp TEXT,
    author_fk INTEGER REFERENCES authors(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    original_text_json TEXT NOT NULL,
    reply_to_message_id TEXT,
    topic_json TEXT,
    permalink TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_fk, platform_message_id)
);
CREATE INDEX IF NOT EXISTS messages_source_time
    ON messages(source_fk, timestamp, id);
CREATE INDEX IF NOT EXISTS messages_reply
    ON messages(source_fk, reply_to_message_id);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    message_fk INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    attachment_type TEXT NOT NULL,
    exported_path TEXT,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachment_snapshots (
    source_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    storage_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    file_name TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    PRIMARY KEY(source_id, message_id, attachment_id)
);
CREATE TABLE IF NOT EXISTS source_sync_state (
    source_fk INTEGER PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    username TEXT,
    source_kind TEXT NOT NULL,
    oldest_message_id INTEGER,
    newest_message_id INTEGER,
    history_complete INTEGER NOT NULL DEFAULT 0,
    last_sync_at TEXT,
    UNIQUE(provider, entity_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, content='messages', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text)
    VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text)
    VALUES ('delete', old.id, old.text);
    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


class KnowledgeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            os.chmod(self.path, 0o600)
        else:
            os.close(descriptor)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate_attachments(connection)

    @staticmethod
    def _migrate_attachments(connection: sqlite3.Connection) -> None:
        from .attachment_identity import attachment_fields, stable_attachment_id

        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(attachments)")
        }
        additions = {
            "attachment_id": "TEXT",
            "media_type": "TEXT",
            "file_name": "TEXT",
            "declared_size": "INTEGER",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE attachments ADD COLUMN {name} {sql_type}")
        rows = connection.execute(
            """SELECT a.*, m.platform_message_id FROM attachments a
               JOIN messages m ON m.id=a.message_fk
               ORDER BY a.message_fk, a.id"""
        ).fetchall()
        current_message = None
        fallback_index = 0
        for row in rows:
            if row["message_fk"] != current_message:
                current_message = row["message_fk"]
                fallback_index = 0
            metadata = json.loads(row["metadata_json"])
            attachment_id = row["attachment_id"] or stable_attachment_id(
                row["attachment_type"], metadata,
                exported_path=row["exported_path"], fallback_index=fallback_index,
            )
            media_type, file_name, declared_size = attachment_fields(
                row["attachment_type"], metadata, row["exported_path"]
            )
            connection.execute(
                """UPDATE attachments SET attachment_id=?, media_type=COALESCE(media_type, ?),
                       file_name=COALESCE(file_name, ?),
                       declared_size=COALESCE(declared_size, ?) WHERE id=?""",
                (attachment_id, media_type, file_name, declared_size, row["id"]),
            )
            fallback_index += 1
        connection.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS attachments_message_identity
               ON attachments(message_fk, attachment_id)"""
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def replace_attachments(
        connection: sqlite3.Connection,
        message_fk: int,
        attachments: list[dict[str, Any]],
    ) -> None:
        identities = []
        for attachment in attachments:
            identities.append(attachment["attachment_id"])
            connection.execute(
                """INSERT INTO attachments(
                     message_fk, attachment_type, exported_path, metadata_json,
                     attachment_id, media_type, file_name, declared_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(message_fk, attachment_id) DO UPDATE SET
                     attachment_type=excluded.attachment_type,
                     exported_path=excluded.exported_path,
                     metadata_json=excluded.metadata_json,
                     media_type=excluded.media_type,
                     file_name=excluded.file_name,
                     declared_size=excluded.declared_size""",
                (
                    message_fk, attachment["type"], attachment.get("exported_path"),
                    json.dumps(attachment["metadata"], ensure_ascii=False),
                    attachment["attachment_id"], attachment.get("media_type"),
                    attachment.get("file_name"), attachment.get("declared_size"),
                ),
            )
        if identities:
            placeholders = ",".join("?" for _ in identities)
            connection.execute(
                f"DELETE FROM attachments WHERE message_fk=? AND attachment_id NOT IN ({placeholders})",
                (message_fk, *identities),
            )
        else:
            connection.execute("DELETE FROM attachments WHERE message_fk=?", (message_fk,))

from __future__ import annotations

import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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

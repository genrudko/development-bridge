from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.api.errors import BridgeError
from app.settings import load_settings

from .importer import TelegramJsonImporter
from .store import KnowledgeStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a Telegram Desktop JSON export")
    parser.add_argument("input", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--title")
    parser.add_argument("--config", type=Path)
    arguments = parser.parse_args()
    settings = load_settings(arguments.config)
    if settings.knowledge.database_path is None:
        parser.error("knowledge.database_path is not configured")
    try:
        result = TelegramJsonImporter(
            KnowledgeStore(settings.knowledge.database_path.expanduser().resolve())
        ).import_file(
            arguments.input,
            arguments.source_id,
            source_url=arguments.source_url,
            title=arguments.title,
        )
    except BridgeError as error:
        parser.error(error.message)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

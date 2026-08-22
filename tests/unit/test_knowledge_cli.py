from __future__ import annotations

import json
import sys
from pathlib import Path

from app.knowledge.cli import main


FIXTURE = Path(__file__).parents[1] / "fixtures" / "telegram_export.json"


def test_telegram_import_cli_uses_configured_external_database(tmp_path, monkeypatch, capsys):
    database = tmp_path / "knowledge.sqlite3"
    config = tmp_path / "bridge.yaml"
    config.write_text(
        f"version: 1\nknowledge:\n  database_path: {database}\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "development-bridge-import-telegram", str(FIXTURE),
            "--config", str(config), "--source-id", "ad5x",
            "--title", "AD5X Community",
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["inserted"] == 4
    assert database.exists()

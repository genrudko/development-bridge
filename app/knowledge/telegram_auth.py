from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from telethon import TelegramClient

from app.knowledge.telegram import ensure_session_file
from app.settings import load_settings


async def authorize(api_id: int, api_hash: str, session_path: Path, phone: str | None) -> str:
    session_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_session_file(session_path)
    client = TelegramClient(str(session_path), api_id, api_hash)
    try:
        await client.connect()
        await client.start(phone=phone or (lambda: input("Telegram phone: ").strip()))
        account = await client.get_me()
    finally:
        await client.disconnect()
    actual_session_path = Path(client.session.filename)
    os.chmod(actual_session_path, 0o600)
    username = getattr(account, "username", None)
    return f"@{username}" if username else str(account.id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize the Development Bridge Telegram session")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--phone", help="Optional phone number; otherwise prompted interactively")
    arguments = parser.parse_args()
    settings = load_settings(arguments.config)
    telegram = settings.knowledge.telegram
    if telegram.api_id is None or telegram.api_hash is None or telegram.session_path is None:
        parser.error("knowledge.telegram api_id, api_hash, and session_path must be configured")
    account = asyncio.run(
        authorize(
            telegram.api_id,
            telegram.api_hash.get_secret_value(),
            telegram.session_path.expanduser().resolve(),
            arguments.phone,
        )
    )
    print(f"Telegram authorization complete for {account}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

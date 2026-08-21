from __future__ import annotations

import asyncio
import fcntl
import time
from contextlib import asynccontextmanager

from app.api.errors import BridgeError, ErrorCode

from .models import Repository


class RepositoryMutationLock:
    """Serialize repository mutations across services and Bridge processes."""

    def __init__(self, *, timeout_seconds: float = 5) -> None:
        self._timeout_seconds = timeout_seconds
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    @asynccontextmanager
    async def acquire(self, repository: Repository):
        local = self._locks.setdefault(
            (repository.project_id, repository.id), asyncio.Lock()
        )
        async with local:
            directory = repository.root / ".git" / "development-bridge"
            directory.mkdir(parents=True, exist_ok=True)
            lock_file = (directory / "repository.lock").open("a+")
            deadline = time.monotonic() + self._timeout_seconds
            try:
                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise BridgeError(
                                ErrorCode.GIT_COMMAND_FAILED,
                                "Repository mutation lock is busy",
                                retryable=True,
                                details={"repository_id": repository.id},
                            )
                        await asyncio.sleep(0.05)
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()

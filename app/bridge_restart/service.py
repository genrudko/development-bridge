from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from app.api.errors import BridgeError, ErrorCode
from app.jobs import JobService

logger = logging.getLogger(__name__)

RESTART_COMMAND = (
    "/usr/bin/systemd-run",
    "--user",
    "--collect",
    "--unit=development-bridge-self-restart",
    "/usr/bin/sudo",
    "-n",
    "/usr/bin/systemctl",
    "--no-block",
    "restart",
    "development-bridge.service",
)


class BridgeRestartService:
    def __init__(
        self,
        jobs: JobService,
        *,
        delay_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        spawn: Callable[..., Awaitable[object]] = asyncio.create_subprocess_exec,
        create_task: Callable[
            [Awaitable[None]], asyncio.Task[None]
        ] = asyncio.create_task,
    ) -> None:
        self._jobs = jobs
        self._delay_seconds = delay_seconds
        self._sleep = sleep
        self._spawn = spawn
        self._create_task = create_task
        self._tasks: set[asyncio.Task[None]] = set()

    async def schedule(self, checkpoint: Callable[[], Awaitable[None]] | None = None) -> dict[str, object]:
        async def schedule_task() -> dict[str, object]:
            if checkpoint is not None:
                await checkpoint()
            pending_restart = self._restart_after_delay()
            try:
                task = self._create_task(pending_restart)
            except Exception as exc:
                pending_restart.close()
                raise BridgeError(
                    ErrorCode.INTERNAL_ERROR,
                    "Bridge restart could not be scheduled",
                ) from exc
            self._tasks.add(task)
            task.add_done_callback(self._restart_finished)
            return {
                "restart_scheduled": True,
                "service": "development-bridge.service",
                "delay_seconds": self._delay_seconds,
            }

        return await self._jobs.run_when_globally_idle(
            schedule_task, operation_name="bridge_restart"
        )

    async def _restart_after_delay(self) -> None:
        await self._sleep(self._delay_seconds)
        runtime_dir = f"/run/user/{os.getuid()}"
        await self._spawn(
            *RESTART_COMMAND,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                "XDG_RUNTIME_DIR": runtime_dir,
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
            },
        )

    def _restart_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Detached bridge restart process could not be spawned",
                exc_info=(type(error), error, error.__traceback__),
            )

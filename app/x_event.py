from __future__ import annotations

import asyncio
import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

_generation = 0
_message = ""
_claimed: set[int] = set()
_lock = asyncio.Lock()


def _json(payload: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
        },
    )


async def event_state(request: Request):
    return _json({"generation": _generation, "message": _message})


async def claim_event(request: Request):
    try:
        generation = int(request.query_params.get("generation", "0"))
    except ValueError:
        return _json({"claimed": False, "error": "bad_generation"}, 400)
    async with _lock:
        if generation <= 0 or generation != _generation or generation in _claimed:
            return _json({"claimed": False, "generation": _generation})
        _claimed.add(generation)
        return _json({"claimed": True, "generation": generation})


async def trigger_event(request: Request):
    global _generation, _message
    token = request.path_params["token"]
    expected = os.environ.get("X_PROBE_TRIGGER_TOKEN", "")
    if not expected or token != expected:
        return _json({"ok": False}, 404)
    body = await request.json()
    message = str(body.get("message", "")).strip()
    if not message:
        return _json({"ok": False, "error": "message_required"}, 400)
    async with _lock:
        _generation += 1
        _message = message
        _claimed.discard(_generation)
        return _json({"ok": True, "generation": _generation})


def x_event_routes(endpoint: str) -> list[Route]:
    base = endpoint.rsplit("/", 1)[0]
    return [
        Route(base + "/x-event", event_state, methods=["GET"]),
        Route(base + "/x-claim", claim_event, methods=["POST"]),
        Route(base + "/x-trigger/{token}", trigger_event, methods=["POST"]),
    ]

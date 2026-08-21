from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str


def new_request_context() -> RequestContext:
    return RequestContext(request_id=f"req_{uuid4().hex}")


from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from .provider import BridgeOAuthProvider


def approval_route(provider: BridgeOAuthProvider):
    async def approve(request: Request):
        request_id = (
            request.query_params.get("request_id")
            if request.method == "GET"
            else (await request.form()).get("request_id")
        )
        if not isinstance(request_id, str) or provider.pending_authorization(request_id) is None:
            return HTMLResponse("Authorization request is invalid or expired", status_code=400)
        error = ""
        if request.method == "POST":
            password = (await request.form()).get("password")
            redirect = provider.approve(
                request_id, password if isinstance(password, str) else ""
            )
            if redirect is not None:
                return RedirectResponse(redirect, status_code=302)
            error = "<p>Owner verification failed.</p>"
        escaped_request_id = html.escape(request_id, quote=True)
        return HTMLResponse(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Authorize Development Bridge</title></head><body>"
            "<h1>Authorize Development Bridge</h1>"
            f"{error}<form method='post'>"
            f"<input type='hidden' name='request_id' value='{escaped_request_id}'>"
            "<label>Owner password <input type='password' name='password' "
            "autocomplete='current-password' required></label>"
            "<button type='submit'>Authorize</button></form></body></html>",
            headers={"Cache-Control": "no-store"},
        )

    return approve

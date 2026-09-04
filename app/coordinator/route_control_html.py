from __future__ import annotations

import html
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "route_control_result.html"
_TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")

ERROR_CODE_STAGE_MAP = {
    "RETURN_TARGET_MISSING": "Conversation identification",
    "TARGET_PARSE_FAILED": "Target validation",
    "TOKEN_INVALID": "Security token verification",
    "TOKEN_EXPIRED": "Security token verification",
    "TOKEN_REPLAYED": "Candidate registration",
    "PROJECT_MISMATCH": "Project policy check",
    "GENERATION_CHANGED": "Route generation check",
    "CANDIDATE_NOT_READY": "Route binding commit",
    "CANDIDATE_EXPIRED": "Route binding commit",
    "REGISTRY_WRITE_FAILED": "Route binding commit",
    "PENDING_WAKES": "Wake cancellation",
    "WAKE_CANCEL_FAILED": "Wake cancellation",
    "TARGET_PROBE_FAILED": "Target verification",
}


def render_route_control_page(
    *,
    mode: str,
    route_id: str | None = None,
    generation: int | None = None,
    pending_wakes: int | str = 0,
    diagnostic_id: str | None = None,
    stage_name: str | None = None,
    commit_url: str | None = None,
    return_url: str | None = None,
    return_base_url: str | None = None,
) -> str:
    rendered = _TEMPLATE
    safe_route = html.escape(route_id or "")
    safe_diag = html.escape(diagnostic_id or "")

    if mode == "pending":
        status_icon = "⏳"
        status_title = "Completing route binding..."
        status_msg = f"Validating and finalizing route binding for <code>{safe_route}</code>."
        meta_rows = [
            f'<div class="meta-row"><span class="meta-label">Route:</span> <span class="meta-value"><code>{safe_route}</code></span></div>',
        ]
        if diagnostic_id:
            meta_rows.append(
                f'<div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>{safe_diag}</code></span></div>'
            )
        meta_summary = f'<div id="meta-summary" class="meta-summary">{"".join(meta_rows)}</div>'
        actions = (
            f'<form id="commit-form" method="POST" action="{html.escape(commit_url or "")}">'
            '<button id="commit-btn" type="submit" class="btn btn-primary">Complete binding</button>'
            '</form>'
        )
        safe_return_base = html.escape(return_base_url or "")
        auto_commit_script = f"""<script>
(async function() {{
  function escapeHtml(str) {{
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }}
  const form = document.getElementById('commit-form');
  const commitBtn = document.getElementById('commit-btn');
  const statusIcon = document.getElementById('status-icon');
  const statusTitle = document.getElementById('status-title');
  const statusMsg = document.getElementById('status-msg');
  const metaSummary = document.getElementById('meta-summary');
  const actionsDiv = document.getElementById('actions');

  if (!form) return;
  try {{
    if (commitBtn) commitBtn.disabled = true;
    const res = await fetch(form.action, {{
      method: 'POST',
      headers: {{ 'Accept': 'application/json' }}
    }});
    const data = await res.json();
    if (res.ok && data.ok) {{
      if (data.state === 'already_bound') {{
        statusIcon.textContent = '⚠️';
        statusTitle.textContent = 'Chat already linked';
        statusMsg.innerHTML = 'This ChatGPT conversation is already the active binding for route <code>' + escapeHtml(data.route_id) + '</code>.';
      }} else {{
        statusIcon.textContent = '✅';
        statusTitle.textContent = 'Chat linked';
        statusMsg.innerHTML = 'ChatGPT securely identified this conversation and Bridge accepted it for route <code>' + escapeHtml(data.route_id) + '</code>.';
      }}
      metaSummary.innerHTML = `
        <div class="meta-row"><span class="meta-label">Generation:</span> <span class="meta-value">${{escapeHtml(String(data.generation))}}</span></div>
        <div class="meta-row"><span class="meta-label">Pending wake:</span> <span class="meta-value">${{escapeHtml(String(data.pending_wakes ?? 0))}}</span></div>
        <div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>${{escapeHtml(data.diagnostic_id || '')}}</code></span></div>
      `;
      const returnUrl = '{safe_return_base}/' + encodeURIComponent(data.diagnostic_id || '');
      actionsDiv.innerHTML = `<a href="${{returnUrl}}" class="btn btn-primary">Return to ChatGPT</a>`;
    }} else {{
      statusIcon.textContent = '❌';
      statusTitle.textContent = 'Chat could not be linked';
      statusMsg.innerHTML = 'Failed at: Route binding commit<br><span class="subtext">Existing binding was not changed.</span>';
      if (data && data.diagnostic_id) {{
        metaSummary.innerHTML = `<div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>${{escapeHtml(data.diagnostic_id)}}</code></span></div>`;
        const returnUrl = '{safe_return_base}/' + encodeURIComponent(data.diagnostic_id);
        actionsDiv.innerHTML = `<a href="${{returnUrl}}" class="btn btn-secondary">Return to ChatGPT</a>`;
      }} else {{
        metaSummary.innerHTML = '';
        actionsDiv.innerHTML = '';
      }}
    }}
  }} catch (e) {{
    if (commitBtn) commitBtn.disabled = false;
  }}
}})();
</script>"""

    elif mode == "success":
        status_icon = "✅"
        status_title = "Chat linked"
        status_msg = f"ChatGPT securely identified this conversation and Bridge accepted it for route <code>{safe_route}</code>."
        meta_rows = [
            f'<div class="meta-row"><span class="meta-label">Generation:</span> <span class="meta-value">{int(generation or 0)}</span></div>',
            f'<div class="meta-row"><span class="meta-label">Pending wake:</span> <span class="meta-value">{html.escape(str(pending_wakes))}</span></div>',
        ]
        if diagnostic_id:
            meta_rows.append(
                f'<div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>{safe_diag}</code></span></div>'
            )
        meta_summary = f'<div id="meta-summary" class="meta-summary">{"".join(meta_rows)}</div>'
        actions = f'<a href="{html.escape(return_url or "#")}" class="btn btn-primary">Return to ChatGPT</a>' if return_url else ""
        auto_commit_script = ""

    elif mode == "warning":
        status_icon = "⚠️"
        status_title = "Chat already linked"
        status_msg = f"This ChatGPT conversation is already the active binding for route <code>{safe_route}</code>."
        meta_rows = [
            f'<div class="meta-row"><span class="meta-label">Generation:</span> <span class="meta-value">{int(generation or 0)}</span></div>',
            f'<div class="meta-row"><span class="meta-label">Pending wake:</span> <span class="meta-value">{html.escape(str(pending_wakes))}</span></div>',
        ]
        if diagnostic_id:
            meta_rows.append(
                f'<div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>{safe_diag}</code></span></div>'
            )
        meta_summary = f'<div id="meta-summary" class="meta-summary">{"".join(meta_rows)}</div>'
        actions = f'<a href="{html.escape(return_url or "#")}" class="btn btn-primary">Return to ChatGPT</a>' if return_url else ""
        auto_commit_script = ""

    else:  # failed
        status_icon = "❌"
        status_title = "Chat could not be linked"
        safe_stage = html.escape(stage_name or "Conversation identification")
        status_msg = f"Failed at: {safe_stage}<br><span class=\"subtext\">Existing binding was not changed.</span>"
        meta_rows = []
        if diagnostic_id:
            meta_rows.append(
                f'<div class="meta-row"><span class="meta-label">Diagnostic code:</span> <span class="meta-value"><code>{safe_diag}</code></span></div>'
            )
        meta_summary = f'<div id="meta-summary" class="meta-summary">{"".join(meta_rows)}</div>' if meta_rows else ""
        actions = f'<a href="{html.escape(return_url or "#")}" class="btn btn-secondary">Return to ChatGPT</a>' if return_url else ""
        auto_commit_script = ""

    rendered = rendered.replace("__STATUS_ICON__", status_icon)
    rendered = rendered.replace("__STATUS_TITLE__", status_title)
    rendered = rendered.replace("__STATUS_MESSAGE__", status_msg)
    rendered = rendered.replace("__META_SUMMARY__", meta_summary)
    rendered = rendered.replace("__ACTIONS__", actions)
    rendered = rendered.replace("__AUTO_COMMIT_SCRIPT__", auto_commit_script)
    return rendered

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import cairosvg
import fitz
import httpx
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ImageContent
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

Backend = Literal['drawio', 'iec', 'power', 'kicad', 'spice']
BACKENDS: dict[str, dict[str, Any]] = {
    'drawio': {'url': 'http://127.0.0.1:8792/mcp', 'purpose': 'RF/EMC/PCB/general engineering draw.io helpers'},
    'iec': {'url': 'http://127.0.0.1:8793/mcp', 'purpose': 'IEC 60617 industrial electrical/control schematics'},
    'power': {'url': 'http://127.0.0.1:8794/mcp', 'purpose': 'power-system models, load flow, N-1, SLD/network diagrams'},
    'kicad': {'url': 'http://127.0.0.1:8795/mcp', 'purpose': 'real KiCad electronic schematics, libraries, ERC/export'},
    'spice': {'url': 'http://127.0.0.1:8796/mcp', 'purpose': 'ngspice circuit simulation and waveform analysis'},
}
PREFIX = Path('/home/eodadmin/.config/engineering-mcp/capability-prefix').read_text().strip()
PUBLIC_BASE = f'https://mcp.vigilante.website/{PREFIX}/hub'
ARTIFACT_DIR = Path('/home/eodadmin/mcp-workspaces/hub/artifacts').resolve()
ARTIFACT_APP_URI = 'ui://engineering/artifact-viewer.html'
ARTIFACT_APP_V2_URI = 'ui://engineering/artifact-viewer-v2.html'
ARTIFACT_APP_HTML = Path('/home/eodadmin/services/engineering-mcp/hub/artifact-app.html')


class ArtifactViewResult(BaseModel):
    download_url: str
    preview_url: str | None = None
    filename: str
    mime_type: str

ALLOWED_LOCAL_ROOTS = [
    Path('/home/eodadmin/mcp-workspaces').resolve(),
    Path('/home/eodadmin/mcp-kicad').resolve(),
]
TOOL_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
BACKEND_SESSIONS: dict[str, str] = {}
BACKEND_UNITS = {
    'drawio': 'engineering-drawio.service',
    'iec': 'engineering-schematika.service',
    'power': 'engineering-power.service',
    'kicad': 'engineering-kicad.service',
    'spice': 'engineering-spice.service',
}
BACKEND_IDLE_SECONDS = 180.0
BACKEND_IDLE_TASKS: dict[str, asyncio.Task] = {}
BACKEND_CONTROL_LOCKS = {name: asyncio.Lock() for name in BACKEND_UNITS}
RPC_ID = 0
CACHE_TTL = 600.0
MAX_ARTIFACT_BYTES = 40 * 1024 * 1024

mcp = FastMCP(
    'Engineering Bridge',
    instructions=(
        'Compact engineering facade over draw.io-engineering, Schematika IEC, PyPowsybl, '
        'MCP-KiCad and ngspice. Use search_tools and tool_schema before call_tool instead of '
        'guessing backend arguments. call_tool automatically surfaces SVG/PNG/PDF artifacts '
        'as an inline image preview when possible and preserves a download URL for the original.'
    ),
    host='127.0.0.1',
    port=8797,
    stateless_http=True,
    json_response=True,
)


def _next_id() -> int:
    global RPC_ID
    RPC_ID += 1
    return RPC_ID


def _parse_response(text: str, request_id: int) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith('data: '):
            try:
                candidates.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    if not candidates:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                candidates.append(obj)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'backend returned non-MCP response: {text[:500]!r}') from exc
    for obj in candidates:
        if obj.get('id') == request_id:
            return obj
    if candidates:
        return candidates[-1]
    raise RuntimeError('empty MCP response')


async def _user_systemctl(action: str, backend: str) -> None:
    unit = BACKEND_UNITS[backend]
    runtime = f'/run/user/{os.getuid()}'
    env = os.environ.copy()
    env['XDG_RUNTIME_DIR'] = runtime
    env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path={runtime}/bus'
    proc = await asyncio.create_subprocess_exec(
        '/usr/bin/systemctl', '--user', action, unit,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = (stderr or stdout).decode('utf-8', 'replace')[:1000]
        raise RuntimeError(f'{action} {unit} failed: {detail}')


def _cancel_backend_idle_stop(backend: str) -> None:
    task = BACKEND_IDLE_TASKS.pop(backend, None)
    if task is not None and not task.done():
        task.cancel()


async def _idle_stop_backend(backend: str) -> None:
    try:
        await asyncio.sleep(BACKEND_IDLE_SECONDS)
        BACKEND_SESSIONS.pop(backend, None)
        await _user_systemctl('stop', backend)
    except asyncio.CancelledError:
        return
    finally:
        current = BACKEND_IDLE_TASKS.get(backend)
        if current is asyncio.current_task():
            BACKEND_IDLE_TASKS.pop(backend, None)


def _schedule_backend_idle_stop(backend: str) -> None:
    _cancel_backend_idle_stop(backend)
    BACKEND_IDLE_TASKS[backend] = asyncio.create_task(_idle_stop_backend(backend))


async def _ensure_backend_started(backend: str) -> None:
    async with BACKEND_CONTROL_LOCKS[backend]:
        await _user_systemctl('start', backend)


async def _backend_post(
    backend: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> httpx.Response:
    _cancel_backend_idle_stop(backend)

    async def issue() -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=4.0), trust_env=False
        ) as client:
            return await client.post(BACKENDS[backend]['url'], headers=headers, json=body)

    try:
        try:
            return await issue()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # Connection never reached the backend, so retrying after start is safe
            # even for mutation tools. Read/write timeouts are deliberately not retried.
            await _ensure_backend_started(backend)
            last_error: Exception | None = None
            for delay in (0.15, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0):
                await asyncio.sleep(delay)
                try:
                    return await issue()
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_error = exc
            raise RuntimeError(f'{backend} did not become ready after systemd start') from last_error
    finally:
        _schedule_backend_idle_stop(backend)


async def _post(backend: str, method: str, params: dict[str, Any], session: str | None = None,
                timeout: float = 180.0) -> tuple[dict[str, Any], str | None]:
    rid = _next_id()
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'MCP-Protocol-Version': '2025-11-25',
        'User-Agent': 'engineering-bridge/1.0',
    }
    if session:
        headers['Mcp-Session-Id'] = session
    body = {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}
    response = await _backend_post(backend, headers=headers, body=body, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f'{backend} HTTP {response.status_code}: {response.text[:1000]}')
    obj = _parse_response(response.text, rid)
    if 'error' in obj:
        raise RuntimeError(f"{backend} MCP error: {obj['error']}")
    return obj, response.headers.get('mcp-session-id')


async def _notify(backend: str, method: str, params: dict[str, Any], session: str) -> None:
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'MCP-Protocol-Version': '2025-11-25',
        'Mcp-Session-Id': session,
        'User-Agent': 'engineering-bridge/1.0',
    }
    body = {'jsonrpc': '2.0', 'method': method, 'params': params}
    response = await _backend_post(backend, headers=headers, body=body, timeout=30.0)
    if response.status_code >= 400:
        raise RuntimeError(f'{backend} HTTP {response.status_code}: {response.text[:1000]}')


async def _ensure_backend_session(backend: str, force: bool = False) -> str:
    if not force and backend in BACKEND_SESSIONS:
        return BACKEND_SESSIONS[backend]
    _, sess = await _post(backend, 'initialize', {
        'protocolVersion': '2025-11-25',
        'capabilities': {},
        'clientInfo': {'name': 'engineering-bridge', 'version': '1.0'},
    })
    if not sess:
        raise RuntimeError(f'{backend} did not return Mcp-Session-Id')
    BACKEND_SESSIONS[backend] = sess
    await _notify(backend, 'notifications/initialized', {}, sess)
    return sess


async def _session_request(backend: str, method: str, params: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
    sess = await _ensure_backend_session(backend)
    try:
        obj, _ = await _post(backend, method, params, sess, timeout=timeout)
    except RuntimeError as exc:
        text = str(exc).lower()
        if 'session' not in text and 'http 400' not in text:
            raise
        BACKEND_SESSIONS.pop(backend, None)
        sess = await _ensure_backend_session(backend, force=True)
        obj, _ = await _post(backend, method, params, sess, timeout=timeout)
    return obj


async def _list_tools(backend: str, force: bool = False) -> list[dict[str, Any]]:
    cached = TOOL_CACHE.get(backend)
    if cached and not force and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]
    obj = await _session_request(backend, 'tools/list', {})
    tools = obj.get('result', {}).get('tools', [])
    TOOL_CACHE[backend] = (time.monotonic(), tools)
    return tools


async def _call_backend(backend: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    obj = await _session_request(backend, 'tools/call', {'name': tool_name, 'arguments': arguments})
    return obj.get('result', {})

def _content_text(result: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in result.get('content', []) or []:
        if isinstance(block, dict) and block.get('type') == 'text':
            parts.append(str(block.get('text', '')))
    structured = result.get('structuredContent') or result.get('structured_content')
    if structured is not None:
        try:
            parts.append(json.dumps(structured, ensure_ascii=False, indent=2))
        except TypeError:
            parts.append(str(structured))
    return '\n'.join(p for p in parts if p)


def _allowed_local(path: Path) -> bool:
    p = path.resolve()
    return any(p == root or root in p.parents for root in ALLOWED_LOCAL_ROOTS)


def _find_artifact_sources(text: str) -> list[str]:
    found: list[str] = []
    url_re = re.compile(r'https://mcp\.vigilante\.website/' + re.escape(PREFIX) + r'/[^\s\]\)\}\>"\']+\.(?:svg|png|jpg|jpeg|webp|pdf)(?:\?[^\s\]\)\}\>"\']*)?', re.I)
    path_re = re.compile(r'(/home/eodadmin/[^\s\]\)\}\>"\']+\.(?:svg|png|jpg|jpeg|webp|pdf))', re.I)
    for m in url_re.finditer(text):
        found.append(m.group(0))
    for m in path_re.finditer(text):
        found.append(m.group(1))
    # Stable de-duplication
    return list(dict.fromkeys(found))


async def _read_source(source: str) -> tuple[bytes, str]:
    if source.startswith('https://'):
        parsed = urlparse(source)
        allowed_prefix = f'/{PREFIX}/'
        if parsed.hostname != 'mcp.vigilante.website' or not parsed.path.startswith(allowed_prefix):
            raise ValueError('remote artifact URL is outside the engineering capability prefix')
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, trust_env=False) as client:
            r = await client.get(source)
        r.raise_for_status()
        data = r.content
        suffix = Path(parsed.path).suffix.lower()
        if not suffix:
            ctype = r.headers.get('content-type', '').split(';', 1)[0]
            suffix = {'image/svg+xml': '.svg', 'image/png': '.png', 'image/jpeg': '.jpg', 'application/pdf': '.pdf'}.get(ctype, '.bin')
    else:
        p = Path(source).expanduser().resolve()
        if not _allowed_local(p):
            raise ValueError('local artifact path is outside engineering workspaces')
        if not p.is_file():
            raise FileNotFoundError(source)
        data = p.read_bytes()
        suffix = p.suffix.lower()
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f'artifact too large: {len(data)} bytes')
    return data, suffix


async def _stage_artifact(source: str) -> dict[str, str | None]:
    data, suffix = await _read_source(source)
    token = secrets.token_urlsafe(18).replace('-', '_')
    original = ARTIFACT_DIR / f'{token}{suffix}'
    original.write_bytes(data)
    preview: Path | None = None
    try:
        if suffix == '.svg':
            preview = ARTIFACT_DIR / f'{token}.preview.png'
            cairosvg.svg2png(bytestring=data, write_to=str(preview), output_width=1800)
        elif suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
            preview = original
        elif suffix == '.pdf':
            doc = fitz.open(stream=data, filetype='pdf')
            if doc.page_count:
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                preview = ARTIFACT_DIR / f'{token}.preview.png'
                pix.save(str(preview))
            doc.close()
    except Exception:
        preview = None
    preview_url = f'{PUBLIC_BASE}/artifacts/{preview.name}' if preview else None
    mime_type = mimetypes.guess_type(original.name)[0] or 'application/octet-stream'
    return {
        'original_path': str(original),
        'preview_path': str(preview) if preview else None,
        'download_url': f'{PUBLIC_BASE}/artifacts/{original.name}',
        'preview_url': preview_url,
        'filename': original.name,
        'mime_type': mime_type,
    }


async def _auto_kicad_preview(backend: str, text: str) -> list[str]:
    if backend != 'kicad':
        return []
    sch_paths = list(dict.fromkeys(re.findall(r'(/home/eodadmin/[^\s\]\)\}\>"\']+\.kicad_sch)', text)))
    out: list[str] = []
    for path in sch_paths[:2]:
        try:
            result = await _call_backend('kicad', 'export_schematic_image', {'schematic_path': path, 'format': 'svg'})
            out_text = _content_text(result)
            out.extend(_find_artifact_sources(out_text))
        except Exception as exc:
            out.append(f'ERROR:{exc}')
    return out


@mcp.tool()
def capabilities() -> dict[str, Any]:
    """Show the engineering backends and the compact workflow exposed by this Bridge."""
    return {
        'backends': {name: cfg['purpose'] for name, cfg in BACKENDS.items()},
        'workflow': 'search_tools -> tool_schema -> call_tool',
        'rendering': 'call_tool auto-detects graphical artifacts; show_artifact can display one explicitly',
        'note': 'For free-form wiring/general draw.io schematics, the dedicated Draw.io MCP App remains the richest inline editor.',
    }


@mcp.tool()
async def search_tools(query: str, backend: str = 'all', limit: int = 12) -> list[dict[str, Any]]:
    """Search backend MCP tools by intent without loading 141 tool schemas into the host. backend: all/drawio/iec/power/kicad/spice."""
    if backend != 'all' and backend not in BACKENDS:
        raise ValueError(f'unknown backend {backend!r}')
    selected = list(BACKENDS) if backend == 'all' else [backend]
    terms = [t for t in re.split(r'\W+', query.lower()) if t]
    hits: list[tuple[int, dict[str, Any]]] = []
    for b in selected:
        for tool in await _list_tools(b):
            name = str(tool.get('name', ''))
            desc = str(tool.get('description', ''))
            hay = (name + ' ' + desc).lower()
            score = 0
            if query.lower() in name.lower(): score += 20
            if query.lower() in hay: score += 10
            for term in terms:
                if term in name.lower(): score += 6
                if term in desc.lower(): score += 2
            if score:
                schema = tool.get('inputSchema', {}) or {}
                hits.append((score, {
                    'backend': b,
                    'tool': name,
                    'description': desc[:700],
                    'required': schema.get('required', []),
                }))
    hits.sort(key=lambda x: (-x[0], x[1]['backend'], x[1]['tool']))
    return [h for _, h in hits[:max(1, min(limit, 30))]]


@mcp.tool()
async def tool_schema(backend: Backend, tool_name: str) -> dict[str, Any]:
    """Return the exact backend tool description and JSON input schema before execution."""
    for tool in await _list_tools(backend):
        if tool.get('name') == tool_name:
            return {'backend': backend, 'tool': tool_name, 'description': tool.get('description', ''), 'inputSchema': tool.get('inputSchema', {})}
    raise ValueError(f'{backend} tool not found: {tool_name}')


@mcp.tool()
async def call_tool(backend: Backend, tool_name: str, arguments: dict[str, Any], max_text_chars: int = 24000):
    """Execute one discovered backend tool. Graphical SVG/PNG/PDF results are automatically previewed inline and get a download URL."""
    # Fail fast on typos and avoid arbitrary hidden backend calls.
    known = {t.get('name') for t in await _list_tools(backend)}
    if tool_name not in known:
        raise ValueError(f'{backend} tool not found: {tool_name}; use search_tools first')
    result = await _call_backend(backend, tool_name, arguments)
    full_text = _content_text(result)
    blocks: list[Any] = []
    clipped = full_text
    cap = max(1000, min(max_text_chars, 60000))
    if len(clipped) > cap:
        clipped = clipped[:cap] + f'\n...[truncated {len(full_text)-cap} chars by Engineering Bridge]'
    if clipped:
        blocks.append(clipped)

    # Preserve native backend images.
    for block in result.get('content', []) or []:
        if isinstance(block, dict) and block.get('type') == 'image' and block.get('data'):
            blocks.append(ImageContent(type='image', data=block['data'], mimeType=block.get('mimeType') or block.get('mime_type') or 'image/png'))

    sources = _find_artifact_sources(full_text)
    for extra in await _auto_kicad_preview(backend, full_text):
        if not extra.startswith('ERROR:'):
            sources.append(extra)
        else:
            blocks.append('KiCad auto-preview warning: ' + extra[6:])
    sources = list(dict.fromkeys(sources))[:4]
    for source in sources:
        try:
            staged = await _stage_artifact(source)
            blocks.append(f"Artifact: {staged['download_url']} (original: {source})")
            if staged['preview_path']:
                blocks.append(Image(path=staged['preview_path']))
        except Exception as exc:
            blocks.append(f'Artifact preview warning for {source}: {exc}')
    if not blocks:
        blocks.append(json.dumps(result, ensure_ascii=False)[:cap])
    return blocks


@mcp.tool(
    meta={
        'ui': {'resourceUri': ARTIFACT_APP_URI},
        'ui/resourceUri': ARTIFACT_APP_URI,
        'openai/toolInvocation/invoking': 'Preparing engineering schematic...',
        'openai/toolInvocation/invoked': 'Engineering schematic ready.',
    },
    structured_output=True,
)
async def show_artifact(source: str) -> ArtifactViewResult:
    """Display an engineering SVG/PNG/JPEG/PDF in an inline MCP App card with download control."""
    staged = await _stage_artifact(source)
    return ArtifactViewResult(
        download_url=str(staged['download_url']),
        preview_url=str(staged['preview_url']) if staged.get('preview_url') else None,
        filename=str(staged['filename']),
        mime_type=str(staged['mime_type']),
    )


@mcp.resource(
    ARTIFACT_APP_URI,
    name='Engineering Artifact Viewer',
    mime_type='text/html;profile=mcp-app',
    meta={
        'ui': {
            'domain': 'https://mcp.vigilante.website',
            'csp': {
                'resourceDomains': ['https://mcp.vigilante.website'],
                'connectDomains': ['https://mcp.vigilante.website'],
            },
        },
    },
)
def engineering_artifact_viewer() -> str:
    return ARTIFACT_APP_HTML.read_text(encoding='utf-8')


@mcp.tool(
    name='display_artifact',
    title='Display Engineering Artifact',
    meta={
        'ui': {'resourceUri': ARTIFACT_APP_V2_URI},
        'ui/resourceUri': ARTIFACT_APP_V2_URI,
        'openai/toolInvocation/invoking': 'Preparing engineering schematic...',
        'openai/toolInvocation/invoked': 'Engineering schematic ready.',
    },
)
async def display_artifact(source: str) -> str:
    """Display an engineering SVG/PNG/JPEG/PDF in an inline MCP App card with a download button."""
    staged = await _stage_artifact(source)
    payload = {
        'download_url': str(staged['download_url']),
        'preview_url': str(staged['preview_url']) if staged.get('preview_url') else None,
        'filename': str(staged['filename']),
        'mime_type': str(staged['mime_type']),
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.resource(
    ARTIFACT_APP_V2_URI,
    name='Engineering Artifact Viewer v2',
    mime_type='text/html;profile=mcp-app',
    meta={
        'ui': {
            'csp': {
                'resourceDomains': ['https://mcp.vigilante.website'],
                'connectDomains': ['https://mcp.vigilante.website'],
            },
        },
    },
)
def engineering_artifact_viewer_v2() -> str:
    return ARTIFACT_APP_HTML.read_text(encoding='utf-8')


@mcp.custom_route('/healthz', methods=['GET'], include_in_schema=False)
async def healthz(_: Request):
    return JSONResponse({'status': 'ok', 'backends': list(BACKENDS)})


@mcp.custom_route('/artifacts/{name}', methods=['GET'], include_in_schema=False)
async def artifact_download(request: Request):
    name = request.path_params['name']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        return PlainTextResponse('invalid artifact name', status_code=400)
    path = (ARTIFACT_DIR / name).resolve()
    if path.parent != ARTIFACT_DIR or not path.is_file():
        return PlainTextResponse('not found', status_code=404)
    return FileResponse(path, filename=name)


if __name__ == '__main__':
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    mcp.run(transport='streamable-http')

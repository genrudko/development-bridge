import fs from 'node:fs';

const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i += 2) args[argv[i]] = argv[i + 1];
const endpoint = String(args['--browser-endpoint'] || '').replace(/\/$/, '');
const marker = String(args['--marker'] || '');
const routeUrl = String(args['--route-url'] || '');
const output = String(args['--output'] || '');
const allowProjectChange = String(args['--allow-project-change'] || '0') === '1';
const timeoutMs = Math.max(5000, Math.min(Number(args['--timeout-ms'] || 45000), 90000));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const write = (payload) => fs.writeFileSync(output, JSON.stringify(payload), 'utf8');

function conversationIdFromUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'chatgpt.com') return null;
    const parts = url.pathname.split('/').filter(Boolean);
    const index = parts.lastIndexOf('c');
    if (index < 0 || index !== parts.length - 2) return null;
    return parts[index + 1] || null;
  } catch (_) {
    return null;
  }
}

function projectIdentityFromUrl(value) {
  try {
    const url = new URL(value);
    const parts = url.pathname.split('/').filter(Boolean);
    const index = parts.indexOf('g');
    if (index < 0 || index + 1 >= parts.length) return null;
    const context = parts[index + 1];
    if (!context.startsWith('g-p-')) return null;
    const match = context.match(/^(g-p-[0-9a-fA-F]{32})(?:-|$)/);
    return (match ? match[1] : context).toLowerCase();
  } catch (_) {
    return null;
  }
}

function canonicalObservedRoute(value) {
  const url = new URL(value);
  url.search = '';
  url.hash = '';
  return url.toString().replace(/\/$/, '');
}

async function main() {
  if (!endpoint || !/^DBRIDGE_ROUTE_BIND_[A-Za-z0-9_-]{20,120}$/.test(marker) || !routeUrl || !output) throw new Error('invalid-arguments');
  const expectedProject = projectIdentityFromUrl(routeUrl);
  if (!expectedProject && !allowProjectChange) throw new Error('route-url-has-no-project');

  const pages = await (await fetch(endpoint + '/json/list')).json();
  const page = pages.find((x) => x.type === 'page' && String(x.url || '').includes('chatgpt.com')) || pages.find((x) => x.type === 'page');
  if (!page?.webSocketDebuggerUrl) throw new Error('chatgpt-page-unavailable');
  if (typeof globalThis.WebSocket !== 'function') throw new Error('node-websocket-unavailable');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('websocket-open-timeout')), 5000);
    ws.onopen = () => { clearTimeout(timer); resolve(); };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('websocket-open-failed')); };
  });

  let id = 0;
  const pending = new Map();
  const rejectPending = (reason) => {
    for (const [, item] of pending) {
      clearTimeout(item.timer);
      item.reject(new Error(reason));
    }
    pending.clear();
  };
  ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (_) { return; }
    if (!msg.id || !pending.has(msg.id)) return;
    const item = pending.get(msg.id);
    pending.delete(msg.id);
    clearTimeout(item.timer);
    if (msg.error) item.reject(new Error(`cdp-${item.method}-error`));
    else item.resolve(msg);
  };
  ws.onerror = () => rejectPending('websocket-error');
  ws.onclose = () => rejectPending('websocket-closed');

  const cmd = (method, params = {}, commandTimeoutMs = 5000) => new Promise((resolve, reject) => {
    const requestId = ++id;
    const timer = setTimeout(() => {
      pending.delete(requestId);
      reject(new Error(`command-timeout:${method}`));
    }, commandTimeoutMs);
    pending.set(requestId, {resolve, reject, timer, method});
    ws.send(JSON.stringify({id: requestId, method, params}));
  });
  const evaluate = async (expression) => {
    const response = await cmd('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    return response?.result?.result?.value;
  };
  const deadline = Date.now() + timeoutMs;
  const waitUntil = async (probe, delay = 250) => {
    while (Date.now() < deadline) {
      const value = await probe();
      if (value) return value;
      await sleep(delay);
    }
    return null;
  };

  try {
    await cmd('Page.enable');
    await cmd('Runtime.enable');
    await cmd('Page.navigate', {url: 'https://chatgpt.com/'});
    const homeReady = await waitUntil(() => evaluate(`(() => {
      const body = document.body?.innerText || '';
      if (/log in|sign up|welcome to chatgpt/i.test(body)) return {state:'login'};
      const ready = location.hostname === 'chatgpt.com' && ['interactive','complete'].includes(document.readyState);
      return ready ? {state:'ready'} : null;
    })()`));
    if (!homeReady) { write({found:false, detail:'ChatGPT home did not become ready before discovery timeout'}); return; }
    if (homeReady.state === 'login') { write({found:false, owner_input_required:true, detail:'ChatGPT login is required'}); return; }

    const searchOpened = await waitUntil(async () => {
      const state = await evaluate(`(() => {
        const input = document.getElementById('global-search-modal-input');
        if (input) return 'input';
        const button = [...document.querySelectorAll('button')].find((node) => node.getAttribute('aria-label') === 'Search');
        if (!button) return null;
        button.click();
        return 'clicked';
      })()`);
      return state === 'input' ? true : null;
    });
    if (!searchOpened) { write({found:false, detail:'ChatGPT global search did not open before discovery timeout'}); return; }

    const querySet = await evaluate(`(() => {
      const input = document.getElementById('global-search-modal-input');
      if (!input) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(input, ${JSON.stringify(marker)});
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.dispatchEvent(new Event('change', {bubbles:true}));
      input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
      return true;
    })()`);
    if (!querySet) { write({found:false, detail:'ChatGPT global search input disappeared'}); return; }

    let lastCount = 0;
    let matches = null;
    while (Date.now() < deadline) {
      matches = await evaluate(`(() => {
        const marker = ${JSON.stringify(marker)};
        const anchors = [...document.querySelectorAll('[data-testid="global-search-results-scroller"] ol a[href*="/c/"]')];
        const rows = anchors.map((a) => ({href:a.href, text:a.innerText || ''})).filter((row) => row.text.includes(marker));
        const byId = new Map();
        for (const row of rows) {
          try {
            const parts = new URL(row.href).pathname.split('/').filter(Boolean);
            const i = parts.lastIndexOf('c');
            if (i >= 0 && i === parts.length - 2) byId.set(parts[i + 1], row);
          } catch (_) {}
        }
        return [...byId.entries()].map(([conversation_id,row]) => ({conversation_id, href:row.href}));
      })()`);
      lastCount = Array.isArray(matches) ? matches.length : 0;
      if (lastCount > 1) { write({found:false, match_count:lastCount, detail:`Expected exactly one marker match; found ${lastCount}`}); return; }
      if (lastCount === 1) break;
      await sleep(500);
    }
    if (!Array.isArray(matches) || matches.length !== 1) { write({found:false, match_count:lastCount, detail:'Marker was not indexed before discovery timeout'}); return; }

    const conversationId = matches[0].conversation_id;
    const observedSearchHref = String(matches[0].href || '');
    if (conversationIdFromUrl(observedSearchHref) !== conversationId) { write({found:false, match_count:1, detail:'Search result conversation identity is invalid'}); return; }
    const markerMatchClicked = await evaluate(`(() => {
      const marker = ${JSON.stringify(marker)};
      const conversationId = ${JSON.stringify(conversationId)};
      for (const anchor of document.querySelectorAll('[data-testid="global-search-results-scroller"] ol a[href*="/c/"]')) {
        try {
          if (!(anchor.innerText || '').includes(marker)) continue;
          const parts = new URL(anchor.href).pathname.split('/').filter(Boolean);
          const i = parts.lastIndexOf('c');
          if (i < 0 || i !== parts.length - 2 || parts[i + 1] !== conversationId) continue;
          anchor.click();
          return true;
        } catch (_) {}
      }
      return false;
    })()`);
    if (!markerMatchClicked) { write({found:false, match_count:1, marker_verified:false, detail:'Exact marker search result disappeared before navigation'}); return; }
    const markerNavigated = await waitUntil(() => evaluate(`(() => {
      const parts = location.pathname.split('/').filter(Boolean);
      const i = parts.lastIndexOf('c');
      const onConversation = i >= 0 && i === parts.length - 2 && parts[i + 1] === ${JSON.stringify(conversationId)};
      return onConversation && ['interactive','complete'].includes(document.readyState);
    })()`), 350);
    if (!markerNavigated) { write({found:false, match_count:1, marker_verified:false, detail:'Marker result did not navigate to the indexed conversation'}); return; }


    if (allowProjectChange) {
      const currentUrl = String(await evaluate('location.href') || '');
      if (conversationIdFromUrl(currentUrl) !== conversationId) { write({found:false, match_count:1, marker_verified:true, detail:'Browser left the marker-verified conversation before authorized cross-project bind'}); return; }
      write({found:true, route_url:canonicalObservedRoute(currentUrl), conversation_id:conversationId, marker_verified:true, match_count:1, project_change_authorized:true, observed_search_href:observedSearchHref});
      return;
    }

    let authoritativeRoutes = await evaluate(`(() => {
      const conversationId = ${JSON.stringify(conversationId)};
      const rows = [];
      for (const anchor of document.querySelectorAll('a[href*="/c/"]')) {
        try {
          const url = new URL(anchor.href);
          const parts = url.pathname.split('/').filter(Boolean);
          const ci = parts.lastIndexOf('c');
          if (ci < 0 || ci !== parts.length - 2 || parts[ci + 1] !== conversationId) continue;
          const gi = parts.indexOf('g');
          if (gi < 0 || gi + 1 >= parts.length || !parts[gi + 1].startsWith('g-p-')) continue;
          url.search = ''; url.hash = '';
          rows.push(url.toString().replace(/\/$/, ''));
        } catch (_) {}
      }
      return [...new Set(rows)];
    })()`);
    if (!Array.isArray(authoritativeRoutes)) authoritativeRoutes = [];
    if (authoritativeRoutes.length === 0) {
      // The target conversation may be rendered as a plain /c/... route with no
      // project links in its DOM. Re-open the already-registered source route,
      // which is known to belong to the expected project, and observe ChatGPT's
      // real slugged project landing there instead of synthesizing a URL.
      await cmd('Page.navigate', {url:routeUrl});
      const observedProjectLanding = await waitUntil(() => evaluate(`(() => {
        const expectedProject = ${JSON.stringify(expectedProject)};
        if (!['interactive','complete'].includes(document.readyState)) return null;
        for (const anchor of document.querySelectorAll('a[href*=\"/project\"]')) {
          try {
            const href = String(anchor.href || '');
            const parts = new URL(href).pathname.split('/').filter(Boolean);
            if (parts.at(-1) !== 'project') continue;
            const gi = parts.indexOf('g');
            if (gi < 0 || gi + 1 >= parts.length) continue;
            const context = parts[gi + 1];
            const match = context.match(/^(g-p-[0-9a-fA-F]{32})(?:-|$)/);
            const project = (match ? match[1] : context).toLowerCase();
            if (project === expectedProject) return href;
          } catch (_) {}
        }
        return null;
      })()`), 350);
      if (!observedProjectLanding) {
        write({found:false, match_count:1, marker_verified:true, detail:'Expected project landing was not observable in authenticated ChatGPT UI'});
        return;
      }
      await cmd('Page.navigate', {url:observedProjectLanding});
      const projectMembership = await waitUntil(() => evaluate(`(() => {
        const conversationId = ${JSON.stringify(conversationId)};
        if (!['interactive','complete'].includes(document.readyState)) return null;
        const found = [...document.querySelectorAll('a[href*="/c/"]')].some((anchor) => {
          try {
            const parts = new URL(anchor.href).pathname.split('/').filter(Boolean);
            const ci = parts.lastIndexOf('c');
            const projectItem = anchor.closest('li');
            const inProjectResults = Boolean(projectItem && String(projectItem.className || '').includes('group/project-item') && anchor.closest('[role="tabpanel"]'));
            return inProjectResults && ci >= 0 && ci === parts.length - 2 && parts[ci + 1] === conversationId;
          } catch (_) { return false; }
        });
        return found ? location.href : null;
      })()`), 350);
      if (!projectMembership || projectIdentityFromUrl(projectMembership) !== expectedProject) {
        write({found:false, match_count:1, marker_verified:true, detail:'Conversation project membership was not observable in authenticated ChatGPT project UI'});
        return;
      }
      const projectPage = new URL(projectMembership);
      const parts = projectPage.pathname.split('/').filter(Boolean);
      if (parts.at(-1) !== 'project') {
        write({found:false, match_count:1, marker_verified:true, detail:'Observed project page route was invalid'});
        return;
      }
      parts.splice(parts.length - 1, 1, 'c', conversationId);
      projectPage.pathname = '/' + parts.join('/');
      projectPage.search = ''; projectPage.hash = '';
      authoritativeRoutes = [projectPage.toString().replace(/\/$/, '')];
    }
    const sameProjectRoutes = authoritativeRoutes.filter((value) => projectIdentityFromUrl(value) === expectedProject);
    if (sameProjectRoutes.length !== 1) {
      write({found:false, match_count:1, marker_verified:true, detail: sameProjectRoutes.length === 0 ? 'Discovered conversation belongs to a different project' : `Expected one authoritative same-project route; found ${sameProjectRoutes.length}`});
      return;
    }
    const authoritativeRoute = canonicalObservedRoute(sameProjectRoutes[0]);
    if (conversationIdFromUrl(authoritativeRoute) !== conversationId) { write({found:false, match_count:1, marker_verified:true, detail:'Authoritative project route conversation identity disagrees'}); return; }
    await cmd('Page.navigate', {url:authoritativeRoute});
    const authoritativeReady = await waitUntil(() => evaluate(`(() => {
      const parts = location.pathname.split('/').filter(Boolean);
      const i = parts.lastIndexOf('c');
      return i >= 0 && i === parts.length - 2 && parts[i + 1] === ${JSON.stringify(conversationId)} && ['interactive','complete'].includes(document.readyState);
    })()`), 350);
    if (!authoritativeReady) { write({found:false, match_count:1, marker_verified:true, detail:'Authoritative project route did not load the discovered conversation'}); return; }
    const currentUrl = String(await evaluate('location.href') || '');
    if (conversationIdFromUrl(currentUrl) !== conversationId || projectIdentityFromUrl(currentUrl) !== expectedProject) { write({found:false, match_count:1, marker_verified:true, detail:'Browser left the authoritative same-project conversation before bind completion'}); return; }

    write({found:true, route_url:canonicalObservedRoute(currentUrl), conversation_id:conversationId, marker_verified:true, match_count:1, authoritativeRoutes, observed_search_href:observedSearchHref});
  } finally {
    rejectPending('discovery-complete');
    try { ws.close(); } catch (_) {}
  }
}

main().catch((error) => {
  try { write({found:false, detail:String(error?.message || error)}); } catch (_) {}
  process.exitCode = 1;
});

#!/usr/bin/env node

import { fileURLToPath } from "node:url";

const CHATGPT_ORIGIN = "https://chatgpt.com";
const WAIT_STEP_MS = 250;
const DISCOVERY_TIMEOUT_MS = 5_000;
const CONNECT_TIMEOUT_MS = 5_000;
const COMMAND_TIMEOUT_MS = 5_000;

export function canonicalizeCandidateUrl(href) {
  if (typeof href !== "string") return null;
  let url;
  try { url = new URL(href, CHATGPT_ORIGIN); } catch { return null; }
  if (url.origin !== CHATGPT_ORIGIN) return null;
  const match = url.pathname.match(/^\/(?:g\/([^/]+)\/)?c\/([^/]+)\/?$/);
  if (!match) return null;
  return match[1] ? `${CHATGPT_ORIGIN}/g/${match[1]}/c/${match[2]}` : `${CHATGPT_ORIGIN}/c/${match[2]}`;
}

function canonicalCandidates(hrefs) {
  const byConversationId = new Map();
  for (const href of hrefs) {
    const candidate = canonicalizeCandidateUrl(href);
    if (!candidate) continue;
    const conversationId = candidate.match(/\/c\/([^/]+)$/)?.[1];
    if (conversationId && !byConversationId.has(conversationId)) byConversationId.set(conversationId, candidate);
  }
  return [...byConversationId.values()];
}

export function classifyCandidateHrefs(hrefs) {
  const candidates = canonicalCandidates(Array.isArray(hrefs) ? hrefs : []);
  if (candidates.length === 0) return { status: "zero" };
  if (candidates.length !== 1) return { status: "ambiguous" };
  return { status: "unique", candidate_url: candidates[0] };
}

function countLiteralOccurrences(text, marker) {
  if (typeof text !== "string" || !marker) return 0;
  let count = 0;
  let offset = 0;
  while ((offset = text.indexOf(marker, offset)) !== -1) {
    count += 1;
    offset += marker.length;
  }
  return count;
}

export function resolveFixture(hrefs, messageTurns, marker) {
  const classified = classifyCandidateHrefs(hrefs);
  if (classified.status !== "unique") return classified;
  const matches = Array.isArray(messageTurns) ? messageTurns.reduce((total, turn) => {
    if (!turn || !["user", "assistant"].includes(turn.role)) return total;
    return total + countLiteralOccurrences(turn.text, marker);
  }, 0) : 0;
  if (matches === 0) return { status: "zero" };
  if (matches !== 1) return { status: "ambiguous" };
  return classified;
}

export function isVisibleElement(element, styleFor = globalThis.getComputedStyle) {
  // Array callbacks receive an index as their second argument, not a style reader.
  if (typeof styleFor !== "function") styleFor = globalThis.getComputedStyle;
  if (!element || element.hidden || element.getAttribute?.("aria-hidden") === "true" ||
      element.getClientRects?.().length === 0) return false;
  const style = styleFor(element);
  return style.display !== "none" && !["hidden", "collapse"].includes(style.visibility) &&
    style.opacity !== "0";
}

export function snapshotSearchScope(input, scope, styleFor = globalThis.getComputedStyle,
  visible = isVisibleElement) {
  if (!input || !scope || !input.isConnected || !scope.isConnected ||
      !visible(input, styleFor) || !visible(scope, styleFor)) return null;
  const loading = [...scope.querySelectorAll(
    '[aria-busy="true"], [role="progressbar"], [class*="loading"]'
  )].some((element) => visible(element, styleFor)) || scope.getAttribute("aria-busy") === "true";
  const hrefs = [...scope.querySelectorAll("a[href]")]
    .filter((element) => visible(element, styleFor))
    .map((element) => element.getAttribute("href"));
  const noResults = [...scope.querySelectorAll(
    '[data-testid*="no-result"], [role="status"], [class*="noResults"]'
  )].some((element) => visible(element, styleFor) &&
    (/no (results|chats|conversations)|nothing found/i.test(element.textContent || "") ||
      String(element.className || "").includes("noResults")));
  return { loading, hrefs, noResults };
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function withTimeout(operation, timeoutMs, message) {
  let timer;
  try {
    return await Promise.race([
      operation,
      new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
      }),
    ]);
  } finally { clearTimeout(timer); }
}

export class CdpClient {
  constructor(url, { WebSocketImpl = WebSocket, connectTimeoutMs = CONNECT_TIMEOUT_MS,
    commandTimeoutMs = COMMAND_TIMEOUT_MS } = {}) {
    this.socket = new WebSocketImpl(url);
    this.nextId = 1;
    this.pending = new Map();
    this.connectTimeoutMs = connectTimeoutMs;
    this.commandTimeoutMs = commandTimeoutMs;
    this.closedError = null;
  }

  fail(error) {
    if (!this.closedError) this.closedError = error;
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(this.closedError);
    }
    this.pending.clear();
  }

  async connect() {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("CDP connection timed out")), this.connectTimeoutMs);
      const finish = (callback) => { clearTimeout(timer); callback(); };
      this.socket.addEventListener("open", () => finish(resolve), { once: true });
      this.socket.addEventListener("error", () => finish(() => reject(new Error("CDP connection failed"))), { once: true });
      this.socket.addEventListener("close", () => finish(() => reject(new Error("CDP connection closed"))), { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve, reject, timer } = this.pending.get(message.id);
      clearTimeout(timer);
      this.pending.delete(message.id);
      if (message.error) reject(new Error("CDP command failed"));
      else resolve(message.result ?? {});
    });
    this.socket.addEventListener("error", () => this.fail(new Error("CDP connection failed")));
    this.socket.addEventListener("close", () => this.fail(new Error("CDP connection closed")));
  }

  call(method, params = {}) {
    if (this.closedError) return Promise.reject(this.closedError);
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("CDP command timed out"));
      }, this.commandTimeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try { this.socket.send(JSON.stringify({ id, method, params })); }
      catch {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new Error("CDP command failed"));
      }
    });
  }

  close() {
    this.fail(new Error("CDP connection closed"));
    try { this.socket.close(); } catch { /* already closed */ }
  }
}

async function evaluate(client, expression) {
  const result = await client.call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error("Page evaluation failed");
  return result.result?.value;
}

async function waitFor(client, expression, timeoutMs = 10_000, waitStepMs = WAIT_STEP_MS) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await evaluate(client, expression);
    if (value) return value;
    await delay(waitStepMs);
  }
  throw new Error("Page readiness timed out");
}

const VISIBLE_ELEMENT_SOURCE = `(${isVisibleElement.toString()})`;
const SNAPSHOT_SEARCH_SCOPE_SOURCE = `(${snapshotSearchScope.toString()})`;

const SEARCH_SNAPSHOT_EXPRESSION = `(() => {
  const input = globalThis.__dbridgeGlobalSearchInput;
  const scope = globalThis.__dbridgeGlobalSearchResultsScroller;
  const dialog = input?.closest('[role="dialog"]');
  if (!dialog?.matches('[data-testid="modal-global-search"]') || !dialog.contains(scope)) return null;
  return ${SNAPSHOT_SEARCH_SCOPE_SOURCE}(input, scope, getComputedStyle, ${VISIBLE_ELEMENT_SOURCE});
})()`;

async function waitForSettledSearchHrefs(client, baseline, timeoutMs = 15_000, waitStepMs = WAIT_STEP_MS) {
  const deadline = Date.now() + timeoutMs;
  const baselineSignature = JSON.stringify(baseline);
  let transitioned = false;
  let previous = null;
  let stableSamples = 0;
  while (Date.now() < deadline) {
    const snapshot = await evaluate(client, SEARCH_SNAPSHOT_EXPRESSION);
    const signature = JSON.stringify(snapshot);
    if (signature !== baselineSignature || (snapshot?.loading && !baseline?.loading)) transitioned = true;
    const settled = snapshot && !snapshot.loading && (snapshot.hrefs.length > 0 || snapshot.noResults);
    if (transitioned && settled) {
      stableSamples = signature === previous ? stableSamples + 1 : 0;
      previous = signature;
      if (stableSamples >= 2) return snapshot.hrefs;
    } else {
      stableSamples = 0;
      previous = null;
    }
    await delay(waitStepMs);
  }
  throw new Error("Search did not settle");
}

async function waitForStableSearchBaseline(client, timeoutMs = 15_000, waitStepMs = WAIT_STEP_MS) {
  const deadline = Date.now() + timeoutMs;
  let previous = null;
  let stableSamples = 0;
  while (Date.now() < deadline) {
    const snapshot = await evaluate(client, SEARCH_SNAPSHOT_EXPRESSION);
    const signature = JSON.stringify(snapshot);
    if (snapshot && !snapshot.loading) {
      stableSamples = signature === previous ? stableSamples + 1 : 0;
      previous = signature;
      if (stableSamples >= 2) return snapshot;
    } else {
      previous = null;
      stableSamples = 0;
    }
    await delay(waitStepMs);
  }
  throw new Error("Cleared search did not settle");
}

const MESSAGE_TURNS_EXPRESSION = `(() => {
  const visible = ${VISIBLE_ELEMENT_SOURCE};
  return [...document.querySelectorAll('[data-testid^="conversation-turn-"]')]
    .filter((turn) => visible(turn))
    .map((turn) => {
      const message = turn.querySelector('[data-message-author-role="user"], [data-message-author-role="assistant"]');
      return message ? { role: message.getAttribute('data-message-author-role'),
        text: message.innerText || message.textContent || '' } : null;
    }).filter(Boolean);
})()`;

async function waitForStableMessageTurns(client, timeoutMs = 10_000, waitStepMs = WAIT_STEP_MS) {
  const deadline = Date.now() + timeoutMs;
  let previous = null;
  let stableSamples = 0;
  while (Date.now() < deadline) {
    const turns = await evaluate(client, MESSAGE_TURNS_EXPRESSION);
    const signature = JSON.stringify(turns);
    if (Array.isArray(turns) && turns.length > 0) {
      stableSamples = signature === previous ? stableSamples + 1 : 0;
      previous = signature;
      if (stableSamples >= 2) return turns;
    } else {
      previous = null;
      stableSamples = 0;
    }
    await delay(waitStepMs);
  }
  throw new Error("Conversation turns did not settle");
}

async function selectPage(browserEndpoint, { fetchImpl = fetch,
  discoveryTimeoutMs = DISCOVERY_TIMEOUT_MS } = {}) {
  const endpoint = browserEndpoint.replace(/\/$/, "");
  const controller = new AbortController();
  const discovery = (async () => {
    const response = await fetchImpl(`${endpoint}/json/list`, { signal: controller.signal });
    if (!response.ok) throw new Error("CDP discovery failed");
    return response.json();
  })();
  let pages;
  try {
    pages = await withTimeout(discovery, discoveryTimeoutMs, "CDP discovery timed out");
  } finally { controller.abort(); }
  const page = pages.find((item) => item.type === "page" &&
    item.url?.startsWith(`${CHATGPT_ORIGIN}/`) && item.webSocketDebuggerUrl);
  if (!page) throw new Error("No browser page available");
  return page.webSocketDebuggerUrl;
}

const EXPLICIT_INTERVENTION_EXPRESSION = `(() => {
  const visible = ${VISIBLE_ELEMENT_SOURCE};
  const login = [...document.querySelectorAll(
    'form[action*="/auth/login"], a[href*="/auth/login"], [data-testid="login-button"]'
  )].some(visible);
  const cloudflare = [...document.querySelectorAll(
    'iframe[src*="challenges.cloudflare.com"], .cf-turnstile, #challenge-running, #cf-challenge-running'
  )].some(visible);
  return login || cloudflare;
})()`;

export async function resolveViaCdp(browserEndpoint, marker, options = {}) {
  const waitStepMs = options.waitStepMs ?? WAIT_STEP_MS;
  const readinessTimeoutMs = options.readinessTimeoutMs ?? 10_000;
  const searchTimeoutMs = options.searchTimeoutMs ?? 15_000;
  const pageUrl = await selectPage(browserEndpoint, options);
  const client = options.clientFactory ? options.clientFactory(pageUrl) : new CdpClient(pageUrl, options);
  try {
    await client.connect();
    await client.call("Page.enable");
    await client.call("Runtime.enable");
    await client.call("Page.navigate", { url: CHATGPT_ORIGIN });
    await waitFor(client, "document.readyState === 'complete'", readinessTimeoutMs, waitStepMs);
    if (await evaluate(client, EXPLICIT_INTERVENTION_EXPRESSION)) return { status: "owner_input_required" };

    await evaluate(client, `(() => {
      const visible = ${VISIBLE_ELEMENT_SOURCE};
      const trigger = [...document.querySelectorAll('button, a')].find((el) => visible(el) &&
        /search/i.test(el.getAttribute('aria-label') || el.getAttribute('data-testid') || el.textContent || ''));
      if (trigger) { trigger.click(); return true; }
      return false;
    })()`);
    await waitFor(client, `(() => {
      const visible = ${VISIBLE_ELEMENT_SOURCE};
      const dialogs = [...document.querySelectorAll('[data-testid="modal-global-search"][role="dialog"]')]
        .filter(visible);
      const dialog = dialogs.find((el) => el.querySelector('[data-testid="global-search-results-scroller"]'));
      const scope = dialog?.querySelector('[data-testid="global-search-results-scroller"]');
      const input = dialog && [...dialog.querySelectorAll('input')].find((el) => visible(el) &&
        /search/i.test(el.placeholder || el.getAttribute('aria-label') || ''));
      if (!input || !scope || !visible(scope)) return false;
      globalThis.__dbridgeGlobalSearchInput = input;
      globalThis.__dbridgeGlobalSearchResultsScroller = scope;
      input.focus(); input.select();
      return document.activeElement === input;
    })()`, readinessTimeoutMs, waitStepMs);
    await client.call("Input.dispatchKeyEvent", { type: "keyDown", key: "a", code: "KeyA", modifiers: 2 });
    await client.call("Input.dispatchKeyEvent", { type: "keyUp", key: "a", code: "KeyA", modifiers: 2 });
    await client.call("Input.dispatchKeyEvent", { type: "keyDown", key: "Backspace", code: "Backspace" });
    await client.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Backspace", code: "Backspace" });
    const cleared = await evaluate(client, `(() => {
      const input = globalThis.__dbridgeGlobalSearchInput;
      return Boolean(input?.isConnected && document.activeElement === input && input.value === '');
    })()`);
    if (!cleared) return { status: "transient" };
    const baseline = await waitForStableSearchBaseline(client, searchTimeoutMs, waitStepMs);
    for (const character of marker) await client.call("Input.dispatchKeyEvent", { type: "char", text: character });
    const exactValue = await evaluate(client, `(() => {
      const visible = ${VISIBLE_ELEMENT_SOURCE};
      const input = globalThis.__dbridgeGlobalSearchInput;
      const scope = globalThis.__dbridgeGlobalSearchResultsScroller;
      const dialog = input?.closest('[role="dialog"]');
      return Boolean(input && scope && input.isConnected && scope.isConnected &&
        visible(input) && visible(scope) && visible(dialog) &&
        dialog?.matches('[data-testid="modal-global-search"]') && dialog.contains(scope) &&
        document.activeElement === input && input.value === ${JSON.stringify(marker)});
    })()`);
    if (!exactValue) return { status: "transient" };

    const hrefs = await waitForSettledSearchHrefs(client, baseline, searchTimeoutMs, waitStepMs);
    const classified = classifyCandidateHrefs(hrefs);
    if (classified.status !== "unique") return classified;

    await client.call("Page.navigate", { url: classified.candidate_url });
    const expectedLocation = JSON.stringify(classified.candidate_url);
    await waitFor(client, `(() => {
      const canonical = (href) => {
        try {
          const url = new URL(href);
          const match = url.pathname.match(/^\\/(?:g\\/[^/]+\\/)?c\\/[^/]+\\/?$/);
          return url.origin === 'https://chatgpt.com' && match ? url.origin + url.pathname.replace(/\\/$/, '') : null;
        } catch { return null; }
      };
      return document.readyState === 'complete' && canonical(location.href) === ${expectedLocation};
    })()`, readinessTimeoutMs, waitStepMs);
    if (await evaluate(client, EXPLICIT_INTERVENTION_EXPRESSION)) return { status: "owner_input_required" };
    const messageTurns = await waitForStableMessageTurns(client, readinessTimeoutMs, waitStepMs);
    return resolveFixture([classified.candidate_url], messageTurns, marker);
  } finally { client.close(); }
}

export function parseArgs(argv) {
  if (!Array.isArray(argv) || argv.length !== 4) throw new Error("Invalid arguments");
  const allowed = new Set(["--browser-endpoint", "--marker"]);
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    if (!allowed.has(name) || Object.hasOwn(values, name) || !argv[index + 1]) throw new Error("Invalid arguments");
    values[name] = argv[index + 1];
  }
  if (!values["--browser-endpoint"] || !values["--marker"]) throw new Error("Missing required arguments");
  return { "browser-endpoint": values["--browser-endpoint"], marker: values["--marker"] };
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    const result = await resolveViaCdp(args["browser-endpoint"], args.marker);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch { process.stdout.write('{"status":"transient"}\n'); }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) await main();

const ext = globalThis.browser ?? globalThis.chrome;
const pendingRoutes = document.getElementById("pendingRoutes");
const bindButton = document.getElementById("bindButton");
const refreshButton = document.getElementById("refreshButton");
const statusNode = document.getElementById("status");
let pending = [];

function status(message) {
  statusNode.textContent = message;
}

function normalizeRouteControlBaseUrl(value) {
  const parsed = new URL(String(value || ""));
  if (parsed.protocol !== "https:") throw new Error("Bridge URL должен использовать HTTPS");
  return parsed.href.replace(/\/$/, "");
}

async function loadConfig() {
  const config = await ext.storage.local.get(["routeControlBaseUrl", "binderToken"]);
  if (!config.routeControlBaseUrl || !config.binderToken) {
    throw new Error("Сначала задайте Bridge URL и Binder token в настройках расширения");
  }
  return {
    routeControlBaseUrl: normalizeRouteControlBaseUrl(config.routeControlBaseUrl),
    binderToken: String(config.binderToken),
  };
}

function validateChatGptConversation(urlValue) {
  const parsed = new URL(urlValue);
  if (parsed.protocol !== "https:" || parsed.hostname !== "chatgpt.com") {
    throw new Error("Активная вкладка должна быть на chatgpt.com");
  }
  const parts = parsed.pathname.split("/").filter(Boolean);
  const conversationIndex = parts.lastIndexOf("c");
  if (conversationIndex < 0 || !parts[conversationIndex + 1]) {
    throw new Error("Откройте конкретный чат ChatGPT перед привязкой");
  }
  return parsed.href;
}

async function activeChatUrl() {
  const tabs = await ext.tabs.query({ active: true, currentWindow: true });
  if (!tabs.length || !tabs[0].url) throw new Error("Не удалось определить активную вкладку");
  return validateChatGptConversation(tabs[0].url);
}

function renderPending(items) {
  pending = Array.isArray(items) ? items : [];
  pendingRoutes.replaceChildren();
  if (pending.length === 0) {
    const option = new Option("Нет ожидающих привязок", "");
    pendingRoutes.add(option);
    bindButton.disabled = true;
    return;
  }
  if (pending.length > 1) {
    pendingRoutes.add(new Option("Выберите маршрут…", ""));
    pendingRoutes.selectedIndex = 0;
  }
  for (const item of pending) {
    const value = `${item.route_id}\t${item.generation}`;
    pendingRoutes.add(new Option(`${item.route_id} · g${item.generation} · ${item.state}`, value));
  }
  if (pending.length === 1) pendingRoutes.selectedIndex = 0;
  bindButton.disabled = false;
}

async function refreshPending() {
  try {
    status("Загрузка…");
    const config = await loadConfig();
    const response = await fetch(`${config.routeControlBaseUrl}/binder/pending`, {
      headers: { Authorization: `Bearer ${config.binderToken}` },
      cache: "no-store",
    });
    const body = await response.json();
    if (!response.ok || body.ok !== true) throw new Error(body.error || `HTTP ${response.status}`);
    renderPending(body.pending);
    status(pending.length ? "Выберите маршрут и нажмите «Привязать»." : "Ожидающих привязок нет.");
  } catch (error) {
    renderPending([]);
    status(error.message || String(error));
  }
}

bindButton.addEventListener("click", async () => {
  try {
    const selected = pendingRoutes.value;
    if (!selected) throw new Error("Выберите маршрут");
    const [route_id, generationText] = selected.split("\t");
    const generation = Number.parseInt(generationText, 10);
    const url = await activeChatUrl();
    const config = await loadConfig();
    bindButton.disabled = true;
    status("Привязка…");
    const response = await fetch(`${config.routeControlBaseUrl}/binder/complete`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.binderToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ route_id, generation, url }),
    });
    const body = await response.json();
    if (!response.ok || body.ok !== true) throw new Error(body.error || `HTTP ${response.status}`);
    status(`Готово: ${body.route_id}, generation ${body.generation}`);
    await refreshPending();
  } catch (error) {
    bindButton.disabled = false;
    status(error.message || String(error));
  }
});

refreshButton.addEventListener("click", refreshPending);
refreshPending();

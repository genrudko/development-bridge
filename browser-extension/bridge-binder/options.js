const ext = globalThis.browser ?? globalThis.chrome;
const routeControlBaseUrl = document.getElementById("routeControlBaseUrl");
const binderToken = document.getElementById("binderToken");
const saveButton = document.getElementById("saveButton");
const statusNode = document.getElementById("status");

async function restore() {
  const saved = await ext.storage.local.get(["routeControlBaseUrl", "binderToken"]);
  routeControlBaseUrl.value = saved.routeControlBaseUrl || "";
  binderToken.value = saved.binderToken || "";
}

saveButton.addEventListener("click", async () => {
  try {
    const parsed = new URL(routeControlBaseUrl.value.trim());
    if (parsed.protocol !== "https:") throw new Error("Bridge URL должен использовать HTTPS");
    const normalized = parsed.href.replace(/\/$/, "");
    if (!normalized.endsWith("/x/route-control")) {
      throw new Error("URL должен заканчиваться на /x/route-control");
    }
    if (!binderToken.value) throw new Error("Binder token обязателен");

    const granted = await ext.permissions.request({ origins: [`${parsed.origin}/*`] });
    if (!granted) throw new Error("Не выдано разрешение на доступ к настроенному Bridge host");

    await ext.storage.local.set({
      routeControlBaseUrl: normalized,
      binderToken: binderToken.value,
    });
    statusNode.textContent = "Сохранено";
  } catch (error) {
    statusNode.textContent = error.message || String(error);
  }
});

restore();

import shutil
import subprocess
from pathlib import Path
import pytest


def test_operator_dashboard_app_js_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for app.js execution test")

    js_path = Path(__file__).parents[2] / "app/ops/static/app.js"
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const jsContent = fs.readFileSync(process.argv[1], "utf8");

const elements = new Map();
function makeElement(id) {
  const el = {
    id,
    textContent: "",
    innerHTML: "",
    className: "",
    style: {},
    dataset: {},
    checked: true,
    value: "",
    scrollHeight: 0,
    scrollTop: 0,
    clientHeight: 0,
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    addEventListener(evt, cb) { this.listeners = this.listeners || {}; this.listeners[evt] = cb; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    classList: { add() {}, remove() {} },
  };
  elements.set(id, el);
  return el;
}

const requiredIds = [
  "bridgeName", "headerActiveJobs", "headerRoutes", "headerExecutors", "headerUptime",
  "activeJobsBadge", "activeJobsTableBody", "routesBadge", "routesTableBody", "routeSelect",
  "progTitle", "progStatus", "progPercent", "progFill", "progPhase", "progCurrent", "progNext", "progDetail",
  "terminalJobSelect", "terminalContent", "terminalJobStatus", "terminalJobId", "terminalTruncated", "autoScrollCheckbox",
  "jobsTableBody", "gitBranch", "gitHead", "gitCleanStatus", "gitChangedFiles", "gitUpstream", "gitAheadBehind",
  "wakeChannel", "wakeState", "wakeContinuation", "wakeAttempts", "wakeDelivered", "wakeTransport", "wakeOwnerAlert", "wakeCooldown",
  "sysMem", "sysDisk", "sysLoad", "sysProcs", "sysUptime", "connStatus", "lastUpdated",
];
requiredIds.forEach(makeElement);

let fetchUrl = null;
let eventSourceUrl = null;

globalThis.document = {
  body: { dataset: { basePath: "/custom-ops" } },
  getElementById: (id) => elements.get(id) || makeElement(id),
  querySelectorAll: () => [],
  addEventListener: (event, cb) => {
    if (event === "DOMContentLoaded") setTimeout(cb, 0);
  },
};

globalThis.window = {
  location: {
    pathname: "/custom-ops/",
    search: "?route_id=eod&job_id=job-b",
    href: "/custom-ops/",
  },
};

const snapshot = {
  bridge: { name: "test-bridge", uptime_seconds: 65 },
  routes: [
    { route_id: "bridge", channel_id: "telegram-bridge-g4", state: "active", default: true, progress: { title: "Bridge work", status: "working", percent: 60 } },
    { route_id: "eod", channel_id: "telegram-eod-g1", state: "active", default: false, progress: { title: "EOD work", status: "working", percent: 25 } },
    { route_id: "ad5xwork", channel_id: "telegram-ad5xwork-g1", state: "active", default: false, progress: null },
  ],
  route: { route_id: "eod", channel_id: "telegram-eod-g1", title: "EOD" },
  progress: { title: "EOD work", status: "working", percent: 25 },
  jobs: {
    active_count: 2,
    active: [
      { job_id: "job-a", project_id: "p1", repository_id: "r1", status: "running", executor: "antigravity", executor_model: "gemini" },
      { job_id: "job-b", project_id: "p2", repository_id: "r2", status: "queued", executor: "codex", executor_model: "gpt" },
    ],
    recent: [
      { job_id: "job-a", project_id: "p1", repository_id: "r1", task_id: "a", status: "running", executor: "antigravity", executor_model: "gemini" },
      { job_id: "job-b", project_id: "p2", repository_id: "r2", task_id: "b", status: "queued", executor: "codex", executor_model: "gpt" },
    ],
    focused: { job_id: "job-b" },
  },
  git: null,
  wake: { channel_id: "telegram-eod-g1", state: "idle" },
  system: { process_counts: {}, load: [] },
};

globalThis.fetch = (url) => {
  fetchUrl = url;
  return Promise.resolve({ status: 200, json: () => Promise.resolve(snapshot) });
};

class MockEventSource {
  constructor(url) { eventSourceUrl = url; this.listeners = {}; }
  addEventListener(evt, cb) { this.listeners[evt] = cb; }
  close() {}
}
globalThis.EventSource = MockEventSource;

vm.runInThisContext(jsContent);

setTimeout(() => {
  if (fetchUrl !== "/custom-ops/api/snapshot?route_id=eod&job_id=job-b") {
    throw new Error(`fetchUrl lost focus query: ${fetchUrl}`);
  }
  if (eventSourceUrl !== "/custom-ops/api/events?route_id=eod&job_id=job-b") {
    throw new Error(`eventSourceUrl lost focus query: ${eventSourceUrl}`);
  }
  if (elements.get("headerActiveJobs").textContent !== 2) throw new Error("active job count missing");
  if (elements.get("headerRoutes").textContent !== 3) throw new Error("route count missing");
  const executors = elements.get("headerExecutors").textContent;
  if (!executors.includes("antigravity: 1") || !executors.includes("codex: 1")) {
    throw new Error(`executor summary incomplete: ${executors}`);
  }
  if (!elements.get("activeJobsTableBody").innerHTML.includes("job-a") || !elements.get("activeJobsTableBody").innerHTML.includes("job-b")) {
    throw new Error("overview does not show all active jobs");
  }
  if (!elements.get("routesTableBody").innerHTML.includes("ad5xwork")) throw new Error("overview does not show all routes");
  if (!elements.get("routeSelect").innerHTML.includes("eod")) throw new Error("route selector missing");
  if (!elements.get("terminalJobSelect").innerHTML.includes("job-b")) throw new Error("terminal job selector missing");
  if (elements.get("progStatus").textContent !== "в работе") throw new Error("status is not localized");
  process.stdout.write("app.js tests passed\n");
}, 20);
'''
    result = subprocess.run(
        [node, "-e", harness, str(js_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"JS execution failed:\n{result.stderr}\n{result.stdout}"
    assert "app.js tests passed" in result.stdout


def test_operator_dashboard_templates_are_russian_and_global_first():
    root = Path(__file__).parents[2] / "app" / "ops" / "templates"
    dashboard = (root / "dashboard.html").read_text(encoding="utf-8")
    login = (root / "login.html").read_text(encoding="utf-8")

    assert '<html lang="ru">' in dashboard
    assert '<html lang="ru">' in login
    for label in ("Активных задач", "Маршрутов", "Исполнители", "Обзор", "Терминал", "Задачи", "Пробуждение", "Система"):
        assert label in dashboard
    assert "Панель оператора" in login
    assert "Пароль" in login
    assert "Войти" in login
    assert 'id="routeSelect"' in dashboard
    assert 'id="terminalJobSelect"' in dashboard

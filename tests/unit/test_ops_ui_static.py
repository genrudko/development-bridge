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

// Mock DOM environment
const elements = new Map();
function makeElement(id) {
  const el = {
    id,
    textContent: "",
    innerHTML: "",
    className: "",
    style: {},
    dataset: { basePath: "/custom-ops" },
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    addEventListener() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
  };
  elements.set(id, el);
  return el;
}

const requiredIds = [
  "bridgeName", "headerRoute", "headerExecutor", "headerUptime",
  "progTitle", "progStatus", "progPercent", "progFill", "progPhase", "progCurrent", "progNext", "progDetail",
  "overviewJobId", "overviewJobStatus",
  "terminalContent", "terminalJobStatus", "terminalJobId", "terminalTruncated", "autoScrollCheckbox",
  "jobsTableBody", "tab-git", "gitBranch", "gitHead", "gitCleanStatus", "gitChangedFiles", "gitUpstream", "gitAheadBehind",
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
  createElement: (tag) => ({
    tagName: tag.toUpperCase(),
    textContent: "",
    innerHTML: "",
    className: "",
    style: {},
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    setAttribute() {},
  }),
};

globalThis.window = {
  location: { pathname: "/custom-ops/", href: "/custom-ops/" },
};

globalThis.fetch = (url) => {
  fetchUrl = url;
  return Promise.resolve({
    status: 200,
    json: () => Promise.resolve({
      bridge: { name: "test-bridge" },
      progress: { percent: undefined },
      jobs: { current: { job_id: "job-1", status: "running" } },
    }),
  });
};

class MockEventSource {
  constructor(url) {
    eventSourceUrl = url;
    this.listeners = {};
  }
  addEventListener(evt, cb) { this.listeners[evt] = cb; }
  close() {}
}
globalThis.EventSource = MockEventSource;

vm.runInThisContext(jsContent);

setTimeout(() => {
  if (!fetchUrl || !fetchUrl.startsWith("/custom-ops/")) {
    throw new Error(`fetchUrl does not honor basePath: ${fetchUrl}`);
  }
  if (!eventSourceUrl || !eventSourceUrl.startsWith("/custom-ops/")) {
    throw new Error(`eventSourceUrl does not honor basePath: ${eventSourceUrl}`);
  }

  const progPercent = elements.get("progPercent").textContent;
  if (progPercent === "50%") {
    throw new Error("Progress percent inferred 50% when semantic percent was absent!");
  }

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

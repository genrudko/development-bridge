from pathlib import Path
import shutil
import subprocess

import pytest


def test_dashboard_binds_operation_and_stops_polling_after_collapse():
    html = (Path(__file__).parents[2] / "app/dashboard/status_ui.html").read_text(encoding="utf-8")

    assert "boundOperationId" in html
    assert 'data-lifecycle="expanded"' in html
    assert 'collapseProgress("completed")' in html
    assert 'collapseProgress("superseded")' in html
    assert "COLLAPSE_DELAY_MS" in html
    assert "pollingStopped" in html


def test_dashboard_collapse_is_terminal_for_in_flight_refresh():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the executable dashboard lifecycle test")
    html_path = Path(__file__).parents[2] / "app/dashboard/status_ui.html"
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
let source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/m, "const App = globalThis.App;")
  .replace("await app.connect();", "app.connect();");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: "", className: "", dataset: {}, style: {},
    classList: { toggle(name, enabled) { this[name] = enabled; } },
  });
  return elements.get(id);
}
const listeners = {};
const timeouts = new Map();
let nextTimer = 1;
let resolveRead;
class DashboardAppStub {
  constructor() { globalThis.dashboardApp = this; }
  connect() { return Promise.resolve(); }
  sendSizeChanged() {}
  readServerResource() { return new Promise(resolve => { resolveRead = resolve; }); }
}
globalThis.App = DashboardAppStub;
globalThis.document = {
  hidden: false,
  documentElement: { scrollHeight: 100 },
  getElementById: element,
  addEventListener(name, fn) { listeners[name] = fn; },
};
globalThis.window = { addEventListener() {} };
globalThis.requestAnimationFrame = fn => fn();
globalThis.setTimeout = fn => { const id = nextTimer++; timeouts.set(id, fn); return id; };
globalThis.clearTimeout = id => timeouts.delete(id);
vm.runInThisContext(source);
const completed = {progress: {operation_id:"op-1", title:"Build", total:1, completed:1, percent:100, status:"completed"}};
for (const status of ["waiting", "blocked"]) {
  dashboardApp.ontoolresult({progress: {...completed.progress, completed:0, percent:0, status}});
  if (element("progress").dataset.lifecycle !== "expanded" || timeouts.size === 0) {
    throw new Error(`${status} progress is not expanded and live`);
  }
}
dashboardApp.ontoolresult(completed);
listeners.visibilitychange();
const collapse = [...timeouts.values()].find(fn => fn.toString().includes('collapseProgress("completed")'));
if (!collapse || !resolveRead) throw new Error("harness did not create the race");
collapse();
resolveRead({contents:[{text:JSON.stringify(completed)}]});
setImmediate(() => {
  if (element("progress").dataset.lifecycle !== "collapsed") throw new Error("in-flight refresh expanded collapsed progress");
  if (timeouts.size !== 0) throw new Error("collapsed progress restarted polling");
  process.stdout.write("terminal collapse preserved\n");
});
'''
    result = subprocess.run(
        [node, "-e", harness, str(html_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "terminal collapse preserved\n"


def test_dashboard_ignores_pre_bind_refresh_from_previous_operation():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the executable dashboard lifecycle test")
    html_path = Path(__file__).parents[2] / "app/dashboard/status_ui.html"
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
let source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/m, "const App = globalThis.App;")
  .replace("await app.connect();", "app.connect();");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: "", className: "", dataset: {}, style: {},
    classList: { toggle(name, enabled) { this[name] = enabled; } },
  });
  return elements.get(id);
}
const listeners = {};
const timeouts = new Map();
let nextTimer = 1;
let resolveRead;
class DashboardAppStub {
  constructor() { globalThis.dashboardApp = this; }
  connect() { return Promise.resolve(); }
  sendSizeChanged() {}
  readServerResource() { return new Promise(resolve => { resolveRead = resolve; }); }
}
globalThis.App = DashboardAppStub;
globalThis.document = {
  hidden: false,
  documentElement: { scrollHeight: 100 },
  getElementById: element,
  addEventListener(name, fn) { listeners[name] = fn; },
};
globalThis.window = { addEventListener() {} };
globalThis.requestAnimationFrame = fn => fn();
globalThis.setTimeout = fn => { const id = nextTimer++; timeouts.set(id, fn); return id; };
globalThis.clearTimeout = id => timeouts.delete(id);
vm.runInThisContext(source);
listeners.visibilitychange();
if (!resolveRead) throw new Error("harness did not start the pre-bind refresh");
dashboardApp.ontoolresult({progress: {
  operation_id:"NEW", title:"New operation", total:4, completed:2,
  percent:50, status:"working", current:"new work",
}});
resolveRead({contents:[{text:JSON.stringify({progress: {
  operation_id:"OLD", title:"Old operation", total:3, completed:1,
  percent:33, status:"working", current:"old work",
}})}]});
setImmediate(() => {
  if (element("progress").dataset.lifecycle !== "expanded") {
    throw new Error("pre-bind refresh collapsed the newly bound operation");
  }
  if (element("progressTitle").textContent !== "New operation" ||
      element("progressCurrent").textContent !== "Сейчас: new work") {
    throw new Error("pre-bind refresh replaced the newly bound operation");
  }
  if (timeouts.size === 0) throw new Error("pre-bind refresh permanently stopped polling");
  process.stdout.write("pre-bind stale refresh ignored\n");
});
'''
    result = subprocess.run(
        [node, "-e", harness, str(html_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "pre-bind stale refresh ignored\n"


def test_dashboard_ignores_out_of_order_revision_for_bound_operation():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the executable dashboard lifecycle test")
    html_path = Path(__file__).parents[2] / "app/dashboard/status_ui.html"
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
let source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/m, "const App = globalThis.App;")
  .replace("await app.connect();", "app.connect();");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: "", className: "", dataset: {}, style: {},
    classList: { toggle(name, enabled) { this[name] = enabled; } },
  });
  return elements.get(id);
}
const listeners = {};
const reads = [];
class DashboardAppStub {
  constructor() { globalThis.dashboardApp = this; }
  connect() { return Promise.resolve(); }
  sendSizeChanged() {}
  readServerResource() { return new Promise(resolve => reads.push(resolve)); }
}
globalThis.App = DashboardAppStub;
globalThis.document = {
  hidden: false,
  documentElement: { scrollHeight: 100 },
  getElementById: element,
  addEventListener(name, fn) { listeners[name] = fn; },
};
globalThis.window = { addEventListener() {} };
globalThis.requestAnimationFrame = fn => fn();
globalThis.setTimeout = () => 1;
globalThis.clearTimeout = () => {};
vm.runInThisContext(source);
listeners.visibilitychange();
listeners.visibilitychange();
if (reads.length !== 2) throw new Error("harness did not start two refreshes");
const snapshot = (revision, completed) => ({contents:[{text:JSON.stringify({progress:{
  operation_id:"op-1", revision, title:"Build", total:3, completed,
  percent:completed * 10, status:"working", current:`revision ${revision}`,
}})}]});
reads[1](snapshot(2, 2));
setImmediate(() => {
  reads[0](snapshot(1, 1));
  setImmediate(() => {
    if (element("progressCurrent").textContent !== "Сейчас: revision 2") {
      throw new Error(`stale revision rendered: ${element("progressCurrent").textContent}`);
    }
    if (element("progressCount").textContent !== "2 / 3 · 20%") {
      throw new Error(`stale progress rendered: ${element("progressCount").textContent}`);
    }
    process.stdout.write("newest revision preserved\n");
  });
});
'''
    result = subprocess.run(
        [node, "-e", harness, str(html_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "newest revision preserved\n"


def test_dashboard_newer_waiting_snapshot_cancels_completed_collapse():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the executable dashboard lifecycle test")
    html_path = Path(__file__).parents[2] / "app/dashboard/status_ui.html"
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
let source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/m, "const App = globalThis.App;")
  .replace("await app.connect();", "app.connect();");
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: "", className: "", dataset: {}, style: {},
    classList: { toggle(name, enabled) { this[name] = enabled; } },
  });
  return elements.get(id);
}
const timeouts = new Map();
let nextTimer = 1;
class DashboardAppStub {
  constructor() { globalThis.dashboardApp = this; }
  connect() { return Promise.resolve(); }
  sendSizeChanged() {}
  readServerResource() { return new Promise(() => {}); }
}
globalThis.App = DashboardAppStub;
globalThis.document = {
  hidden: false,
  documentElement: { scrollHeight: 100 },
  getElementById: element,
  addEventListener() {},
};
globalThis.window = { addEventListener() {} };
globalThis.requestAnimationFrame = fn => fn();
globalThis.setTimeout = fn => { const id = nextTimer++; timeouts.set(id, fn); return id; };
globalThis.clearTimeout = id => timeouts.delete(id);
vm.runInThisContext(source);
const snapshot = (revision, status) => ({progress: {
  operation_id:"op-1", revision, title:"Build", total:2,
  completed:status === "completed" ? 2 : 1,
  percent:status === "completed" ? 100 : 50,
  status,
}});
dashboardApp.ontoolresult(snapshot(7, "completed"));
const collapseEntry = [...timeouts.entries()].find(([, fn]) =>
  fn.toString().includes('collapseProgress("completed")'));
if (!collapseEntry) throw new Error("completed snapshot did not schedule collapse");
dashboardApp.ontoolresult(snapshot(8, "waiting"));
if (timeouts.has(collapseEntry[0])) collapseEntry[1]();
if (element("progress").dataset.lifecycle !== "expanded") {
  throw new Error("stale completed timer collapsed newer waiting progress");
}
if (element("progressState").textContent !== "waiting") {
  throw new Error(`newer live state was lost: ${element("progressState").textContent}`);
}
process.stdout.write("newer waiting progress remains live\n");
'''
    result = subprocess.run(
        [node, "-e", harness, str(html_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "newer waiting progress remains live\n"

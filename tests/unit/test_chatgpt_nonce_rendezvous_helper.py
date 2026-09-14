from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "chatgpt_nonce_rendezvous.mjs"


def run_module(expression: str) -> object:
    script = (
        f'import * as helper from {json.dumps(HELPER.as_uri())};'
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def run_async_module(body: str) -> object:
    script = (
        f'import * as helper from {json.dumps(HELPER.as_uri())};'
        f"const value = await (async () => {{ {body} }})();"
        "process.stdout.write(JSON.stringify(value));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_canonicalizes_supported_chatgpt_conversation_urls_and_rejects_others():
    hrefs = [
        "https://chatgpt.com/c/conv-one?utm_source=search#fragment",
        "/g/g-p-project/c/conv-two?foo=bar",
        "https://chat.openai.com/c/legacy",
        "/share/shared-id",
        "javascript:alert(1)",
    ]

    assert run_module(f"{json.dumps(hrefs)}.map(helper.canonicalizeCandidateUrl)") == [
        "https://chatgpt.com/c/conv-one",
        "https://chatgpt.com/g/g-p-project/c/conv-two",
        None,
        None,
        None,
    ]


def test_deduplicates_canonical_conversation_identities_before_classification():
    hrefs = [
        "/c/conv-one",
        "https://chatgpt.com/c/conv-one?duplicate=1",
        "/g/g-p-project/c/conv-two",
        "/g/g-p-project/c/conv-two#duplicate",
    ]

    assert run_module(f"helper.classifyCandidateHrefs({json.dumps(hrefs)})") == {
        "status": "ambiguous"
    }
    same_conversation = ["/c/conv-one", "/g/g-p-project/c/conv-one"]
    assert run_module(
        f"helper.classifyCandidateHrefs({json.dumps(same_conversation)})"
    ) == {"status": "unique", "candidate_url": "https://chatgpt.com/c/conv-one"}


def test_zero_and_ambiguous_fixture_handling_never_emit_candidate_url():
    zero = run_module("helper.classifyCandidateHrefs([])")
    ambiguous = run_module(
        'helper.classifyCandidateHrefs(["/c/first", "/c/second"])'
    )

    assert zero == {"status": "zero"}
    assert ambiguous == {"status": "ambiguous"}
    assert "candidate_url" not in zero
    assert "candidate_url" not in ambiguous


def test_sole_candidate_requires_exactly_one_marker_occurrence_across_roles():
    marker = "DBRIDGE_BIND bnd_exact-marker"
    candidate = "https://chatgpt.com/g/g-p-project/c/conv-only?search=1"

    assert run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], "
        f"[{{role:'assistant', text:{json.dumps('assistant preface\\n' + marker + '\\nassistant suffix')}}}], "
        f"{json.dumps(marker)})"
    ) == {
        "status": "unique",
        "candidate_url": "https://chatgpt.com/g/g-p-project/c/conv-only",
    }
    assert run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], [], {json.dumps(marker)})"
    ) == {"status": "zero"}
    assert run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], "
        f"[{{role:'user', text:{json.dumps('user: ' + marker)}}}, "
        f"{{role:'assistant', text:{json.dumps('assistant: ' + marker)}}}], {json.dumps(marker)})"
    ) == {"status": "ambiguous"}
    assert run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], "
        f"[{{role:'assistant', text:{json.dumps(marker + ' then ' + marker)}}}], {json.dumps(marker)})"
    ) == {"status": "ambiguous"}
    assert run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], "
        f"[{{role:'system', text:{json.dumps(marker)}}}], {json.dumps(marker)})"
    ) == {"status": "zero"}


def test_real_cdp_workflow_scopes_search_waits_for_transition_and_render():
    marker = "DBRIDGE_BIND bnd_workflow"
    body = f"""
      const marker = {json.dumps(marker)};
      const evaluations = [];
      const commands = [];
      let snapshot = 0;
      let locationChecks = 0;
      let turnChecks = 0;
      const client = {{
        async connect() {{}},
        close() {{}},
        async call(method, params = {{}}) {{
          commands.push({{method, params}});
          if (method !== 'Runtime.evaluate') return {{}};
          const expression = params.expression;
          evaluations.push(expression);
          let value;
          if (expression.includes('canonical(location.href)')) value = ++locationChecks >= 2;
          else if (expression.includes('.some((turn)')) value = ++turnChecks >= 2;
          else if (expression.includes('.map((turn)')) value = [
            {{role:'user', text:'user content'}},
            {{role:'assistant', text:'assistant preface\\n' + marker + '\\nassistant suffix'}},
          ];
          else if (expression.includes('input.value ===')) value = true;
          else if (expression.includes('const loading =')) {{
            const states = [
              {{loading:false, hrefs:['/c/stale'], noResults:false}},
              {{loading:true, hrefs:['/c/stale'], noResults:false}},
              {{loading:false, hrefs:['/c/final'], noResults:false}},
              {{loading:false, hrefs:['/c/final'], noResults:false}},
              {{loading:false, hrefs:['/c/final'], noResults:false}},
            ];
            value = states[Math.min(snapshot++, states.length - 1)];
          }} else if (expression.includes('/auth/login')) value = false;
          else value = true;
          return {{result: {{value}}}};
        }},
      }};
      const result = await helper.resolveViaCdp('http://fake-cdp', marker, {{
        fetchImpl: async () => ({{ok:true, json:async () => [{{type:'page', url:'https://chatgpt.com/', webSocketDebuggerUrl:'ws://fake'}}]}}),
        clientFactory: () => client,
        waitStepMs: 0,
        readinessTimeoutMs: 100,
        searchTimeoutMs: 100,
      }});
      return {{result, evaluations, commands, locationChecks, turnChecks, snapshot}};
    """
    outcome = run_async_module(body)

    assert outcome["result"] == {
        "status": "unique",
        "candidate_url": "https://chatgpt.com/c/final",
    }
    assert outcome["snapshot"] >= 4
    assert outcome["locationChecks"] >= 2
    assert outcome["turnChecks"] >= 2
    expressions = "\n".join(outcome["evaluations"])
    assert '[data-testid="global-search-results-scroller"]' in expressions
    assert "globalThis.__dbridgeGlobalSearchInput" in expressions
    assert '[data-message-author-role="user"]' in expressions
    assert '[data-message-author-role="assistant"]' in expressions


def test_portal_visibility_and_live_search_state_do_not_depend_on_offset_parent():
    body = """
      const visiblePortal = {
        isConnected: true,
        hidden: false,
        getAttribute(name) { return name === 'aria-hidden' ? 'false' : null; },
        getClientRects() { return [{width: 100, height: 100}]; },
      };
      const hiddenPortal = {
        ...visiblePortal,
        getAttribute(name) { return name === 'aria-hidden' ? 'true' : null; },
      };
      const loading = {...visiblePortal, className: 'group global-search-loading'};
      const noResults = {...visiblePortal, className: 'globalSearch-noResults'};
      const scope = {
        ...visiblePortal,
        getAttribute() { return null; },
        querySelectorAll(selector) {
          if (selector === 'a[href]') return [];
          if (selector.includes('[class*="loading"')) return [loading];
          if (selector.includes('[class*="noResults"')) return [noResults];
          return [];
        },
      };
      const styleFor = () => ({display:'grid', visibility:'visible', opacity:'1'});
      return {
        visible: helper.isVisibleElement(visiblePortal, styleFor),
        hidden: helper.isVisibleElement(hiddenPortal, styleFor),
        snapshot: helper.snapshotSearchScope(visiblePortal, scope, styleFor),
      };
    """

    assert run_async_module(body) == {
        "visible": True,
        "hidden": False,
        "snapshot": {"loading": True, "hrefs": [], "noResults": True},
    }


def test_visibility_predicate_accepts_array_callback_arguments():
    body = """
      globalThis.getComputedStyle = () => ({display:'grid', visibility:'visible', opacity:'1'});
      const portal = {
        offsetParent: null, hidden: false,
        getAttribute() { return null; },
        getClientRects() { return [{width:100, height:100}]; },
      };
      const elements = [{...portal, hidden:true}, portal];
      return {
        filtered: elements.filter(helper.isVisibleElement).length,
        some: elements.some(helper.isVisibleElement),
        injected: helper.isVisibleElement(portal, () => ({display:'none'})),
      };
    """
    assert run_async_module(body) == {"filtered": 1, "some": True, "injected": False}


def test_stale_empty_search_state_is_not_accepted_as_zero():
    body = """
      const client = {
        async connect() {}, close() {},
        async call(method, params = {}) {
          if (method !== 'Runtime.evaluate') return {};
          const expression = params.expression;
          let value = true;
          if (expression.includes('const loading ='))
            value = {loading:false, hrefs:[], noResults:false};
          else if (expression.includes('/auth/login')) value = false;
          return {result:{value}};
        },
      };
      try {
        await helper.resolveViaCdp('http://fake-cdp', 'DBRIDGE_BIND bnd_stale', {
          fetchImpl: async () => ({ok:true, json:async () => [{type:'page', url:'https://chatgpt.com/', webSocketDebuggerUrl:'ws://fake'}]}),
          clientFactory: () => client, waitStepMs: 0, readinessTimeoutMs: 50, searchTimeoutMs: 10,
        });
        return 'accepted';
      } catch { return 'transient'; }
    """
    assert run_async_module(body) == "transient"


def test_cdp_client_rejects_pending_command_when_socket_closes():
    body = """
      class FakeSocket {
        constructor() { this.listeners = {}; queueMicrotask(() => this.emit('open', {})); }
        addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
        emit(name, event) { for (const callback of this.listeners[name] ?? []) callback(event); }
        send() { queueMicrotask(() => this.emit('close', {})); }
        close() {}
      }
      const client = new helper.CdpClient('ws://fake', {WebSocketImpl:FakeSocket, connectTimeoutMs:50, commandTimeoutMs:50});
      await client.connect();
      try { await client.call('Runtime.enable'); return 'resolved'; }
      catch { return 'rejected'; }
    """
    assert run_async_module(body) == "rejected"


def test_cdp_connect_and_command_waits_have_independent_timeouts():
    body = """
      class SilentSocket {
        constructor() { this.listeners = {}; }
        addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
        send() {}
        close() {}
      }
      class OpenSocket extends SilentSocket {
        constructor() {
          super();
          queueMicrotask(() => {
            for (const callback of this.listeners.open ?? []) callback({});
          });
        }
      }
      const unopened = new helper.CdpClient('ws://fake', {
        WebSocketImpl:SilentSocket, connectTimeoutMs:10, commandTimeoutMs:10,
      });
      const connect = await unopened.connect().then(() => 'resolved', () => 'rejected');
      const opened = new helper.CdpClient('ws://fake', {
        WebSocketImpl:OpenSocket, connectTimeoutMs:10, commandTimeoutMs:10,
      });
      await opened.connect();
      const command = await opened.call('Runtime.enable').then(() => 'resolved', () => 'rejected');
      opened.close();
      return {connect, command};
    """
    assert run_async_module(body) == {
        "connect": "rejected",
        "command": "rejected",
    }


def test_cdp_discovery_is_bounded_even_when_fetch_ignores_abort_signal():
    body = """
      const outcome = await Promise.race([
        helper.resolveViaCdp('http://fake-cdp', 'DBRIDGE_BIND bnd_timeout', {
          fetchImpl: async () => new Promise(() => {}), discoveryTimeoutMs: 10,
        }).then(() => 'resolved', () => 'rejected'),
        new Promise((resolve) => setTimeout(() => resolve('timed_out'), 100)),
      ]);
      return outcome;
    """
    assert run_async_module(body) == "rejected"


def test_only_explicit_intervention_ui_returns_owner_input_required():
    body = """
      const client = {
        async connect() {}, close() {},
        async call(method, params = {}) {
          if (method !== 'Runtime.evaluate') return {};
          const value = params.expression.includes('document.readyState') ||
            params.expression.includes('/auth/login');
          return {result:{value}};
        },
      };
      return helper.resolveViaCdp('http://fake-cdp', 'DBRIDGE_BIND bnd_login', {
        fetchImpl: async () => ({ok:true, json:async () => [{type:'page', url:'https://chatgpt.com/', webSocketDebuggerUrl:'ws://fake'}]}),
        clientFactory: () => client, waitStepMs:0, readinessTimeoutMs:50,
      });
    """
    assert run_async_module(body) == {"status": "owner_input_required"}


def test_non_unique_fixture_outputs_cannot_leak_candidate_url():
    candidate = "https://chatgpt.com/c/secret-conversation"
    result = run_module(
        f"helper.resolveFixture([{json.dumps(candidate)}], "
        '[{role:"assistant", text:"wrong"}], "marker")'
    )

    assert result == {"status": "zero"}
    assert candidate not in json.dumps(result)


def test_cli_emits_one_json_object_without_echoing_invalid_arguments():
    result = subprocess.run(
        ["node", str(HELPER), "--unsupported", "https://chatgpt.com/c/secret"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout) == {"status": "transient"}
    assert "secret" not in result.stdout


def test_cli_rejects_duplicate_and_extra_options():
    for arguments in (
        ["--marker", "one", "--marker", "two"],
        ["--browser-endpoint", "http://localhost", "--marker", "one", "--extra", "x"],
    ):
        result = subprocess.run(
            ["node", str(HELPER), *arguments], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )
        assert json.loads(result.stdout) == {"status": "transient"}

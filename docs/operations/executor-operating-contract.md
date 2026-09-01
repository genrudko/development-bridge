# Coding Executor Operating Contract

This runbook applies to Codex, Antigravity, and any future coding executor launched through Development Bridge. ChatGPT/Development Bridge remains the coordinator and acceptance authority; the coding agent is a bounded implementation/review worker.

## 1. One bounded outcome per executor job

The coordinator must give the executor one complete engineering outcome with:

- exact repository and scope;
- required behavior and invariants;
- files or subsystems that may be changed;
- explicit non-goals;
- acceptance tests and required verification;
- stop conditions and known operator boundaries;
- explicit permission state for commit, push, PR, merge, deploy, credential, service, or topology changes.

Do not turn the executor into a conversational shell where every substep returns to the coordinator for another instruction. The executor should inspect, implement, debug, verify, and report one bounded result.

## 2. VPS-first execution

Repository work should stay on the VPS whenever the VPS can answer the question directly.

Use local repository tools for file reads, `rg`/`grep`, Git reads, builds, tests, linters, formatters, and bounded log inspection. Batch related probes under one decision boundary. Prefer one durable repository job for work lasting more than a few seconds.

Do not spend Bridge/MCP/ChatGPT/browser round-trips on ordinary local work. Bridge-native tools remain required where Bridge is the authority: registered repository resolution, durable job lifecycle, coordinator wake/ACK, protected Git/GitHub writes, and other capabilities that intentionally keep credentials or policy out of executor shells.

## 3. No redundant tool calls

A coding executor or coordinator must not repeat the same tool call merely to "make sure".

Repeat only when at least one of these is true:

1. a state-changing event occurred after the previous read;
2. new evidence changes the hypothesis being tested;
3. the previous call returned a documented retryable/transient failure;
4. the previous result did not contain data now required by a new decision.

Do not repeatedly discover an unchanged schema/capability, poll a durable job at short intervals, reread unchanged files, or issue multiple equivalent log/status queries. Use event-driven wake where available and combine VPS-side evidence gathering into bounded commands.

## 4. Minimal-change implementation

Read `AGENTS.md` first. Inspect only relevant source, tests, configuration, and nearby call sites. Make the smallest change that satisfies the accepted design and tests. Do not refactor unrelated code or modify repository topology as a diagnostic shortcut.

Executor shells must not receive or manufacture Bridge-native credentials. Never replace Bridge-native Git/GitHub writes with shell `git push`, `gh auth`, embedded PATs, credential files, or remote rewriting.

## 5. Mandatory debug sweep before handoff

A first green targeted test is not completion. Before reporting a coding change ready for coordinator acceptance, perform a bounded debug sweep designed to falsify the implementation.

At minimum:

1. **Original condition:** reproduce the original bug, regression, or acceptance condition and prove the new behavior.
2. **Happy path:** exercise the ordinary successful path through the changed behavior.
3. **Nearest failure/edge path:** exercise the most relevant adjacent failure, boundary, invalid input, timeout, retry, or state-transition case.
4. **Runtime evidence:** inspect only bounded/filtered logs and output for unexpected warnings, tracebacks, retries, leaked resources, or ambiguous states.
5. **Regression tests:** run the targeted tests plus the closest neighboring suite affected by the change.
6. **Repository hygiene:** run `git diff --check`, inspect `git diff --stat`/relevant diff, and confirm final status contains only intended files.
7. **Live acceptance gate:** browser/UI/E2E is allowed only when offline review and verification are already green. Run the smallest deliberate live acceptance once. Do not repeat a successful live acceptance without new evidence.

If the debug sweep finds a defect, fix it and rerun the affected offline checks. Do not stack workarounds on an unproven diagnosis. If the failure is auth, quota, operator input, credential, service policy, or unsafe topology change, stop and return a proven blocker instead of modifying infrastructure without permission.

## 6. Retry and rework discipline

No automatic executor retry loop is allowed. A failed executor job is evidence. Classify it first:

- repository/test failure -> debug the repository change;
- executor runtime failure -> report the exact runtime evidence;
- auth required -> stop for operator action;
- quota exhausted -> stop or let the coordinator select another executor;
- proven retryable transient -> coordinator may authorize one bounded retry;
- uncertain privileged/live action -> never retry automatically.

A second executor job should exist because the first result produced new actionable evidence, not because the first answer was inconvenient.

## 7. Handoff evidence

Return a compact evidence report containing:

- what changed and why;
- exact files changed;
- original-condition reproduction result;
- debug-sweep cases exercised;
- targeted/neighboring test commands and results;
- relevant warnings or known unrelated failures;
- `git diff --check` result and final worktree status;
- commit SHA if commit permission was granted;
- any remaining blocker or operator action.

Do not claim completion from intuition, agent self-report, or partial tests. The coordinator independently decides acceptance and whether any Bridge-native write is allowed.

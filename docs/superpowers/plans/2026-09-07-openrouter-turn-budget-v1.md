# OpenRouter Turn Budget v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded OpenRouter worker `max_turns=30` guardrail with an explicit executor setting and make turn-budget exhaustion fail the durable job instead of reporting false success.

**Architecture:** Keep `task_timeout_seconds` as the independent wall-clock hard stop and add `OpenRouterExecutorSettings.max_turns` as the model/tool-loop budget. Propagate the configured value through `OpenRouterExecutor.launch()` via a worker CLI argument, parse it in `openrouter_worker.py`, and return a non-success worker result when the loop exhausts. Do not redesign the tool protocol or change automatic executor selection.

**Tech Stack:** Python 3.12, Pydantic settings, argparse, pytest, Development Bridge durable executor/job pipeline.

**Spec:** `docs/superpowers/plans/2026-09-06-openrouter-executor-v1.md` plus the accepted live bug report that 30 hard-coded turns can be consumed by DeepSeek before implementation begins.

## Global Constraints

- Preserve explicit-only OpenRouter executor selection behavior.
- Default `max_turns` is **120**; validate **1..500**.
- Environment override name is `DEVELOPMENT_BRIDGE_OPENROUTER_MAX_TURNS`.
- Do not derive turn budget from Antigravity settings.
- Do not replace or weaken `task_timeout_seconds`; it remains a separate wall-clock limit.
- Exhausting `max_turns` must produce worker `status=ERROR`, a machine-readable `reason=max_turns_exhausted`, preserve cumulative `usage`, and cause the process/job to fail.
- Normal completion before the limit remains `status=SUCCESS`.
- No push, deploy, unrelated refactor, credential changes, or remote mutation.

---

### Task 1: Configurable OpenRouter turn budget

**Files:**
- Modify: `app/settings.py`
- Modify: `app/executors/openrouter.py`
- Modify: `app/executors/openrouter_worker.py`
- Test: `tests/unit/test_settings.py`
- Test: `tests/unit/test_openrouter_executor.py`
- Test: `tests/unit/test_openrouter_worker.py`

**Interfaces:**
- Consumes: `OpenRouterExecutorSettings`, `OpenRouterExecutor.launch()`, `OpenRouterWorker`, worker `main()`.
- Produces: `OpenRouterExecutorSettings.max_turns: int`, `--max-turns <int>` worker launch argument, validated worker construction with the configured value.

- [ ] **Step 1: Write RED settings tests**
  - Assert default `max_turns == 120`.
  - Assert values below 1 and above 500 are rejected.
  - Assert `DEVELOPMENT_BRIDGE_OPENROUTER_MAX_TURNS=75` loads `75`.

- [ ] **Step 2: Run settings tests and observe RED**
  - `.venv/bin/python -m pytest tests/unit/test_settings.py -k openrouter -q`

- [ ] **Step 3: Write RED adapter/CLI propagation tests**
  - Assert launch includes `--max-turns` and configured value.
  - Assert worker CLI passes parsed value into `OpenRouterWorker(max_turns=...)`.

- [ ] **Step 4: Run propagation tests and observe RED**
  - `.venv/bin/python -m pytest tests/unit/test_openrouter_executor.py tests/unit/test_openrouter_worker.py -k 'max_turn or launch' -q`

- [ ] **Step 5: Implement minimum GREEN path**
  - Add `max_turns: int = Field(default=120, ge=1, le=500)`.
  - Parse `DEVELOPMENT_BRIDGE_OPENROUTER_MAX_TURNS`.
  - Add `--max-turns <value>` to launch arguments.
  - Parse CLI as `int` and pass into `OpenRouterWorker`.

- [ ] **Step 6: Run focused tests to GREEN**

### Task 2: Turn exhaustion is failure, not false success

**Files:**
- Modify: `app/executors/openrouter_worker.py`
- Test: `tests/unit/test_openrouter_worker.py`

**Interfaces:**
- Produces on exhaustion: `{"status":"ERROR","reason":"max_turns_exhausted","error":"Execution reached maximum turns limit.","usage":...}` and a non-zero worker process exit.

- [ ] **Step 1: Change the existing max-turns test to RED against desired semantics**
  - Keep deterministic `max_turns=2` infinite tool-calls.
  - Assert ERROR, reason, error text, and preserved usage.

- [ ] **Step 2: Run the single test and observe RED**
  - `.venv/bin/python -m pytest tests/unit/test_openrouter_worker.py::test_openrouter_worker_hits_max_turns_limit -q`

- [ ] **Step 3: Implement minimal exhaustion failure**
  - Return ERROR immediately after loop exhaustion; do not synthesize successful final response.
  - Leave normal SUCCESS behavior unchanged.

- [ ] **Step 4: Run worker tests to GREEN**

### Task 3: Verification and integration

- [ ] **Step 1: Focused gate**
  - `.venv/bin/python -m pytest tests/unit/test_openrouter_worker.py tests/unit/test_openrouter_executor.py tests/unit/test_settings.py tests/integration/test_mcp_executors.py tests/contract/test_executor_tools.py -q`

- [ ] **Step 2: Full gate**
  - `.venv/bin/python -m pytest -q`
  - `git diff --check`

- [ ] **Step 3: Self-review and commit**
  - Only scoped files plus this plan.
  - Commit `fix(executor): make OpenRouter turn budget configurable`.

- [ ] **Step 4: Independent review**
  - Review settings propagation, failure semantics, regression risk, and tests; repair/re-review any load-bearing finding.

- [ ] **Step 5: Live acceptance after local fast-forward and guarded restart**
  - Fast-forward local `main` only after approval; do not push.
  - Guarded restart is allowed for this runtime fix.
  - Confirm OpenRouter remains available/authenticated on `deepseek/deepseek-v4-flash-0731`.
  - Run a real bounded DeepSeek implementation smoke without a per-job turn override so runtime uses the configured default.
  - Require success or explicit failure; false SUCCESS on exhaustion is forbidden.

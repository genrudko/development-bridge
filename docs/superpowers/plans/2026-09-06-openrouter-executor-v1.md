# OpenRouter Executor v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit queueable `openrouter` executor able to run bounded repository coding tasks with allowlisted DeepSeek/Qwen models.

**Architecture:** Reuse ExecutorService → durable JobService. `OpenRouterExecutor` produces a standalone Python worker launch. The worker calls OpenRouter's OpenAI-compatible API and exposes only repository-confined read/write/search/process tools. Automatic Codex/Antigravity selection remains unchanged; OpenRouter is explicit-only in v1.

**Tech Stack:** Python stdlib HTTP/subprocess/pathlib, Pydantic, existing durable job engine, pytest.

**Spec:** This plan is the implementation spec.

## Global Constraints
- Default deny; disabled unless enabled.
- API key only through configured environment variable, never args/stdout/settings serialization.
- Default allowlist: `deepseek/deepseek-v4-flash-0731`, `qwen/qwen3-coder-next`.
- Explicit requested model must be allowlisted.
- Existing automatic executor selection unchanged.
- Reuse durable FIFO with `require_repository_idle=False`.
- File operations must stay inside repository and reject path/symlink escape.
- Process tool must reject push/deploy/credential/remote mutation and obvious network download commands.
- Local git status/diff/add/commit may be used only as bounded repository work; no push/remotes/gh/sudo/systemctl.
- Worker final stdout is bounded JSON with final response plus cumulative usage when returned by OpenRouter.
- No push, deploy, restart, PR, remote mutation, or secret output.

### Task 1: Contract/settings
**Files:** `app/executors/models.py`, `app/settings.py`, `app/tools/executors.py`; tests in `tests/unit/test_settings.py`, `tests/contract/test_executor_tools.py`.
- [x] Add RED tests for enum/model input/default-disabled settings/allowlist validation.
- [x] Verify RED.
- [x] Minimal implementation.
- [x] Verify GREEN.

### Task 2: Adapter/worker
**Files:** create `app/executors/openrouter.py`, `app/executors/openrouter_worker.py`; modify `app/executors/__init__.py`; tests `tests/unit/test_openrouter_executor.py`, `tests/unit/test_openrouter_worker.py`.
- [x] RED tests for disabled/missing-key probe, allowlist, launch env, path confinement, unsafe-command reject, tool loop, usage aggregation.
- [x] Verify RED.
- [x] Minimal implementation.
- [x] GREEN + nearest failure-path tests.

### Task 3: Service/container integration
**Files:** `app/executors/service.py`, `app/container.py`, `app/tools/executors.py`; tests `tests/unit/test_executor_service.py`, `tests/integration/test_mcp_executors.py`.
- [x] RED: status lists three executors; explicit OpenRouter queues busy; model persists; model on non-OpenRouter rejected; automatic selection unchanged.
- [x] Verify RED.
- [x] Wire adapter.
- [x] GREEN focused/integration tests.

### Task 4: Verification
- [x] Executor/settings/job focused suite.
- [x] Full pytest.
- [x] Ruff changed files if installed, otherwise record unavailable.
- [x] `git diff --check`, secret scan, status/diff review.
- [x] One bounded feature commit. Do not merge/restart/push.

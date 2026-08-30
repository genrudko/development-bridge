# Antigravity Executor Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add milestone-1 support for selecting and running authenticated Google Antigravity CLI tasks through Development Bridge's existing durable repository-job engine, with conservative status/quota routing and an operator-owned install/OAuth boundary.

**Architecture:** Add a focused `app/executors` service layer: an Antigravity probe/adapter produces normalized state and an existing `JobService.start_execution(...)` specification, while a selector owns routing policy. Persist executor attribution in the existing jobs tables and expose two hidden-capable MCP tools; do not create another queue, worker, scheduler, subprocess registry, or repository resolver.

**Tech Stack:** Python 3.12, asyncio subprocesses, frozen dataclasses/`StrEnum`, Pydantic 2 settings, SQLite, MCP 2.0, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-31-antigravity-executor-design.md`

## Global Constraints

- Milestone 1 only: operator bootstrap boundary, runtime probe, explicit Antigravity adapter, normalized quota/status, conservative selector, minimal Bridge surface, offline tests, and one live acceptance gate.
- Reuse `JobService`, `JobStore`, their queue/worker, per-repository admission, bounded output, timeout, cancellation, restart recovery, and repository registry; do not add a scheduler or run executor jobs in the status service.
- `agy` remains optional and disabled by default; implementation and offline tests must not install it, invoke an installer, or require it on `PATH`.
- The operator alone runs `curl -fsSL https://antigravity.google/cli/install.sh | bash`, launches `~/.local/bin/agy` in an SSH terminal, opens the OAuth URL locally, completes Google sign-in/2FA, and pastes the authorization code into that same terminal.
- Bridge must never accept, automate, intercept, proxy, persist, or log an OAuth URL, 2FA challenge, authorization code, Google credential, token, or Bridge-native GitHub credential.
- Use Antigravity headless mode with one process using `-p`, `--output-format json`, and `--print-timeout`. On this owner-operated VPS do not pass `--sandbox`: its Linux nsjail cannot initialize in the host environment. Never pass `--dangerously-skip-permissions`, `--continue`, or `--conversation`.
- Do not alter Git remotes, SSH configuration, `/etc/systemd`, external production deployments, or paid-overage settings; never expose Bridge GitHub credentials to the child environment.
- `/usage` and `/quota` currently open an interactive TUI. Production code must not scrape it. Until a documented structured quota source exists, fresh Antigravity quota is `unknown`; automatic routing therefore selects Codex.
- Explicit `antigravity` selection is allowed only when it is available, authenticated, not busy, and not known exhausted; explicit selection may proceed with `quota_state=unknown` and must record that state.
- Automatic selection chooses Antigravity only for a bounded `implementation` or `review` task when status is available, authenticated, idle, and `quota_state=ok`; `low`, `exhausted`, and `unknown` select Codex.
- Antigravity exhaustion, auth failure, crash, and timeout each produce one bounded terminal result with no automatic retry. Repository/test failures remain ordinary executor failures.
- Keep tools as MCP adapters only; all probing, normalization, selection, prompt construction, and submission logic belongs in services.

---

## File Map

- Create `app/executors/models.py`: executor names, request/result/status types, quota normalization, and public serialization.
- Create `app/executors/antigravity.py`: bounded probe runner, diagnostic redaction/classification, and conversion of one bounded task into a durable job execution request.
- Create `app/executors/selector.py`: explicit and automatic routing policy only.
- Create `app/executors/service.py`: repository-scoped orchestration across probe, selector, adapter, and `JobService`.
- Create `app/executors/__init__.py`: intentional public exports.
- Modify `app/settings.py`: frozen optional Antigravity settings, disabled by default.
- Modify `app/jobs/models.py`: executor attribution on job status/output.
- Modify `app/jobs/store.py`: additive executor metadata migration and persisted execution metadata.
- Modify `app/jobs/service.py`: accept executor metadata with an ad-hoc execution, preserve it through the existing queue, and expose repository busy state.
- Modify `app/container.py`: construct and expose one `ExecutorService` using the existing `JobService` and repository registry.
- Create `app/tools/executors.py`: thin `executor_status` and `executor_start` MCP adapters.
- Modify `app/tools/registry.py`: register executor tools on the full surface.
- Modify `app/tools/compact.py`: categorize executor tools but leave both off the compact allowlist so discovery/call uses `bridge_search -> bridge_schema -> bridge_call`.
- Modify `config/bridge.example.yaml`: disabled, explicit Antigravity configuration example.
- Create `docs/operations/antigravity-executor.md`: operator-only install/authentication and acceptance runbook with a hard pause before OAuth.
- Create `tests/unit/test_executor_models.py`, `tests/unit/test_antigravity_executor.py`, `tests/unit/test_executor_selector.py`, and `tests/unit/test_executor_service.py`.
- Modify `tests/unit/test_settings.py`, `tests/unit/test_job_store.py`, `tests/unit/test_job_execution_migration.py`, `tests/unit/test_job_service.py`, `tests/unit/test_compact_surface.py`, `tests/contract/test_tool_surface.py`, and `tests/integration/test_mcp_repository_exec.py`.
- Create `tests/contract/test_executor_tools.py` and `tests/integration/test_mcp_executors.py`.

### Task 1: Define normalized executor state and quota semantics

**Files:**
- Create: `app/executors/models.py`
- Create: `app/executors/__init__.py`
- Create: `tests/unit/test_executor_models.py`

**Interfaces:**
- Produces: `ExecutorName(StrEnum)` with `CODEX="codex"`, `ANTIGRAVITY="antigravity"`; `QuotaState(StrEnum)` with `OK`, `LOW`, `EXHAUSTED`, `UNKNOWN`; `TaskKind(StrEnum)` with `IMPLEMENTATION`, `REVIEW`, `OTHER`.
- Produces: `ExecutorStatus`, `ExecutorRequest`, `ExecutorLaunch`, and `ExecutorSelection` frozen slot dataclasses with the exact fields shown below.
- Produces: `normalize_quota(*, remaining_fraction: float | None, exhausted: bool = False) -> QuotaState` and `ExecutorStatus.public_dict() -> dict[str, object]`.

- [ ] **Step 1: Write the model tests**

```python
# tests/unit/test_executor_models.py
from datetime import UTC, datetime

import pytest

from app.executors.models import ExecutorName, ExecutorStatus, QuotaState, normalize_quota


@pytest.mark.parametrize(
    ("remaining", "exhausted", "expected"),
    [
        (None, False, QuotaState.UNKNOWN),
        (0.50, False, QuotaState.OK),
        (0.10, False, QuotaState.LOW),
        (0.0, False, QuotaState.EXHAUSTED),
        (0.75, True, QuotaState.EXHAUSTED),
    ],
)
def test_normalize_quota_is_conservative(remaining, exhausted, expected):
    assert normalize_quota(remaining_fraction=remaining, exhausted=exhausted) is expected


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan")])
def test_normalize_quota_rejects_invalid_fraction(value):
    with pytest.raises(ValueError):
        normalize_quota(remaining_fraction=value)


def test_executor_status_omits_absent_optional_values():
    status = ExecutorStatus(
        executor=ExecutorName.ANTIGRAVITY,
        available=True,
        authenticated=True,
        busy=False,
        model=None,
        quota_state=QuotaState.UNKNOWN,
        remaining_fraction=None,
        reset_time=None,
        last_error=None,
        last_success_at=datetime(2026, 8, 31, tzinfo=UTC),
        version="1.2.3",
    )
    assert status.public_dict() == {
        "executor": "antigravity", "available": True, "authenticated": True,
        "busy": False, "quota_state": "unknown",
        "last_success_at": "2026-08-31T00:00:00+00:00", "version": "1.2.3",
    }
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run: `pytest -q tests/unit/test_executor_models.py`

Expected: collection fails with `ModuleNotFoundError: No module named 'app.executors'`.

- [ ] **Step 3: Implement the exact types and validation**

```python
# app/executors/models.py
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ExecutorName(StrEnum):
    CODEX = "codex"
    ANTIGRAVITY = "antigravity"


class QuotaState(StrEnum):
    OK = "ok"
    LOW = "low"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


class TaskKind(StrEnum):
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    OTHER = "other"


def normalize_quota(*, remaining_fraction: float | None, exhausted: bool = False) -> QuotaState:
    if exhausted:
        return QuotaState.EXHAUSTED
    if remaining_fraction is None:
        return QuotaState.UNKNOWN
    if not math.isfinite(remaining_fraction) or not 0 <= remaining_fraction <= 1:
        raise ValueError("remaining_fraction must be between 0 and 1")
    if remaining_fraction == 0:
        return QuotaState.EXHAUSTED
    if remaining_fraction <= 0.20:
        return QuotaState.LOW
    return QuotaState.OK


@dataclass(frozen=True, slots=True)
class ExecutorStatus:
    executor: ExecutorName
    available: bool
    authenticated: bool
    busy: bool
    model: str | None
    quota_state: QuotaState
    remaining_fraction: float | None
    reset_time: datetime | None
    last_error: str | None
    last_success_at: datetime | None
    version: str | None

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "executor": self.executor.value,
            "available": self.available,
            "authenticated": self.authenticated,
            "busy": self.busy,
            "quota_state": self.quota_state.value,
        }
        for key, value in (("model", self.model), ("remaining_fraction", self.remaining_fraction),
                           ("last_error", self.last_error), ("version", self.version)):
            if value is not None:
                result[key] = value
        if self.reset_time is not None:
            result["reset_time"] = self.reset_time.isoformat()
        if self.last_success_at is not None:
            result["last_success_at"] = self.last_success_at.isoformat()
        return result


@dataclass(frozen=True, slots=True)
class ExecutorRequest:
    task: str
    task_kind: TaskKind
    executor: ExecutorName | None
    timeout_seconds: float
    output_limit_bytes: int
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ExecutorLaunch:
    executable: str
    arguments: tuple[str, ...]
    stdin: str | None
    environment_keys: tuple[str, ...]
    executor: ExecutorName
    model: str | None
    quota_state: QuotaState


@dataclass(frozen=True, slots=True)
class ExecutorSelection:
    executor: ExecutorName
    reason: str
```

Export every named type/function from `app/executors/__init__.py` using explicit imports and `__all__`.

- [ ] **Step 4: Run focused tests**

Run: `pytest -q tests/unit/test_executor_models.py`

Expected: `9 passed`.

- [ ] **Step 5: Commit the model boundary**

```bash
git add app/executors/models.py app/executors/__init__.py tests/unit/test_executor_models.py
git commit -m "feat: define executor status model"
```

### Task 2: Add disabled-by-default Antigravity configuration

**Files:**
- Modify: `app/settings.py:90-96,272-287`
- Modify: `config/bridge.example.yaml:9-12`
- Modify: `tests/unit/test_settings.py`

**Interfaces:**
- Produces: `AntigravityExecutorSettings` with `enabled: bool=False`, `executable: Path=Path("~/.local/bin/agy")`, `probe_timeout_seconds: float=20`, `task_timeout_seconds: float=900`, `output_limit_bytes: int=262_144`, `model: str | None=None`.
- Produces: `ExecutorSettings.antigravity` and `BridgeSettings.executors`.

- [ ] **Step 1: Add settings tests**

```python
def test_antigravity_executor_is_disabled_by_default():
    settings = BridgeSettings()
    assert settings.executors.antigravity.enabled is False
    assert settings.executors.antigravity.executable == Path("~/.local/bin/agy")


def test_antigravity_executor_settings_are_bounded():
    settings = BridgeSettings.model_validate({"executors": {"antigravity": {
        "enabled": True,
        "executable": "/opt/agy/bin/agy",
        "probe_timeout_seconds": 12,
        "task_timeout_seconds": 600,
        "output_limit_bytes": 131072,
        "model": "gemini-3.1-pro",
    }}})
    assert settings.executors.antigravity.executable == Path("/opt/agy/bin/agy")
    assert settings.executors.antigravity.model == "gemini-3.1-pro"


@pytest.mark.parametrize("field,value", [
    ("probe_timeout_seconds", 0), ("task_timeout_seconds", 3601),
    ("output_limit_bytes", 1023), ("output_limit_bytes", 1048577),
])
def test_antigravity_executor_rejects_out_of_bounds_values(field, value):
    with pytest.raises(ValidationError):
        BridgeSettings.model_validate({"executors": {"antigravity": {field: value}}})
```

- [ ] **Step 2: Verify the tests fail on the absent settings tree**

Run: `pytest -q tests/unit/test_settings.py -k antigravity`

Expected: failures report that `BridgeSettings` has no `executors` attribute.

- [ ] **Step 3: Implement settings and the example config**

Add frozen Pydantic models:

```python
class AntigravityExecutorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    executable: Path = Path("~/.local/bin/agy")
    probe_timeout_seconds: float = Field(default=20, gt=0, le=60)
    task_timeout_seconds: float = Field(default=900, gt=0, le=3600)
    output_limit_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)
    model: str | None = Field(default=None, min_length=1, max_length=128)


class ExecutorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    antigravity: AntigravityExecutorSettings = Field(default_factory=AntigravityExecutorSettings)
```

Add `executors: ExecutorSettings = Field(default_factory=ExecutorSettings)` to `BridgeSettings`. Add this commented example to `config/bridge.example.yaml`:

```yaml
# executors:
#   antigravity:
#     enabled: false
#     executable: ~/.local/bin/agy
#     probe_timeout_seconds: 20
#     task_timeout_seconds: 900
#     output_limit_bytes: 262144
#     model: gemini-3.1-pro
```

- [ ] **Step 4: Run settings tests**

Run: `pytest -q tests/unit/test_settings.py`

Expected: all tests pass.

- [ ] **Step 5: Commit configuration**

```bash
git add app/settings.py config/bridge.example.yaml tests/unit/test_settings.py
git commit -m "feat: configure optional Antigravity executor"
```

### Task 3: Implement the bounded Antigravity runtime probe and adapter

**Files:**
- Create: `app/executors/antigravity.py`
- Modify: `app/executors/__init__.py`
- Create: `tests/unit/test_antigravity_executor.py`

**Interfaces:**
- Consumes: `AntigravityExecutorSettings`, `ExecutorLaunch`, `ExecutorName`, `ExecutorStatus`, `QuotaState`.
- Produces: `ProcessResult(returncode: int, stdout: bytes, stderr: bytes, timed_out: bool, stdout_truncated: bool, stderr_truncated: bool)`.
- Produces: `ProcessRunner` protocol with `async run(argv: tuple[str, ...], *, cwd: Path, timeout_seconds: float, output_limit_bytes: int, env: dict[str, str]) -> ProcessResult`.
- Produces: `AsyncioProcessRunner.run(...)`, `AntigravityExecutor.probe(*, busy: bool) -> ExecutorStatus`, and `AntigravityExecutor.launch(repository: Repository, request: ExecutorRequest, status: ExecutorStatus) -> ExecutorLaunch`.

- [ ] **Step 1: Write fake-runner probe and launch tests**

Use a `FakeRunner` that records calls and returns queued `ProcessResult` values. Cover these exact cases:

```python
@pytest.mark.asyncio
async def test_probe_reports_missing_binary_without_auth_probe(tmp_path):
    executor, runner = make_executor(tmp_path, enabled=True, executable=tmp_path / "missing")
    status = await executor.probe(busy=False)
    assert status.public_dict() == {
        "executor": "antigravity", "available": False, "authenticated": False,
        "busy": False, "quota_state": "unknown", "last_error": "binary_missing",
    }
    assert runner.calls == []


@pytest.mark.asyncio
async def test_probe_classifies_auth_required_and_redacts_diagnostics(tmp_path):
    executor, runner = make_executor(tmp_path, results=[
        result(stdout=b"agy 1.2.3\n"),
        result(returncode=1, stderr=b"authentication required code=ABCD-1234 https://accounts.google.test/secret"),
    ])
    status = await executor.probe(busy=False)
    assert status.available is True and status.authenticated is False
    assert status.last_error == "auth_required"
    assert "ABCD" not in str(status.public_dict()) and "https://" not in str(status.public_dict())


@pytest.mark.asyncio
async def test_probe_marks_callable_runtime_with_unknown_quota(tmp_path):
    executor, runner = make_executor(tmp_path, results=[
        result(stdout=b"agy 1.2.3\n"),
        result(stdout=b'{"status":"SUCCESS","response":"BRIDGE_PROBE_OK","model":"gemini-3.1-pro"}'),
    ])
    status = await executor.probe(busy=True)
    assert status.available and status.authenticated and status.busy
    assert status.quota_state is QuotaState.UNKNOWN
    assert status.version == "agy 1.2.3"


def test_launch_builds_documented_headless_argv_and_bounded_prompt(repository):
    launch = executor.launch(repository, request, callable_unknown_status)
    assert launch.arguments == (
        "-p", build_expected_prompt(request.task), "--output-format", "json",
        "--sandbox", "--print-timeout", "900s", "--cwd", str(repository.root),
    )
    assert "AGENTS.md" in launch.arguments[1]
    assert "Do not change Git remotes" in launch.arguments[1]
    assert "Do not push or deploy" in launch.arguments[1]
    assert "Stop after running: pytest -q" in launch.arguments[1]
    assert launch.stdin is None
    assert launch.environment_keys == ("HOME", "SSH_CONNECTION")
```

Also test disabled configuration, version timeout, bounded 16 KiB redacted diagnostic, JSON `ERROR` normalization, an exhaustion diagnostic mapping to `quota_exhausted`, and that the launch environment contains only `PATH`, `LANG`, `LC_ALL`, `HOME`, and `SSH_CONNECTION` when present—never any key ending in `_TOKEN`, `_KEY`, or `_SECRET`.

- [ ] **Step 2: Run tests and verify imports fail**

Run: `pytest -q tests/unit/test_antigravity_executor.py`

Expected: collection fails because `app.executors.antigravity` does not exist.

- [ ] **Step 3: Implement the process runner**

`AsyncioProcessRunner` must use `asyncio.create_subprocess_exec(*argv, cwd=cwd, env=env, start_new_session=True, stdout=PIPE, stderr=PIPE)`, drain each stream concurrently in 8192-byte chunks while retaining at most `output_limit_bytes`, and on timeout send `SIGTERM` to the process group, wait up to two seconds, then send `SIGKILL`. Return one `ProcessResult`; do not retry.

- [ ] **Step 4: Implement probe classification and redaction**

Probe only when enabled and `Path(settings.executable).expanduser().is_file()` is true:

1. Run `(executable, "--version")`.
2. If successful, run the documented non-interactive authentication/callability check `(executable, "-p", "Reply with exactly BRIDGE_PROBE_OK", "--output-format", "json", "--sandbox", "--print-timeout", "15s")` with the configured probe timeout.
3. Parse a JSON object only; accept callability only when `status == "SUCCESS"` and `response.strip() == "BRIDGE_PROBE_OK"`.
4. Case-insensitively classify bounded stderr/status text containing `authentication required`, `sign in`, or `login required` as `auth_required`; `quota exhausted`, `resource exhausted`, or `rate limit` as `quota_exhausted`; timeout as `probe_timeout`; all other failures as `runtime_probe_failed`.
5. Never return raw probe stdout/stderr. `last_error` is one of the fixed classifications above. Quota remains `UNKNOWN` because `/usage` is TUI-only.

The sanitized probe environment helper must copy only `PATH`, `LANG`, `LC_ALL`, `HOME`, and `SSH_CONNECTION`. The launch requests only `HOME` and `SSH_CONNECTION` in `ExecutorLaunch.environment_keys`; Task 5 adds those keys to the durable worker's existing `PATH`/locale allowlist without persisting their values. The fixed error vocabulary, omission of raw diagnostics, and bounded runner jointly enforce secret non-disclosure.

- [ ] **Step 5: Implement prompt construction and launch**

Validate `status.available`, `status.authenticated`, `not status.busy`, and `status.quota_state is not EXHAUSTED`; otherwise raise `BridgeError(ErrorCode.POLICY_VIOLATION, message, details={"reason": reason})` using the exact `(reason, message)` pairs `("unavailable", "Antigravity executor is unavailable")`, `("auth_required", "Antigravity authentication is required")`, `("busy", "Antigravity executor is busy")`, and `("quota_exhausted", "Antigravity quota is exhausted")`. Build the prompt with this exact template, substituting the request task:

```text
You are executing one bounded Development Bridge repository task.
Read and obey AGENTS.md before changing files.
Task:
{task}
Invariants:
- Work only inside the current repository.
- Do not change Git remotes, SSH configuration, credentials, or repository registration.
- Do not expose secrets or Bridge-native GitHub credentials.
- Do not push or deploy.
- Do not start background schedulers or delegate the task.
Verification:
- Run the repository's targeted tests for the changed behavior.
- Stop after running: pytest -q
Stop conditions:
- Stop on an authentication, quota, permission, or environment blocker.
- Return concise evidence: files changed, tests run, and remaining blocker.
```

Reject tasks whose UTF-8 length is outside `1..65536`. Use configured `model` by inserting `("--model", model)` immediately before `--cwd` when non-null. Use `ceil(request.timeout_seconds)` for `--print-timeout`; cap it at configured `task_timeout_seconds`. Do not use any permission-bypass, conversation-resume, shell, or overage flag.

- [ ] **Step 6: Run adapter tests**

Run: `pytest -q tests/unit/test_antigravity_executor.py`

Expected: all tests pass, including timeout, truncation, redaction, and exact argv assertions.

- [ ] **Step 7: Commit the adapter**

```bash
git add app/executors/antigravity.py app/executors/__init__.py tests/unit/test_antigravity_executor.py
git commit -m "feat: probe and adapt Antigravity CLI"
```

### Task 4: Add conservative executor selection

**Files:**
- Create: `app/executors/selector.py`
- Modify: `app/executors/__init__.py`
- Create: `tests/unit/test_executor_selector.py`

**Interfaces:**
- Consumes: `ExecutorRequest`, `ExecutorStatus`, `ExecutorName`, `QuotaState`, `TaskKind`.
- Produces: `ExecutorSelector.select(request: ExecutorRequest, antigravity: ExecutorStatus) -> ExecutorSelection`.

- [ ] **Step 1: Write the routing matrix as parameterized tests**

```python
@pytest.mark.parametrize(
    ("override", "available", "authenticated", "busy", "quota", "kind", "expected", "reason"),
    [
        ("antigravity", True, True, False, "ok", "implementation", "antigravity", "explicit_override"),
        ("antigravity", True, True, False, "low", "review", "antigravity", "explicit_override_low_quota"),
        ("antigravity", True, True, False, "unknown", "review", "antigravity", "explicit_override_unknown_quota"),
        (None, True, True, False, "ok", "implementation", "antigravity", "automatic_suitable"),
        (None, True, True, False, "ok", "other", "codex", "automatic_unsuitable"),
        (None, True, True, False, "low", "implementation", "codex", "automatic_low_quota"),
        (None, True, True, False, "exhausted", "implementation", "codex", "automatic_quota_exhausted"),
        (None, True, True, False, "unknown", "implementation", "codex", "automatic_quota_unknown"),
        (None, False, False, False, "unknown", "implementation", "codex", "automatic_unavailable"),
        (None, True, False, False, "unknown", "implementation", "codex", "automatic_auth_required"),
        (None, True, True, True, "ok", "implementation", "codex", "automatic_busy"),
        ("codex", True, True, False, "ok", "implementation", "codex", "explicit_override"),
    ],
)
def test_selector_matrix(
    override, available, authenticated, busy, quota, kind, expected, reason
):
    request = ExecutorRequest(
        task="bounded task",
        task_kind=TaskKind(kind),
        executor=ExecutorName(override) if override is not None else None,
        timeout_seconds=300,
        output_limit_bytes=262_144,
        idempotency_key=None,
    )
    antigravity = ExecutorStatus(
        executor=ExecutorName.ANTIGRAVITY,
        available=available,
        authenticated=authenticated,
        busy=busy,
        model=None,
        quota_state=QuotaState(quota),
        remaining_fraction=None,
        reset_time=None,
        last_error=None,
        last_success_at=None,
        version=None,
    )
    selection = ExecutorSelector().select(request, antigravity)
    assert (selection.executor.value, selection.reason) == (expected, reason)
```

Add four separate tests asserting explicit Antigravity raises `BridgeError` with fixed `details["reason"]` values `unavailable`, `auth_required`, `busy`, and `quota_exhausted`. Add a test proving selection invokes no runner and has no retry loop.

- [ ] **Step 2: Verify tests fail before implementation**

Run: `pytest -q tests/unit/test_executor_selector.py`

Expected: collection fails because `app.executors.selector` does not exist.

- [ ] **Step 3: Implement the pure policy table**

Implement `select` as a pure synchronous method. Explicit Codex returns immediately. Explicit Antigravity validates the four hard gates in the order unavailable, auth, busy, exhausted; low/unknown remain allowed. Automatic selection checks suitability, then the same health gates, then requires exactly `QuotaState.OK`; every other path returns Codex with the tested reason. Do not inspect model quality, latency, cost, account plan, or environment variables.

- [ ] **Step 4: Run selector tests**

Run: `pytest -q tests/unit/test_executor_selector.py`

Expected: all routing cases pass.

- [ ] **Step 5: Commit selection policy**

```bash
git add app/executors/selector.py app/executors/__init__.py tests/unit/test_executor_selector.py
git commit -m "feat: select executors conservatively"
```

### Task 5: Persist executor attribution in the existing durable job engine

**Files:**
- Modify: `app/jobs/models.py:14-48`
- Modify: `app/jobs/store.py:26-104,192-268`
- Modify: `app/jobs/service.py:371-443,613-723`
- Modify: `tests/unit/test_job_store.py`
- Modify: `tests/unit/test_job_execution_migration.py`
- Modify: `tests/unit/test_job_service.py`
- Modify: `tests/integration/test_mcp_repository_exec.py`

**Interfaces:**
- Changes: `JobRecord` gains `executor: str | None = None`, `executor_model: str | None = None`, and `executor_quota_state: str | None = None`; `status_dict()` and `output_dict()` include present attribution.
- Changes: `JobService.start_execution(..., executor: str | None = None, executor_model: str | None = None, executor_quota_state: str | None = None, environment_keys: tuple[str, ...] = ()) -> JobRecord`.
- Produces: `JobService.repository_busy(repository: Repository) -> bool` backed by `JobStore.has_active_for_repository(...)`.
- Invariant: existing `repository_exec` calls remain valid and attributed fields are absent when null.

- [ ] **Step 1: Add failing persistence and compatibility tests**

Add tests that initialize a legacy database lacking all three columns, call `initialize()` twice, and assert `PRAGMA table_info(jobs)` contains `executor`, `executor_model`, and `executor_quota_state`. Start an attributed execution, rebuild `JobStore`, and assert status/output after restart contain:

```python
{
    "executor": "antigravity",
    "executor_model": "gemini-3.1-pro",
    "executor_quota_state": "unknown",
}
```

Extend `test_repository_exec_uses_durable_job_lifecycle_and_literal_argv` to assert existing raw jobs omit those keys. Add a unit test that `repository_busy` is false, true after queueing, and false after terminal completion.

- [ ] **Step 2: Run the focused tests and observe missing fields**

Run: `pytest -q tests/unit/test_job_store.py tests/unit/test_job_execution_migration.py tests/unit/test_job_service.py tests/integration/test_mcp_repository_exec.py`

Expected: new assertions fail because attribution is not accepted or persisted.

- [ ] **Step 3: Add the idempotent migration and row mapping**

After the existing `executescript`, read `PRAGMA table_info(jobs)` and execute each missing additive migration exactly once:

```sql
ALTER TABLE jobs ADD COLUMN executor TEXT;
ALTER TABLE jobs ADD COLUMN executor_model TEXT;
ALTER TABLE jobs ADD COLUMN executor_quota_state TEXT;
```

Extend `JobStore.create_execution(...)` to accept the three values and insert them into `jobs`. Include them and `environment_keys` in the canonical execution `payload_json` before hashing, so reusing an idempotency key with another executor/model/quota/environment specification raises the existing `IDEMPOTENCY_CONFLICT`. Add `execution_environment_keys(job_id: str) -> tuple[str, ...]`, returning the persisted list for ad-hoc executions and `()` for task profiles. Extend `_row(...)` and `JobRecord` serialization without changing the existing status enum or queue schema.

- [ ] **Step 4: Thread attribution through `JobService` without changing scheduling**

Validate executor values as non-empty strings of at most 128 characters when supplied. Validate `environment_keys` as a duplicate-free tuple containing only `HOME` and `SSH_CONNECTION`; raw `repository_exec` defaults to none. Add them to the execution payload and `create_execution` call. In `_execute`, load `store.execution_environment_keys(job_id)` and pass it to `_task_environment(extra_keys)`, whose fixed base remains `PATH`, `LANG`, and `LC_ALL`; it copies only requested allowed keys from `os.environ`. Do not change `_run_worker`, `_next_eligible_job`, `_active_repositories`, `_processes`, cancellation, timeout, output drain, artifact capture, or restart behavior. Implement:

```python
def repository_busy(self, repository: Repository) -> bool:
    self._require_execute(repository)
    return self._require_store().has_active_for_repository(
        repository.project_id, repository.id
    )
```

- [ ] **Step 5: Run durable-job regression tests**

Run: `pytest -q tests/unit/test_job_store.py tests/unit/test_job_execution_migration.py tests/unit/test_job_service.py tests/unit/test_job_scheduler_concurrency.py tests/unit/test_durable_job_waiters.py tests/integration/test_mcp_repository_exec.py tests/integration/test_mcp_jobs.py`

Expected: all tests pass and the scheduler concurrency tests remain unchanged.

- [ ] **Step 6: Commit durable attribution**

```bash
git add app/jobs/models.py app/jobs/store.py app/jobs/service.py tests/unit/test_job_store.py tests/unit/test_job_execution_migration.py tests/unit/test_job_service.py tests/integration/test_mcp_repository_exec.py
git commit -m "feat: persist executor job attribution"
```

### Task 6: Orchestrate probing, selection, and durable submission

**Files:**
- Create: `app/executors/service.py`
- Modify: `app/executors/__init__.py`
- Modify: `app/container.py:1-45,47-88,334-390`
- Create: `tests/unit/test_executor_service.py`

**Interfaces:**
- Consumes: repository registry-resolved `Repository`, `JobService`, `AntigravityExecutor`, `ExecutorSelector`, `ExecutorRequest`.
- Produces: `async ExecutorService.status(repository: Repository) -> dict[str, object]` and `async ExecutorService.start(repository: Repository, request: ExecutorRequest, request_id: str) -> JobRecord`.
- Changes: `ApplicationContainer` gains `executors: ExecutorService`.

- [ ] **Step 1: Write orchestration tests with fake probe/selector/jobs**

Cover:

1. `status` passes `jobs.repository_busy(repository)` into the Antigravity probe and returns `{"executors": [codex_status, antigravity_status]}`.
2. Explicit Antigravity submits exactly one existing durable execution using adapter launch fields and persisted executor/model/quota attribution.
3. Exhausted Antigravity raises before submission and `jobs.start_execution` call count remains zero.
4. Automatic selection with unknown quota returns `BridgeError(ErrorCode.POLICY_VIOLATION, "Automatic selection chose Codex, whose adapter is not part of milestone 1", details={"selection_reason": "automatic_quota_unknown"})`; it does not silently execute arbitrary Codex shell commands.
5. Explicit Codex returns the same fixed milestone-boundary error. This keeps selection observable without inventing a Codex adapter in this milestone.
6. A second start while the repository has an active job fails the explicit busy gate and creates no second job.

- [ ] **Step 2: Verify service tests fail before implementation**

Run: `pytest -q tests/unit/test_executor_service.py`

Expected: collection fails because `app.executors.service` does not exist.

- [ ] **Step 3: Implement the service**

`status` asynchronously returns a known-good logical Codex status (`available=True`, `authenticated=True`, current repository busy flag, quota `unknown`) plus the fresh Antigravity probe. `start` probes once, selects once, and either raises the fixed Codex milestone-boundary error or calls:

```python
await self._jobs.start_execution(
    repository,
    launch.executable,
    launch.arguments,
    request_id,
    timeout_seconds=request.timeout_seconds,
    output_limit_bytes=request.output_limit_bytes,
    stdin=launch.stdin,
    idempotency_key=request.idempotency_key,
    executor=launch.executor.value,
    executor_model=launch.model,
    executor_quota_state=launch.quota_state.value,
    environment_keys=launch.environment_keys,
)
```

There is no retry/fallback after submission. A failed Antigravity process is read later through ordinary `job_status`/`job_output`; the coordinator decides whether to create another job.

- [ ] **Step 4: Wire the service in the container**

Construct one `AsyncioProcessRunner`, `AntigravityExecutor(configured.executors.antigravity, runner)`, `ExecutorSelector`, and `ExecutorService(jobs, antigravity, selector)` after `jobs` is created. Add it to `ApplicationContainer`; do not add global mutable status or another lifecycle hook.

- [ ] **Step 5: Run orchestration and container tests**

Run: `pytest -q tests/unit/test_executor_service.py tests/unit/test_job_service.py tests/integration/test_startup_validation.py`

Expected: all tests pass.

- [ ] **Step 6: Commit orchestration**

```bash
git add app/executors/service.py app/executors/__init__.py app/container.py tests/unit/test_executor_service.py
git commit -m "feat: submit selected executor jobs"
```

### Task 7: Expose the minimal hidden-capable Bridge surface

**Files:**
- Create: `app/tools/executors.py`
- Modify: `app/tools/registry.py:1-60`
- Modify: `app/tools/compact.py:25-65`
- Create: `tests/contract/test_executor_tools.py`
- Modify: `tests/contract/test_tool_surface.py`
- Modify: `tests/unit/test_compact_surface.py`
- Create: `tests/integration/test_mcp_executors.py`

**Interfaces:**
- Produces hidden-capable tool `executor_status(project_id: str, repository_id: str) -> {executors: list[ExecutorStatus]}`.
- Produces hidden-capable tool `executor_start(project_id: str, repository_id: str, task: str, task_kind: "implementation"|"review"|"other", executor?: "codex"|"antigravity", timeout_seconds?: number, output_limit_bytes?: int, idempotency_key?: str) -> JobRecord.status_dict()`.
- Invariant: neither tool is added to `COMPACT_VISIBLE_TOOLS`; compact coordinators discover and invoke them through existing meta-tools.

- [ ] **Step 1: Write contract tests for exact closed schemas**

Assert the full registry adds exactly `executor_status` and `executor_start`; update the expected full count from 93 to 95. Assert `executor_status.required == ["project_id", "repository_id"]`. Assert `executor_start.required == ["project_id", "repository_id", "task", "task_kind"]`, `task.maxLength == 65536`, enum values are exact, timeout is `(0, 3600]`, output is `[1024, 1048576]`, and both schemas set `additionalProperties: false`.

- [ ] **Step 2: Write integration tests**

Build a container with a fake `agy` executable path and replace only `container.executors._antigravity._runner` with the deterministic fake runner. Through an MCP `ClientSession`:

1. Call `executor_status` and assert normalized keys contain no raw fake diagnostic or credential marker.
2. Call explicit `executor_start`, wait through existing `job_status`, read existing `job_output`, and assert executor attribution is `antigravity`.
3. Return quota exhaustion from the fake runner, call explicit start, assert the error code is `POLICY_VIOLATION`, and assert no job was created.
4. Configure compact surface, prove `executor_status` and `executor_start` are absent from visible definitions, then use `bridge_search`, `bridge_schema`, and `bridge_call` to reach `executor_status`.

- [ ] **Step 3: Verify the new tests fail**

Run: `pytest -q tests/contract/test_executor_tools.py tests/contract/test_tool_surface.py tests/integration/test_mcp_executors.py tests/unit/test_compact_surface.py`

Expected: failures show the two tools are not registered.

- [ ] **Step 4: Implement thin tool adapters**

Resolve repositories only through `container.projects.repositories.get(...)`. Convert string enum inputs to the Task 1 enums, apply settings defaults (`task_timeout_seconds`, `output_limit_bytes`), call `container.executors`, and wrap results with `success(...)`/`to_mcp_result(...)`. Do not launch processes, inspect files, select executors, or access SQLite in the tool module.

Register the new tool tuple before `job_tools(container)` in `build_tool_registry`. Add `executor_` to compact `_category` as `executors`; do not modify `COMPACT_VISIBLE_TOOLS`.

- [ ] **Step 5: Run contract and MCP tests**

Run: `pytest -q tests/contract/test_executor_tools.py tests/contract/test_tool_surface.py tests/unit/test_compact_surface.py tests/integration/test_mcp_executors.py tests/integration/test_mcp_repository_exec.py`

Expected: all tests pass; raw `repository_exec` remains backward compatible.

- [ ] **Step 6: Commit the Bridge surface**

```bash
git add app/tools/executors.py app/tools/registry.py app/tools/compact.py tests/contract/test_executor_tools.py tests/contract/test_tool_surface.py tests/unit/test_compact_surface.py tests/integration/test_mcp_executors.py
git commit -m "feat: expose executor status and submission"
```

### Task 8: Document operator bootstrap and execute offline acceptance

**Files:**
- Create: `docs/operations/antigravity-executor.md`

**Interfaces:**
- Produces: operator runbook separating offline deployment from secret-bearing interactive OAuth and one-shot live acceptance.
- Stop condition: implementation agent stops before the SSH OAuth command and hands control to the operator; it does not install `agy` or run live acceptance autonomously.

- [ ] **Step 1: Write the runbook with exact commands and expected evidence**

The runbook must contain these ordered sections and commands:

1. **Offline release verification**

```bash
pytest -q
git diff --check
```

Expected: the full suite passes and `git diff --check` emits no output.

2. **Operator installation (operator terminal only)**

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
~/.local/bin/agy --version
```

Expected: an `agy` version is printed. Bridge never runs the installer.

3. **Hard stop for OAuth**

Display this exact warning: `STOP: the operator must now run ~/.local/bin/agy in the SSH terminal, open the printed URL locally, complete Google sign-in/2FA, paste the authorization code only into that SSH terminal, exit the TUI, and confirm completion. Do not paste the URL or code into Bridge, chat, logs, or repository files.`

4. **Post-auth configuration**

```yaml
executors:
  antigravity:
    enabled: true
    executable: ~/.local/bin/agy
    probe_timeout_seconds: 20
    task_timeout_seconds: 900
    output_limit_bytes: 262144
```

Restart only the explicitly named non-production deployment using its established operator procedure; the runbook must state that repository agents may not edit `/etc/systemd` or guess a service name.

5. **One-shot live acceptance**

Use `bridge_search(query="executor")`, `bridge_schema(tool_name="executor_status")`, then `bridge_call` for `executor_status`. Verify `available=true`, `authenticated=true`, and `quota_state=unknown`. The runbook must explain that this unknown state is expected while `/usage` remains TUI-only and automatic routing must choose Codex.

Call `executor_start` exactly once with explicit `executor="antigravity"`, `task_kind="review"`, and the harmless task `Read AGENTS.md and report the current branch name and whether git status is clean. Do not modify files, commit, push, or deploy.` Wait with the existing durable wake/status flow, then verify terminal output, no worktree changes, and `executor="antigravity"` attribution. Do not repeat if it passes.

6. **Failure handling**

Document fixed classifications: missing binary → `binary_missing`; expired session → `auth_required` and operator repeats SSH OAuth; exhausted → `quota_exhausted` with no retry; unknown quota → automatic Codex; timeout/crash → one failed job; repository/test error → ordinary job evidence. Explicitly prohibit enabling `useG1Credits`, permission bypasses, or retry loops.

- [ ] **Step 2: Review documentation for secret and deployment boundaries**

Run: `rg -n "authorization code|2FA|installer|production|useG1Credits|dangerously-skip-permissions|retry" docs/operations/antigravity-executor.md`

Expected: every occurrence states an operator-only action or explicit prohibition; no command contains an OAuth URL/code or credential value.

- [ ] **Step 3: Run complete offline verification**

Run: `pytest -q`

Expected: the full Development Bridge suite passes.

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only milestone-1 implementation/test/docs files are modified; pre-existing `share_transcript_6a921405.json` and `tmp/` remain untracked and untouched.

- [ ] **Step 4: Commit the runbook**

```bash
git add docs/operations/antigravity-executor.md
git commit -m "docs: add Antigravity operator runbook"
```

- [ ] **Step 5: Stop for operator OAuth and acceptance**

Report offline test evidence and the exact commit SHA, then stop. Do not install `agy`, start its TUI, request OAuth material, modify a deployment, or perform the live call until the operator confirms installation/authentication and names the non-production deployment/repository scope.

## Final Milestone Review

- [ ] Confirm every process launch is either the probe runner or the unchanged `JobService` worker; there is no new queue, scheduler, background worker, or process registry.
- [ ] Confirm automatic `unknown`, `low`, and `exhausted` quota paths select Codex and cannot enqueue Antigravity.
- [ ] Confirm explicit exhausted/auth-required/busy/unavailable paths enqueue nothing and make no retry.
- [ ] Confirm all normalized diagnostics use fixed classifications and no raw stderr/stdout enters status, logs, audit details, or errors.
- [ ] Confirm child environments exclude GitHub tokens, API keys, and secret variables.
- [ ] Confirm `executor_start` records executor/model/quota attribution in both job status and output after restart.
- [ ] Confirm compact mode reaches the two new tools only through `bridge_search -> bridge_schema -> bridge_call`.
- [ ] Confirm legacy `repository_exec`, task profiles, scheduler concurrency, cancellation, artifacts, and durable waiters remain green.
- [ ] Confirm no production deployment, installer, OAuth flow, Git remote, SSH configuration, paid-overage setting, `share_transcript_6a921405.json`, or `tmp/` was changed.
- [ ] Stop milestone 1 after the single successful live acceptance; reliability/cost/latency scoring and richer automatic routing belong to milestone 2.

# Antigravity Executor Operator Runbook

## 1. Offline release verification

Run inside the Development Bridge checkout:

```bash
pytest -q
git diff --check
```

Expected evidence: the full suite passes and `git diff --check` emits no output.

## 2. Operator installation (operator terminal only)

Only the operator may run the installer in their terminal. Bridge never runs it.

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
~/.local/bin/agy --version
```

Expected evidence: an `agy` version is printed.

## 3. Hard stop for OAuth

STOP: the operator must now run ~/.local/bin/agy in the SSH terminal, open the printed URL locally, complete Google sign-in/2FA, paste the authorization code only into that SSH terminal, exit the TUI, and confirm completion. Do not paste the URL or code into Bridge, chat, logs, or repository files.

## 4. Post-auth configuration

Configure only the explicitly named non-production deployment:

```yaml
executors:
  antigravity:
    enabled: true
    executable: ~/.local/bin/agy
    probe_timeout_seconds: 20
    task_timeout_seconds: 900
    output_limit_bytes: 262144
```

Restart that non-production deployment using its established operator procedure. Repository agents may not edit `/etc/systemd` or guess a service name.

## 5. One-shot live acceptance

Use `bridge_search(query="executor")`, `bridge_schema(tool_name="executor_status")`, then `bridge_call` for `executor_status`. Verify `available=true`, `authenticated=true`, and `quota_state=unknown`. The unknown quota is expected while `/usage` remains TUI-only; production does not scrape it, and automatic routing must choose Codex.

Call `executor_start` exactly once with explicit `executor="antigravity"`, `task_kind="review"`, and this harmless task:

> Read AGENTS.md and report the current branch name and whether git status is clean. Do not modify files, commit, push, or deploy.

Wait using the existing durable wake/status flow. Verify terminal output, no worktree changes, and `executor="antigravity"` attribution. Do not repeat the live acceptance if it passes.

## 6. Failure handling

- Missing binary: `binary_missing`.
- Expired session: `auth_required`; the operator repeats SSH OAuth and keeps the 2FA challenge and authorization code in that terminal only.
- Exhausted quota: `quota_exhausted`; do not retry.
- Unknown quota: automatic routing chooses Codex.
- Timeout or crash: one failed job; no retry loop.
- Repository or test error: ordinary job evidence, not an infrastructure classification.

Never enable `useG1Credits`, use `--dangerously-skip-permissions` or another permission bypass, or add automatic retry loops.

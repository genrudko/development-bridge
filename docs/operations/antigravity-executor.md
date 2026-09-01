# Antigravity Executor Operator Runbook

All Antigravity coding/review jobs also follow `docs/operations/executor-operating-contract.md`, including VPS-first execution, no redundant tool calls, no automatic retry, and the mandatory pre-handoff debug sweep.

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

For this owner-operated VPS, set Antigravity CLI's tool execution policy to `always-proceed` and do not use its Linux terminal sandbox. Bridge still supplies the repository cwd, bounded prompt, timeout, output cap, and a stripped child environment.

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

Never enable `useG1Credits`, pass `--dangerously-skip-permissions`, or add automatic retry loops. The owner-operated VPS uses Antigravity's native `always-proceed` policy instead of the unavailable Linux terminal sandbox.

## 7. Structured quota capture

Antigravity's documented custom status-line protocol sends a JSON state payload to a configured command on stdin. The payload includes quota buckets with `remaining_fraction`, `reset_time`, and `reset_in_seconds`. Configure the deployment status line to run `app/executors/antigravity_quota.py --cache <quota_cache_path>` using an absolute Python/script path. The helper stores only quota/model/tier metadata, not the account email or transcript.

`executor_status` reads the fresh cache after its callable `agy` probe. The most constraining matching `gemini-*` bucket is used for Gemini models; if no model family can be matched, the most constraining valid bucket is used conservatively. Cache older than `quota_cache_max_age_seconds` is treated as `unknown`.

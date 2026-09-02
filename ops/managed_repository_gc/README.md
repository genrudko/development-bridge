# Managed repository GC

Development Bridge managed reference clones are disposable cache, but writable forks are
not. The runtime records one of three retention policies per logical repository:

- `pinned`: never collect automatically (all writable managed forks are forced pinned);
- `cache`: collect only after 30 days without repository access;
- `ephemeral`: collect after 14 days without repository access.

Every normal managed-repository lookup refreshes `last_used_at`, throttled to one manifest
write per repository per minute. Storage aliases share one physical Git checkout; GC only
reclaims a physical storage group when **every** logical alias sharing it is old enough,
read-only, unpinned and clean.

`repository_gc_plan` is read-only. `repository_gc_apply` additionally requires
`confirm=true` and executes through `JobService.run_when_globally_idle`, so durable queued
or running work blocks deletion. During the short apply phase new managed-repository
lookups receive a retryable `JOB_BUSY` instead of racing a removal.

The user timer calls the live compact MCP endpoint through `bridge_call` once daily at
05:30 plus up to 20 minutes randomized delay. It removes at most four physical groups per
run. A busy Bridge is treated as a normal skipped maintenance window.

Install the timer with:

```bash
ops/managed_repository_gc/install-user.sh
```

import pytest

from app.api.errors import BridgeError
from app.executors.models import ExecutorName, ExecutorRequest, ExecutorStatus, QuotaState, TaskKind
from app.executors.selector import ExecutorSelector


def request(override=None, kind="implementation"):
    return ExecutorRequest("bounded", TaskKind(kind), ExecutorName(override) if override else None, 300, 262144, None)


def status(available=True, authenticated=True, busy=False, quota="ok"):
    return ExecutorStatus(ExecutorName.ANTIGRAVITY, available, authenticated, busy, None,
        QuotaState(quota), None, None, None, None, None)


@pytest.mark.parametrize(("override", "available", "authenticated", "busy", "quota", "kind", "expected", "reason"), [
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
])
def test_selector_matrix(override, available, authenticated, busy, quota, kind, expected, reason):
    selected = ExecutorSelector().select(request(override, kind), status(available, authenticated, busy, quota))
    assert (selected.executor.value, selected.reason) == (expected, reason)


@pytest.mark.parametrize(("changes", "reason"), [
    ({"available": False}, "unavailable"), ({"authenticated": False}, "auth_required"),
    ({"busy": True}, "busy"), ({"quota": "exhausted"}, "quota_exhausted"),
])
def test_explicit_antigravity_rejects_hard_gate(changes, reason):
    with pytest.raises(BridgeError) as caught:
        ExecutorSelector().select(request("antigravity"), status(**changes))
    assert caught.value.details["reason"] == reason

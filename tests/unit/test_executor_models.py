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
        "executor": "antigravity",
        "available": True,
        "authenticated": True,
        "busy": False,
        "quota_state": "unknown",
        "last_success_at": "2026-08-31T00:00:00+00:00",
        "version": "1.2.3",
    }

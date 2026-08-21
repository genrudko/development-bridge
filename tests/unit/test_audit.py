import logging

import pytest

from app.audit import AuditEvent, AuditOutcome, CompositeAuditSink, LoggingAuditSink


class RecordingSink:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_composite_audit_emits_to_all_sinks():
    first = RecordingSink()
    second = RecordingSink()
    event = AuditEvent(
        request_id="req_1",
        tool="bridge_info",
        outcome=AuditOutcome.SUCCESS,
        duration_ms=1,
    )
    await CompositeAuditSink([first, second]).emit(event)
    assert first.events == [event]
    assert second.events == [event]


@pytest.mark.asyncio
async def test_logging_audit_is_structured(caplog):
    caplog.set_level(logging.INFO, logger="development_bridge.audit")
    event = AuditEvent(
        request_id="req_2",
        tool="project_list",
        outcome=AuditOutcome.SUCCESS,
        duration_ms=2,
    )
    await LoggingAuditSink().emit(event)
    assert '"request_id": "req_2"' in caplog.text


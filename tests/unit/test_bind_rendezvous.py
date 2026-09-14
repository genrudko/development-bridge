from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from app.api.errors import BridgeError, ErrorCode
from app.coordinator.bind_rendezvous import BindRendezvousService
from app.coordinator.review_gpt_transport import RendezvousResolution
from app.coordinator.route_control import RouteControlService
from app.coordinator.route_control_diagnostics import RouteControlTraceStore
from app.coordinator.routes import RouteRegistry


class Clock:
    def __init__(self, value: float = 1_800_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class Resolver:
    def __init__(self, *items: object) -> None:
        self.items = list(items)
        self.markers: list[str] = []

    async def __call__(self, marker: str) -> RendezvousResolution:
        self.markers.append(marker)
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, RendezvousResolution)
        return item


@pytest.fixture
def setup(tmp_path: Path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.bootstrap(
        "bridge",
        "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/old",
        "telegram-bridge-g0",
    )
    control = RouteControlService(registry, RouteControlTraceStore(tmp_path / "traces"))
    return registry, control


def service(setup, resolver, clock, **kwargs):
    registry, control = setup
    return BindRendezvousService(
        registry, control, resolver=resolver, clock=clock, poll_interval_seconds=0.01, **kwargs
    )


def test_prepare_marker_has_shape_entropy_uniqueness_and_thirty_minute_ttl(setup):
    clock = Clock()
    first = service(setup, Resolver(), clock).prepare("bridge")
    clock.advance(1801)
    second = service(setup, Resolver(), clock).prepare("bridge")
    assert re.fullmatch(r"DBRIDGE_BIND bnd_[A-Za-z0-9_-]{22,}", first["marker"])
    assert first["marker"] != second["marker"]
    raw = first["marker"].removeprefix("DBRIDGE_BIND bnd_")
    assert len(raw) >= 22  # URL-safe encoding of at least 128 random bits.
    durable = json.loads((setup[0].path.parent / "bind-rendezvous.json").read_text())
    assert durable["records"]["bridge"]["expires_at"] - durable["records"]["bridge"]["created_at"] == 1800
    assert set(first) == {"route_id", "state", "generation", "marker", "expires_at"}


def test_prepare_rejects_second_live_rendezvous_and_replaces_terminal(setup):
    clock = Clock()
    svc = service(setup, Resolver(), clock)
    first = svc.prepare("bridge")
    with pytest.raises(BridgeError) as exc_info:
        svc.prepare("bridge")
    assert exc_info.value.code == ErrorCode.POLICY_VIOLATION
    svc._records["bridge"]["state"] = "failed"
    svc._records["bridge"]["terminal_error_code"] = "TEST"
    svc._save()
    assert svc.prepare("bridge")["marker"] != first["marker"]


def test_prepare_replaces_stale_generation_rendezvous(setup):
    registry, _ = setup
    clock = Clock()
    svc = service(setup, Resolver(), clock)
    first = svc.prepare("bridge")
    data = registry._load()
    data["routes"]["bridge"]["generation"] = 1
    registry._save(data)
    second = svc.prepare("bridge")
    assert second["generation"] == 1
    assert second["marker"] != first["marker"]


@pytest.mark.asyncio
async def test_retry_sequence_zero_transient_and_owner_input_resume(setup):
    clock = Clock()
    resolver = Resolver(
        RendezvousResolution("zero"),
        RendezvousResolution("transient"),
        RendezvousResolution("owner_input_required"),
        RendezvousResolution("zero"),
        RendezvousResolution("zero"),
    )
    svc = service(setup, resolver, clock)
    svc.prepare("bridge", allow_project_change=True)
    for expected_state, delay in zip(
        ["pending", "pending", "owner_input_required", "pending", "pending"],
        [5, 15, 30, 60, 120],
    ):
        await svc.run_due_once()
        current = svc.status("bridge")
        assert current["state"] == expected_state
        assert current["next_attempt_at_epoch"] - clock() == delay
        clock.advance(delay)
    assert svc.status("bridge")["attempt_count"] == 5


@pytest.mark.asyncio
async def test_restart_restores_next_attempt_and_policy(setup):
    clock = Clock()
    first = service(setup, Resolver(RendezvousResolution("zero")), clock)
    first.prepare("bridge", allow_project_change=True)
    await first.run_due_once()
    restored = service(setup, Resolver(RendezvousResolution("zero")), clock)
    status = restored.status("bridge")
    assert status["attempt_count"] == 1
    assert status["next_attempt_at_epoch"] == clock() + 5
    assert restored._records["bridge"]["allow_project_change"] is True


@pytest.mark.asyncio
async def test_ambiguity_and_expiry_are_terminal(setup):
    clock = Clock()
    ambiguous = service(setup, Resolver(RendezvousResolution("ambiguous")), clock)
    ambiguous.prepare("bridge")
    await ambiguous.run_due_once()
    assert ambiguous.status("bridge")["terminal_error_code"] == "RENDEZVOUS_AMBIGUOUS"
    ambiguous.prepare("bridge")
    clock.advance(1800)
    await ambiguous.run_due_once()
    assert ambiguous.status("bridge")["terminal_error_code"] == "RENDEZVOUS_EXPIRED"


@pytest.mark.asyncio
async def test_generation_race_fails_closed_without_binding(setup):
    registry, _ = setup
    clock = Clock()
    candidate = "https://chatgpt.com/g/g-p-11111111111111111111111111111111/c/new"
    svc = service(setup, Resolver(RendezvousResolution("unique", candidate)), clock)
    svc.prepare("bridge")
    data = registry._load()
    data["routes"]["bridge"]["generation"] = 1
    registry._save(data)
    await svc.run_due_once()
    assert svc.status("bridge")["terminal_error_code"] == "RENDEZVOUS_GENERATION_CHANGED"
    assert registry.resolve("bridge")["conversation_id"] == "old"


@pytest.mark.asyncio
async def test_unique_uses_internal_guarded_commit_once_and_propagates_policy(setup, monkeypatch):
    _, control = setup
    clock = Clock()
    candidate = "https://chatgpt.com/g/g-p-22222222222222222222222222222222/c/new"
    calls: list[tuple] = []
    original_prepare = control.prepare_bind
    original_commit = control.complete_ephemeral_bind
    monkeypatch.setattr(control, "prepare_bind", lambda route_id, **kw: (calls.append(("prepare", route_id, kw)), original_prepare(route_id, **kw))[1])
    monkeypatch.setattr(control, "complete_ephemeral_bind", lambda op, url: (calls.append(("commit", op)), original_commit(op, url))[1])
    svc = service(setup, Resolver(RendezvousResolution("unique", candidate)), clock)
    svc.prepare("bridge", allow_project_change=True)
    await svc.run_due_once()
    assert svc.status("bridge")["state"] == "bound"
    await svc.run_due_once()
    assert [item[0] for item in calls] == ["prepare", "commit"]
    assert calls[0][2] == {"session_id": None, "allow_project_change": True, "bootstrap_if_missing": False}
    diagnostic = control.trace_store.latest_diagnostic_id_for_route("bridge")
    assert control.trace_store.get_return_target(diagnostic) is None
    assert "operation_id" not in json.dumps(svc.status("bridge"))


@pytest.mark.asyncio
async def test_physical_identity_token_and_exception_are_never_persisted(setup):
    clock = Clock()
    secret = "https://chatgpt.com/c/physical-secret"
    svc = service(setup, Resolver(RuntimeError(secret)), clock)
    prepared = svc.prepare("bridge")
    await svc.run_due_once()
    raw = (setup[0].path.parent / "bind-rendezvous.json").read_text()
    assert secret not in raw
    assert "operation_id" not in raw and "token" not in raw and "candidate" not in raw
    assert prepared["marker"] not in json.dumps(svc.status("bridge"))
    assert svc.status("bridge")["state"] == "pending"


def test_load_validation_fails_closed_and_save_is_atomic(setup, monkeypatch):
    clock = Clock()
    path = setup[0].path.parent / "bind-rendezvous.json"
    path.write_text('{"version":1,"records":{"bridge":{"candidate_url":"bad"}}}')
    with pytest.raises(BridgeError) as exc_info:
        service(setup, Resolver(), clock)
    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    path.unlink()
    svc = service(setup, Resolver(), clock)
    replaced = []
    monkeypatch.setattr("app.coordinator.bind_rendezvous.os.replace", lambda src, dst: replaced.append((src, dst)))
    svc.prepare("bridge")
    assert replaced and replaced[-1][1] == path


@pytest.mark.asyncio
async def test_start_stop_are_idempotent_and_worker_cancels_cleanly(setup):
    clock = Clock()
    svc = service(setup, Resolver(RendezvousResolution("zero")), clock)
    svc.prepare("bridge")
    await svc.start()
    task = svc._task
    await svc.start()
    assert svc._task is task
    await asyncio.sleep(0)
    await svc.stop()
    await svc.stop()
    assert svc._task is None and task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_lock_wait_expiry_and_cancellation_never_bind(setup, cancel):
    registry, _ = setup
    clock = Clock()
    resolver = Resolver(RendezvousResolution("unique", "https://chatgpt.com/c/new"))
    svc = service(setup, resolver, clock)
    svc.prepare("bridge", allow_project_change=True)
    before = registry.path.read_bytes()
    async with registry.route_lock("bridge"):
        task = asyncio.create_task(svc.run_due_once())
        await asyncio.sleep(0)
        assert len(resolver.markers) == 1 and not task.done()
        clock.advance(1800)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    if not cancel:
        await task
    else:
        await svc.run_due_once()
    assert registry.path.read_bytes() == before
    assert svc.status("bridge")["terminal_error_code"] == "RENDEZVOUS_EXPIRED"


@pytest.mark.asyncio
async def test_unique_never_saves_pending_physical_candidate(setup, monkeypatch):
    registry, _ = setup
    saves = []
    original = registry._save

    def capture(data):
        saves.append(json.loads(json.dumps(data)))
        original(data)

    monkeypatch.setattr(registry, "_save", capture)
    svc = service(setup, Resolver(RendezvousResolution("unique", "https://chatgpt.com/c/ephemeral-target")), Clock())
    svc.prepare("bridge", allow_project_change=True)
    await svc.run_due_once()
    assert svc.status("bridge")["state"] == "bound"
    for saved in saves:
        assert "candidate_url" not in json.dumps(saved)
        # Identity is allowed only in the final active binding, with token consumed.
        active = saved.pop("routes")["bridge"]
        assert "ephemeral-target" not in json.dumps(saved)
        if active["conversation_id"] == "ephemeral-target":
            assert active["generation"] == 1
            assert not saved.get("current_binds")


@pytest.mark.asyncio
async def test_overlapping_due_cycles_resolve_once_and_preserve_bound(setup):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def resolve(marker):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return RendezvousResolution("unique", "https://chatgpt.com/c/new")

    svc = service(setup, resolve, Clock())
    svc.prepare("bridge", allow_project_change=True)
    first = asyncio.create_task(svc.run_due_once())
    await entered.wait()
    second = asyncio.create_task(svc.run_due_once())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert calls == 1
    assert svc.status("bridge")["state"] == "bound"


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["unique", "ambiguous", "policy_failure"])
async def test_attempt_count_includes_terminal_results(setup, result):
    resolution = RendezvousResolution(
        "ambiguous" if result == "ambiguous" else "unique", "https://chatgpt.com/c/new"
    )
    svc = service(setup, Resolver(resolution), Clock())
    svc.prepare("bridge", allow_project_change=result != "policy_failure")
    await svc.run_due_once()
    assert svc.status("bridge")["attempt_count"] == 1


@pytest.mark.asyncio
async def test_failed_ephemeral_commit_discards_token_without_candidate_save(setup, monkeypatch):
    registry, _ = setup
    before = registry.resolve("bridge")
    original = registry._save
    writes = []

    def fail_commit(data):
        writes.append(json.loads(json.dumps(data)))
        if data["routes"]["bridge"]["generation"] == 1:
            raise OSError("injected commit failure")
        original(data)

    monkeypatch.setattr(registry, "_save", fail_commit)
    svc = service(setup, Resolver(RendezvousResolution("unique", "https://chatgpt.com/c/new")), Clock())
    svc.prepare("bridge", allow_project_change=True)
    await svc.run_due_once()
    assert svc.status("bridge")["terminal_error_code"] == "RENDEZVOUS_BIND_FAILED"
    assert registry.resolve("bridge") == before
    assert registry.pending_current_bind("bridge") is None
    assert all("candidate_url" not in json.dumps(data) for data in writes)

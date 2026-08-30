from app.jobs import JobStatus, JobStore
import hashlib
import json


def test_store_is_durable_and_recovers_running_jobs(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    assert store.initialize() == ()
    queued, created = store.create(
        project_id="project",
        repository_id="repository",
        task_id="test",
        request_id="req_1",
        idempotency_key=None,
    )
    assert created is True
    assert store.start(queued.job_id) is True

    interrupted = JobStore(path).initialize()
    recovered = JobStore(path).get("project", "repository", queued.job_id)

    assert [job.job_id for job in interrupted] == [queued.job_id]
    assert recovered.status is JobStatus.FAILED
    assert recovered.failure_reason == "interrupted_by_restart"


def test_idempotency_key_returns_existing_job(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.initialize()
    arguments = {
        "project_id": "project",
        "repository_id": "repository",
        "task_id": "test",
        "request_id": "req_1",
        "idempotency_key": "same",
    }

    first, first_created = store.create(**arguments)
    second, second_created = store.create(**arguments)

    assert first_created is True
    assert second_created is False
    assert second.job_id == first.job_id


def test_execution_attribution_survives_store_restart(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    store.initialize()
    payload = {"project_id": "project", "repository_id": "repository", "executable": "agy",
        "arguments": [], "timeout_seconds": 1.0, "output_limit_bytes": 1024,
        "stdin": None, "artifacts": [], "environment_keys": ["HOME"]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    job, _ = store.create_execution(project_id="project", repository_id="repository",
        request_id="req", idempotency_key=None, payload_json=encoded,
        payload_digest=hashlib.sha256(encoded.encode()).hexdigest(), executor="antigravity",
        executor_model="gemini-3.1-pro", executor_quota_state="unknown")
    rebuilt = JobStore(path)
    rebuilt.initialize()
    saved = rebuilt.get("project", "repository", job.job_id)
    expected = {"executor": "antigravity", "executor_model": "gemini-3.1-pro",
        "executor_quota_state": "unknown"}
    assert saved.status_dict() | expected == saved.status_dict()
    assert saved.output_dict() | expected == saved.output_dict()
    assert rebuilt.execution_environment_keys(job.job_id) == ("HOME",)

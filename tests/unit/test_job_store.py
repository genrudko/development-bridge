from app.jobs import JobStatus, JobStore


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

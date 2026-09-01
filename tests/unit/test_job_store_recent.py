import pytest
from app.jobs import JobStatus, JobStore


def test_job_store_recent_newest_first_and_bounded(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    store.initialize()

    # Create 5 jobs
    jobs = []
    for i in range(5):
        job, _ = store.create(
            project_id="proj-a" if i < 3 else "proj-b",
            repository_id="repo-1" if i % 2 == 0 else "repo-2",
            task_id=f"task_{i}",
            request_id=f"req_{i}",
            idempotency_key=None,
        )
        store.append_output(job.job_id, "stdout", b"large stdout content " * 100, 10000)
        jobs.append(job)

    # Test limit = 3
    recent = store.recent(3)
    assert len(recent) == 3
    # Newest first
    assert recent[0].job_id == jobs[4].job_id
    assert recent[1].job_id == jobs[3].job_id
    assert recent[2].job_id == jobs[2].job_id
    # Ensure stdout/stderr are empty in recent query (not loading full blobs)
    assert recent[0].stdout == b""
    assert recent[0].stderr == b""

    # Filter by project_id
    proj_a_recent = store.recent(10, project_id="proj-a")
    assert len(proj_a_recent) == 3
    assert [j.job_id for j in proj_a_recent] == [jobs[2].job_id, jobs[1].job_id, jobs[0].job_id]

    # Filter by repository_id
    repo_2_recent = store.recent(10, repository_id="repo-2")
    assert len(repo_2_recent) == 2
    assert [j.job_id for j in repo_2_recent] == [jobs[3].job_id, jobs[1].job_id]

    # Filter by both
    proj_a_repo_2 = store.recent(10, project_id="proj-a", repository_id="repo-2")
    assert len(proj_a_repo_2) == 1
    assert proj_a_repo_2[0].job_id == jobs[1].job_id

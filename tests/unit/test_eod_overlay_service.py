from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilitySet
from app.eod_overlay.service import (
    EodDevelopmentOverlayService,
)
from app.git.models import GitCommandResult
from app.projects.models import Repository


class FakeGitRunner:
    def __init__(self, status_output: str = ""):
        self.status_output = status_output
        self.calls = []

    async def run(self, repository, arguments, **kwargs):
        self.calls.append((repository, arguments, kwargs))
        return GitCommandResult(
            arguments=tuple(arguments),
            returncode=0,
            stdout=self.status_output,
            stderr="",
        )


class FakeJobs:
    def __init__(self, active: bool = False):
        self.active = active

    async def run_when_repository_idle(self, repository, operation, *, operation_name="run_command"):
        if self.active:
            raise BridgeError(
                ErrorCode.JOB_BUSY,
                f"{operation_name} is unavailable while this repository has a queued or running durable job",
                retryable=True,
            )
        return await operation()


def make_repo(root: Path, project_id: str = "eod", repo_id: str = "eod") -> Repository:
    return Repository(
        project_id=project_id,
        id=repo_id,
        root=root,
        capabilities=CapabilitySet(frozenset(Capability)),
    )


class FakeProcess:
    def __init__(self, returncode: int = 0, stdout: bytes = b"ok\n", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True

    @property
    def stdout(self):
        class Stream:
            def __init__(self, data):
                self.data = data
                self.read_called = False
            async def read(self, n):
                if not self.read_called:
                    self.read_called = True
                    return self.data
                return b""
        return Stream(self._stdout)

    @property
    def stderr(self):
        class Stream:
            def __init__(self, data):
                self.data = data
                self.read_called = False
            async def read(self, n):
                if not self.read_called:
                    self.read_called = True
                    return self.data
                return b""
        return Stream(self._stderr)


@pytest.mark.asyncio
async def test_apply_success_dirty_selection_and_bundle_format(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "static").mkdir(parents=True)
    (repo_root / "tests").mkdir(parents=True)

    # Eligible files
    template_file = repo_root / "src" / "templates" / "index.html"
    template_file.write_text("<h1>Hello</h1>")
    static_file = repo_root / "src" / "static" / "style.css"
    static_file.write_text("body { color: red; }")

    # Unrelated files that should be ignored
    unrelated_test = repo_root / "tests" / "test_app.py"
    unrelated_test.write_text("assert True")
    unrelated_src = repo_root / "src" / "main.py"
    unrelated_src.write_text("print(1)")

    # Git status showing eligible modified/untracked and unrelated modified using -z format
    status_output = (
        " M src/templates/index.html\x00"
        "?? src/static/style.css\x00"
        " M tests/test_app.py\x00"
        "?? src/main.py\x00"
    )
    git_runner = FakeGitRunner(status_output=status_output)
    overlay_dir = tmp_path / "overlay"

    spawn_calls = []
    bundle_snapshots = []

    async def fake_spawn(*argv, **kwargs):
        spawn_calls.append((argv, kwargs))
        bundle_arg = [arg for arg in argv if "bundle-" in arg][0]
        bundle_path = Path(bundle_arg)
        assert bundle_path.exists()
        # Verify mode 0600 on bundle
        mode = stat.S_IMODE(bundle_path.stat().st_mode)
        assert mode == 0o600
        # Verify mode 0700 on overlay dir
        overlay_mode = stat.S_IMODE(overlay_dir.stat().st_mode)
        assert overlay_mode == 0o700
        # Snapshot content before it gets deleted
        bundle_snapshots.append(json.loads(bundle_path.read_text()))
        return FakeProcess(returncode=0, stdout=b"refresh complete\n", stderr=b"")

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=overlay_dir,
        spawn=fake_spawn,
    )

    repo = make_repo(repo_root)
    result = await service.apply(repo)

    assert result["run_id"]
    assert result["file_count"] == 2
    assert sorted(result["applied_files"]) == ["src/static/style.css", "src/templates/index.html"]
    assert result["exit_code"] == 0
    assert result["stdout"] == "refresh complete"

    # Verify git status invocation used -z
    assert git_runner.calls[0][1] == ["status", "--porcelain=v1", "-z", "--untracked-files=all"]

    # Verify bundle structure
    assert len(bundle_snapshots) == 1
    bundle = bundle_snapshots[0]
    assert bundle["version"] == 1
    assert bundle["run_id"] == result["run_id"]
    files_by_path = {f["path"]: f for f in bundle["files"]}
    assert set(files_by_path.keys()) == {"src/static/style.css", "src/templates/index.html"}

    # Verify base64 content and sha256
    t_content = base64.b64decode(files_by_path["src/templates/index.html"]["content"])
    assert t_content == b"<h1>Hello</h1>"
    assert files_by_path["src/templates/index.html"]["sha256"] == hashlib.sha256(b"<h1>Hello</h1>").hexdigest()

    # Verify bundle cleanup (removed after success)
    bundle_path = overlay_dir / f"bundle-{result['run_id']}.json"
    assert not bundle_path.exists()

    # Verify trampoline argv and env
    argv, kwargs = spawn_calls[0]
    assert argv[0:2] == ("/usr/bin/systemd-run", "--user")
    assert argv[2] == f"--unit=eod-overlay-{result['run_id']}"
    assert argv[3:6] == ("--wait", "--pipe", "--collect")
    assert argv[6] == "--property=RuntimeMaxSec=180s"
    assert argv[7:11] == (
        "/usr/bin/sudo",
        "-n",
        "/usr/local/sbin/eod-development-controller",
        "local-hot-refresh",
    )
    assert argv[11] == str(bundle_path)
    assert argv[12] == result["run_id"]

    runtime_dir = f"/run/user/{os.getuid()}"
    assert kwargs["env"] == {
        "XDG_RUNTIME_DIR": runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
    }


@pytest.mark.asyncio
async def test_apply_explicit_paths_filtering(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "static").mkdir(parents=True)

    t1 = repo_root / "src" / "templates" / "t1.html"
    t1.write_text("t1")
    t2 = repo_root / "src" / "templates" / "t2.html"
    t2.write_text("t2")

    status_output = "?? src/templates/t1.html\x00?? src/templates/t2.html\x00"
    git_runner = FakeGitRunner(status_output=status_output)

    bundle_snapshots = []
    async def fake_spawn(*argv, **kwargs):
        bundle_arg = [arg for arg in argv if "bundle-" in arg][0]
        bundle_path = Path(bundle_arg)
        bundle_snapshots.append(json.loads(bundle_path.read_text()))
        return FakeProcess(returncode=0)

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
        spawn=fake_spawn,
    )

    repo = make_repo(repo_root)
    result = await service.apply(repo, paths=["src/templates/t1.html"])
    assert result["file_count"] == 1
    assert result["applied_files"] == ["src/templates/t1.html"]
    assert len(bundle_snapshots[0]["files"]) == 1
    assert bundle_snapshots[0]["files"][0]["path"] == "src/templates/t1.html"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_path", [
    "src/templates/../templates/t1.html",
    "./src/templates/t1.html",
    "src/templates//t1.html",
    "src/templates\\t1.html",
    "/src/templates/t1.html",
    "src/templates/.",
    "src/templates/./t1.html",
    "src/templates/",
    "../src/templates/t1.html",
    "",
])
async def test_apply_rejects_non_canonical_explicit_paths(tmp_path, invalid_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    t1 = repo_root / "src" / "templates" / "t1.html"
    t1.write_text("t1")

    status_output = "?? src/templates/t1.html\x00"
    git_runner = FakeGitRunner(status_output=status_output)
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo, paths=[invalid_path])
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_apply_rejects_non_eod_repository(tmp_path):
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=FakeGitRunner(),
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(tmp_path, project_id="other", repo_id="other")
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION


@pytest.mark.asyncio
@pytest.mark.parametrize("status_line", [
    " D src/templates/index.html\x00",
    "D  src/static/style.css\x00",
    "R  src/templates/new.html\x00src/templates/old.html\x00",
    "R  src/templates/new.html\x00src/app.py\x00",
    "R  src/app.py\x00src/templates/old.html\x00",
    " T src/static/icon.png\x00",
    "U  src/templates/conflict.html\x00",
    "AA src/templates/conflict.html\x00",
    "UU src/templates/conflict.html\x00",
])
async def test_apply_fails_closed_on_eligible_deletion_rename_typechange_conflict(tmp_path, status_line):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "static").mkdir(parents=True)

    git_runner = FakeGitRunner(status_output=status_line)
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION


@pytest.mark.asyncio
async def test_apply_ignores_unrelated_dirty_or_renamed_files(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    f = repo_root / "src" / "templates" / "index.html"
    f.write_text("index content")

    # Status has unrelated rename, deletion, and untracked, plus eligible modified
    status_output = (
        "R  src/new_app.py\x00src/old_app.py\x00"
        " D tests/old_test.py\x00"
        "?? README.md\x00"
        " M src/templates/index.html\x00"
    )
    git_runner = FakeGitRunner(status_output=status_output)

    async def fake_spawn(*argv, **kwargs):
        return FakeProcess(returncode=0, stdout=b"applied\n")

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)
    result = await service.apply(repo)
    assert result["file_count"] == 1
    assert result["applied_files"] == ["src/templates/index.html"]


@pytest.mark.asyncio
async def test_apply_rejects_symlink_leaf(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    target_file = repo_root / "src" / "templates" / "real.html"
    target_file.write_text("real")
    symlink_file = repo_root / "src" / "templates" / "sym.html"
    symlink_file.symlink_to(target_file)

    git_runner = FakeGitRunner(status_output="?? src/templates/sym.html\x00")
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "Symlink" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_rejects_symlink_parent_directory(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir(parents=True)

    outside_dir = tmp_path / "outside_templates"
    outside_dir.mkdir()
    (outside_dir / "index.html").write_text("outside")

    # Symlink directory under src/templates
    (repo_root / "src" / "templates").symlink_to(outside_dir)

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "Symlink" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_rejects_symlink_overlay_dir(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "templates" / "index.html").write_text("content")

    real_overlay = tmp_path / "real_overlay"
    real_overlay.mkdir()
    sym_overlay = tmp_path / "sym_overlay"
    sym_overlay.symlink_to(real_overlay)

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=sym_overlay,
        spawn=lambda *a, **k: FakeProcess(0),
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "symlink" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_apply_enforces_bounds_max_files(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    status_tokens = []
    for i in range(65):
        f = repo_root / "src" / "templates" / f"file_{i}.html"
        f.write_text(f"content {i}")
        status_tokens.append(f"?? src/templates/file_{i}.html\x00")

    git_runner = FakeGitRunner(status_output="".join(status_tokens))
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "64" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_enforces_bounds_single_file_size(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    f = repo_root / "src" / "templates" / "large.html"
    f.write_bytes(b"x" * (2 * 1024 * 1024 + 1))

    git_runner = FakeGitRunner(status_output="?? src/templates/large.html\x00")
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "2 MiB" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_enforces_bounds_total_size(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    status_tokens = []
    for i in range(5):
        f = repo_root / "src" / "templates" / f"part_{i}.html"
        f.write_bytes(b"x" * int(1.7 * 1024 * 1024))
        status_tokens.append(f"?? src/templates/part_{i}.html\x00")

    git_runner = FakeGitRunner(status_output="".join(status_tokens))
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.POLICY_VIOLATION
    assert "8 MiB" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_bundle_cleaned_up_on_controller_failure(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    f = repo_root / "src" / "templates" / "index.html"
    f.write_text("content")

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    overlay_dir = tmp_path / "overlay"

    async def fake_spawn(*argv, **kwargs):
        bundle_arg = [arg for arg in argv if "bundle-" in arg][0]
        bundle_path = Path(bundle_arg)
        assert bundle_path.exists()
        return FakeProcess(returncode=1, stderr=b"controller error\n")

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=overlay_dir,
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.INTERNAL_ERROR

    # Verify no bundle files remain in overlay_dir
    assert list(overlay_dir.glob("bundle-*.json")) == []
    assert list(overlay_dir.glob(".bundle-*.tmp")) == []


@pytest.mark.asyncio
async def test_apply_maps_sudo_failure_to_permission_denied(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    f = repo_root / "src" / "templates" / "index.html"
    f.write_text("content")

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    overlay_dir = tmp_path / "overlay"

    async def fake_spawn(*argv, **kwargs):
        return FakeProcess(returncode=1, stderr=b"sudo: a password is required\n")

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=overlay_dir,
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)
    assert exc.value.code is ErrorCode.PERMISSION_DENIED
    assert not exc.value.retryable


@pytest.mark.asyncio
async def test_apply_and_rollback_serialized_by_job_idle_guard(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)

    f = repo_root / "src" / "templates" / "index.html"
    f.write_text("content")

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(active=True),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
    )
    repo = make_repo(repo_root)
    with pytest.raises(BridgeError) as exc_apply:
        await service.apply(repo)
    assert exc_apply.value.code is ErrorCode.JOB_BUSY

    with pytest.raises(BridgeError) as exc_rollback:
        await service.rollback(repo)
    assert exc_rollback.value.code is ErrorCode.JOB_BUSY


@pytest.mark.asyncio
async def test_rollback_success_exact_argv_and_env(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    spawn_calls = []
    async def fake_spawn(*argv, **kwargs):
        spawn_calls.append((argv, kwargs))
        return FakeProcess(returncode=0, stdout=b"overlay cleared\n")

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=FakeGitRunner(),
        overlay_dir=tmp_path / "overlay",
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)
    result = await service.rollback(repo)

    assert result["cleared"] is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "overlay cleared"

    argv, kwargs = spawn_calls[0]
    assert argv[0:2] == ("/usr/bin/systemd-run", "--user")
    assert argv[2].startswith("--unit=eod-overlay-rollback-")
    assert argv[3:6] == ("--wait", "--pipe", "--collect")
    assert argv[6] == "--property=RuntimeMaxSec=180s"
    assert argv[7:11] == (
        "/usr/bin/sudo",
        "-n",
        "/usr/local/sbin/eod-development-controller",
        "local-hot-refresh-clear",
    )
    runtime_dir = f"/run/user/{os.getuid()}"
    assert kwargs["env"] == {
        "XDG_RUNTIME_DIR": runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
    }


@pytest.mark.asyncio
async def test_trampoline_timeout_kills_process_and_stops_transient_unit(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "templates" / "index.html").write_text("hello")

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")

    spawn_calls = []

    class HangingProcess:
        def __init__(self):
            self.killed = False

        async def wait(self):
            await asyncio.sleep(10.0)
            return 0

        def kill(self):
            self.killed = True

        @property
        def stdout(self):
            class S:
                async def read(self, n):
                    return b""
            return S()

        @property
        def stderr(self):
            class S:
                async def read(self, n):
                    return b""
            return S()

    async def fake_spawn(*argv, **kwargs):
        spawn_calls.append((argv, kwargs))
        if argv[0] == "/usr/bin/systemctl":
            return FakeProcess(returncode=0)
        return HangingProcess()

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
        timeout_seconds=0.05,
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)

    with pytest.raises(BridgeError) as exc:
        await service.apply(repo)

    assert exc.value.code is ErrorCode.INTERNAL_ERROR
    assert "timed out" in str(exc.value)

    # Verify systemctl --user stop <unit> was called
    stop_calls = [call for call in spawn_calls if call[0][0] == "/usr/bin/systemctl"]
    assert len(stop_calls) == 1
    stop_argv = stop_calls[0][0]
    assert stop_argv[0:3] == ("/usr/bin/systemctl", "--user", "stop")
    assert stop_argv[3].startswith("eod-overlay-")


@pytest.mark.asyncio
async def test_trampoline_bounds_large_output(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src" / "templates").mkdir(parents=True)
    (repo_root / "src" / "templates" / "index.html").write_text("hello")

    git_runner = FakeGitRunner(status_output="?? src/templates/index.html\x00")
    large_stdout = b"line\n" * 5000  # ~25 KB

    async def fake_spawn(*argv, **kwargs):
        return FakeProcess(returncode=0, stdout=large_stdout)

    service = EodDevelopmentOverlayService(
        jobs=FakeJobs(),
        git_runner=git_runner,
        overlay_dir=tmp_path / "overlay",
        spawn=fake_spawn,
    )
    repo = make_repo(repo_root)
    result = await service.apply(repo)
    assert len(result["stdout"]) <= 2048

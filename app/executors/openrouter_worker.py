from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def check_path_confinement(repo_root: Path, target_path: str | Path) -> Path:
    repo_root = repo_root.resolve()
    raw = str(target_path)
    if not raw or "\0" in raw:
        raise ValueError(f"Invalid path: {target_path!r}")
    path = Path(target_path)
    if path.is_absolute():
        raise ValueError(f"Path must be relative to repository root: {target_path}")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"Path traversal ('..') is rejected: {target_path}")

    combined = (repo_root / path).resolve()
    try:
        combined.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"Path escapes repository root: {target_path}") from exc

    # Check symlinks along the path
    curr = repo_root / path
    while curr != repo_root:
        if curr.is_symlink():
            target = curr.resolve()
            try:
                target.relative_to(repo_root)
            except ValueError as exc:
                raise ValueError(f"Symlink escapes repository root: {target_path}") from exc
        curr = curr.parent

    return repo_root / path


def read_file(repo_root: Path, path: str) -> str:
    try:
        resolved = check_path_confinement(repo_root, path)
        if not resolved.is_file():
            return f"Error: '{path}' does not exist or is not a regular file."
        content = resolved.read_text(encoding="utf-8", errors="replace")
        if len(content) > 262_144:
            return content[:262_144] + "\n...[truncated: output exceeds limit]"
        return content
    except Exception as exc:
        return f"Error: read_file rejected: {exc}"


def write_file(repo_root: Path, path: str, content: str) -> str:
    try:
        resolved = check_path_confinement(repo_root, path)
        # Prevent writing into .git directory
        rel = resolved.resolve().relative_to(repo_root.resolve())
        if rel.parts and rel.parts[0] == ".git":
            return "Error: write_file to .git directory is rejected."
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content.encode('utf-8'))} bytes to {path}."
    except Exception as exc:
        return f"Error: write_file rejected: {exc}"


def search_files(repo_root: Path, query: str, path: str = ".") -> str:
    try:
        search_dir = check_path_confinement(repo_root, path)
        if not search_dir.is_dir():
            return f"Error: '{path}' is not a directory."
        resolved_repo = repo_root.resolve()
        matches: list[str] = []
        for root, dirs, files in os.walk(search_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            dirs_to_skip = []
            for d in dirs:
                d_path = Path(root) / d
                if d_path.is_symlink():
                    try:
                        d_path.resolve().relative_to(resolved_repo)
                    except ValueError:
                        dirs_to_skip.append(d)
            for d in dirs_to_skip:
                dirs.remove(d)

            for fname in sorted(files):
                file_path = Path(root) / fname
                if file_path.is_symlink():
                    try:
                        file_path.resolve().relative_to(resolved_repo)
                    except ValueError:
                        continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                    if query in text:
                        rel = file_path.relative_to(repo_root)
                        for line_no, line in enumerate(text.splitlines(), 1):
                            if query in line:
                                matches.append(f"{rel}:{line_no}: {line.strip()[:160]}")
                                if len(matches) >= 50:
                                    break
                except Exception:
                    continue
                if len(matches) >= 50:
                    break
            if len(matches) >= 50:
                break
        if not matches:
            return f"No matches found for {query!r}."
        return "\n".join(matches)
    except Exception as exc:
        return f"Error: search_files rejected: {exc}"


BWRAP_PATH: str = "/bin/bwrap"

ALLOWED_EXECUTABLES = {"pytest", "python", "python3", "git", "ruff"}

SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL")

# Pytest allowed options
ALLOWED_PYTEST_OPTIONS_VALUELESS = {
    "-v", "-vv", "-vvv", "-q", "-qq", "-s", "-x", "--exitfirst",
    "-l", "--showlocals", "--collect-only", "--fixtures",
    "--disable-warnings", "--disable-pytest-warnings",
    "--strict-markers", "--strict-config",
    "-ra", "-rA", "-rf", "-rs", "-rE", "-rx", "-rp", "-rP",
    "--import-mode=importlib", "--import-mode=prepend", "--import-mode=append",
    "--continue-on-collection-errors",
}
ALLOWED_PYTEST_OPTIONS_WITH_VALUE = {
    "-k", "-m", "--maxfail", "--durations", "--tb", "-p",
}

# Python allowed flags
ALLOWED_PYTHON_FLAGS = {"-u", "-B", "-v", "-O", "-OO", "-W", "-E"}

# Git allowed subcommands (read-only only in v1)
ALLOWED_GIT_READONLY_SUBCMDS = {"status", "diff", "log", "show"}
ALLOWED_GIT_WRITE_SUBCMDS: set[str] = set()

ALLOWED_GIT_STATUS_OPTIONS = {
    "-s", "--short", "-b", "--branch", "-u", "-uno", "-unormal", "-uall",
    "--untracked-files", "--ignored", "-v", "--verbose", "--",
}
ALLOWED_GIT_DIFF_OPTIONS = {
    "--stat", "--cached", "--staged", "-p", "-u", "--check",
    "--name-only", "--name-status", "-w", "--ignore-all-space", "--word-diff", "--",
}
ALLOWED_GIT_LOG_OPTIONS = {
    "--oneline", "--stat", "-p", "--graph", "--decorate", "--summary",
    "--name-only", "--name-status", "--",
}
ALLOWED_GIT_SHOW_OPTIONS = {
    "--stat", "--oneline", "-p", "--name-only", "--name-status", "--",
}

# Ruff allowed subcommands and options
ALLOWED_RUFF_SUBCMDS = {"check", "format"}
ALLOWED_RUFF_OPTIONS = {"--fix", "--diff", "-v", "-q", "--select", "--ignore"}


def get_scrubbed_env(repo_root: Path, sandbox_home: str = "/tmp/sandbox-home") -> dict[str, str]:
    scrubbed: dict[str, str] = {}
    for var in SAFE_ENV_KEYS:
        if var in os.environ:
            scrubbed[var] = os.environ[var]

    scrubbed["HOME"] = sandbox_home

    # Explicitly exclude secrets, credentials, and SSH_CONNECTION
    for k in list(scrubbed.keys()):
        upper = k.upper()
        if (
            "OPENROUTER" in upper
            or "DEVELOPMENT_BRIDGE" in upper
            or "SECRET" in upper
            or "TOKEN" in upper
            or "KEY" in upper
            or "SSH" in upper
            or "CREDENTIAL" in upper
            or upper == "SSH_CONNECTION"
        ):
            del scrubbed[k]

    return scrubbed


_BWRAP_PROC_FLAGS: list[str] | None = None


def get_bwrap_proc_flags(bwrap_bin: str) -> list[str]:
    global _BWRAP_PROC_FLAGS
    if _BWRAP_PROC_FLAGS is None:
        try:
            probe = subprocess.run(
                [bwrap_bin, "--unshare-all", "--dev", "/dev", "--proc", "/proc", "/bin/true"],
                capture_output=True,
                timeout=2.0,
            )
            if probe.returncode == 0:
                _BWRAP_PROC_FLAGS = ["--proc", "/proc"]
            else:
                _BWRAP_PROC_FLAGS = [
                    "--tmpfs", "/proc",
                    "--ro-bind-try", "/proc/cpuinfo", "/proc/cpuinfo",
                    "--ro-bind-try", "/proc/meminfo", "/proc/meminfo",
                    "--ro-bind-try", "/proc/stat", "/proc/stat",
                ]
        except Exception:
            _BWRAP_PROC_FLAGS = [
                "--tmpfs", "/proc",
                "--ro-bind-try", "/proc/cpuinfo", "/proc/cpuinfo",
                "--ro-bind-try", "/proc/meminfo", "/proc/meminfo",
                "--ro-bind-try", "/proc/stat", "/proc/stat",
            ]
    return list(_BWRAP_PROC_FLAGS)


def resolve_runtime_venv(repo_root: Path) -> tuple[Path | None, bool]:
    local_venv = repo_root / ".venv"
    if (local_venv / "bin").is_dir():
        return local_venv.resolve(), True
    prefix = Path(sys.prefix).resolve()
    if (prefix / "bin").is_dir():
        return prefix, False
    return None, False


def resolve_executable(executable: str, venv_path: Path | None, env_path: str) -> str | None:
    if venv_path:
        target = venv_path / "bin" / executable
        if target.is_file() and os.access(target, os.X_OK):
            return str(target)
        if executable in ("python", "python3"):
            py_target = venv_path / "bin" / "python"
            if py_target.is_file() and os.access(py_target, os.X_OK):
                return str(py_target)
    if executable in ("python", "python3"):
        if os.path.isfile(sys.executable) and os.access(sys.executable, os.X_OK):
            return sys.executable
    return shutil.which(executable, path=env_path)



def run_process(
    repo_root: Path,
    executable: str,
    arguments: list[str] | None = None,
    task: str = "",
    timeout: float = 60.0,
) -> str:
    if not executable or not isinstance(executable, str):
        return "Error: executable name must be a non-empty string."

    clean_exec = executable.strip()
    if " " in clean_exec or "/" in clean_exec or "\\" in clean_exec:
        return f"Error: invalid executable name {executable!r}."

    if clean_exec not in ALLOWED_EXECUTABLES:
        return (
            f"Error: executable '{clean_exec}' is not permitted. "
            f"Only allowlisted tools ({', '.join(sorted(ALLOWED_EXECUTABLES))}) are permitted."
        )

    if arguments is None:
        raw_args: list[str] = []
    elif isinstance(arguments, list):
        raw_args = [str(x) for x in arguments]
    elif isinstance(arguments, (tuple,)):
        raw_args = [str(x) for x in arguments]
    elif isinstance(arguments, str):
        raw_args = [arguments] if arguments else []
    else:
        return "Error: arguments must be a list of strings."

    # Validate argument strings: reject null bytes, absolute paths, and parent directory traversal
    for arg in raw_args:
        if "\0" in arg:
            return f"Error: invalid argument containing null byte: {arg!r}"
        if arg.startswith("/") or arg.startswith("~"):
            return f"Error: absolute path or home path rejected: {arg!r}"
        if ".." in Path(arg).parts or arg == "..":
            return f"Error: directory traversal ('..') rejected: {arg!r}"

    # Executable-specific validation (fail closed)
    if clean_exec in ("python", "python3"):
        idx = 0
        while idx < len(raw_args):
            arg = raw_args[idx]
            if arg in ("-c", "--command") or arg.startswith("-c="):
                return "Error: python inline code execution (-c) is rejected."
            if arg == "-m":
                if idx + 1 >= len(raw_args):
                    return "Error: python -m requires a module name."
                mod = raw_args[idx + 1]
                if "/" in mod or "\\" in mod or ".." in mod:
                    return f"Error: invalid module name: {mod!r}"
                mod_parts = mod.split(".")
                mod_path = repo_root.joinpath(*mod_parts)
                is_local = (
                    mod_path.with_suffix(".py").is_file()
                    or (mod_path / "__init__.py").is_file()
                    or mod_path.is_dir()
                )
                if not is_local:
                    return (
                        f"Error: python -m module '{mod}' is not a repository-local module. "
                        "External module execution is forbidden."
                    )
                try:
                    check_path_confinement(repo_root, mod_parts[0])
                except Exception as exc:
                    return f"Error: module path escapes repository root: {exc}"
                idx += 2
                continue
            if arg.startswith("-"):
                if arg not in ALLOWED_PYTHON_FLAGS:
                    return f"Error: unknown or disallowed python flag: {arg!r}"
                idx += 1
                continue
            # Positional argument: script path
            try:
                confined = check_path_confinement(repo_root, arg)
                if not confined.is_file():
                    return f"Error: script '{arg}' does not exist or is not a regular file."
            except Exception as exc:
                return f"Error: script path rejected: {exc}"
            # Validate remaining script args: check any path-like arguments
            for script_arg in raw_args[idx + 1:]:
                if "/" in script_arg or script_arg.endswith((".py", ".txt", ".json", ".md", ".yml", ".yaml")):
                    try:
                        check_path_confinement(repo_root, script_arg)
                    except Exception as exc:
                        return f"Error: script argument path rejected: {exc}"
            break

    elif clean_exec == "pytest":
        idx = 0
        while idx < len(raw_args):
            arg = raw_args[idx]
            if arg in ALLOWED_PYTEST_OPTIONS_VALUELESS:
                idx += 1
                continue
            if arg in ALLOWED_PYTEST_OPTIONS_WITH_VALUE:
                if idx + 1 >= len(raw_args):
                    return f"Error: pytest option '{arg}' requires a value."
                val = raw_args[idx + 1]
                if arg in ("--maxfail", "--durations"):
                    if not val.isdigit():
                        return f"Error: pytest option '{arg}' requires an integer value."
                elif arg == "--tb":
                    if val not in ("short", "auto", "line", "native", "no", "long"):
                        return f"Error: invalid --tb value '{val}'."
                idx += 2
                continue
            if any(arg.startswith(prefix) for prefix in ("--tb=", "--maxfail=", "--durations=", "--color=")):
                idx += 1
                continue
            if arg.startswith("-"):
                return f"Error: unknown or disallowed pytest option: {arg!r}"
            # Positional argument: test path
            test_target = arg.split("::", 1)[0]
            try:
                check_path_confinement(repo_root, test_target)
            except Exception as exc:
                return f"Error: pytest target rejected: {exc}"
            idx += 1

    elif clean_exec == "git":
        if not raw_args:
            return "Error: git requires a subcommand (e.g. status, diff, log, show)."
        subcmd = raw_args[0]
        if subcmd not in ALLOWED_GIT_READONLY_SUBCMDS:
            return (
                f"Error: git subcommand '{subcmd}' is not permitted in v1. "
                f"Allowed read-only subcommands: {', '.join(sorted(ALLOWED_GIT_READONLY_SUBCMDS))}."
            )

        if subcmd == "status":
            for arg in raw_args[1:]:
                if arg.startswith("-"):
                    if arg not in ALLOWED_GIT_STATUS_OPTIONS:
                        return f"Error: disallowed git status option: {arg!r}"
                elif arg != ".":
                    try:
                        check_path_confinement(repo_root, arg)
                    except Exception as exc:
                        return f"Error: git status path rejected: {exc}"

        elif subcmd == "diff":
            for arg in raw_args[1:]:
                if arg.startswith("-"):
                    if arg not in ALLOWED_GIT_DIFF_OPTIONS and not re.match(r"^-U\d+$", arg):
                        return f"Error: disallowed git diff option: {arg!r}"
                elif arg != ".":
                    if "/" in arg or "." in arg:
                        try:
                            check_path_confinement(repo_root, arg)
                        except Exception as exc:
                            return f"Error: git diff path rejected: {exc}"

        elif subcmd == "log":
            idx = 1
            while idx < len(raw_args):
                arg = raw_args[idx]
                if arg.startswith("-"):
                    if arg in ("-n", "--max-count"):
                        if idx + 1 >= len(raw_args) or not raw_args[idx + 1].isdigit():
                            return "Error: git log -n requires an integer count."
                        idx += 2
                        continue
                    elif re.match(r"^-\d+$", arg):
                        idx += 1
                        continue
                    elif arg not in ALLOWED_GIT_LOG_OPTIONS:
                        return f"Error: disallowed git log option: {arg!r}"
                elif arg != ".":
                    if "/" in arg or "." in arg:
                        try:
                            check_path_confinement(repo_root, arg)
                        except Exception as exc:
                            return f"Error: git log path rejected: {exc}"
                idx += 1

        elif subcmd == "show":
            for arg in raw_args[1:]:
                if arg.startswith("-"):
                    if arg not in ALLOWED_GIT_SHOW_OPTIONS:
                        return f"Error: disallowed git show option: {arg!r}"
                elif arg != ".":
                    if ":" in arg:
                        _, target_path = arg.split(":", 1)
                        try:
                            check_path_confinement(repo_root, target_path)
                        except Exception as exc:
                            return f"Error: git show target rejected: {exc}"
                    elif "/" in arg or "." in arg:
                        try:
                            check_path_confinement(repo_root, arg)
                        except Exception as exc:
                            return f"Error: git show path rejected: {exc}"

    elif clean_exec == "ruff":
        if not raw_args:
            return "Error: ruff requires a subcommand ('check' or 'format')."
        subcmd = raw_args[0]
        if subcmd not in ALLOWED_RUFF_SUBCMDS:
            return f"Error: ruff subcommand '{subcmd}' is not permitted. Only 'check' and 'format' are allowed."
        for arg in raw_args[1:]:
            if arg.startswith("-"):
                if arg not in ALLOWED_RUFF_OPTIONS:
                    return f"Error: disallowed ruff option: {arg!r}"
            elif arg != ".":
                try:
                    check_path_confinement(repo_root, arg)
                except Exception as exc:
                    return f"Error: ruff path rejected: {exc}"

    bwrap_bin = BWRAP_PATH
    if not (os.path.isfile(bwrap_bin) and os.access(bwrap_bin, os.X_OK)):
        return f"Error: {bwrap_bin} is not available. Sandboxed execution failed closed."

    repo_resolved = repo_root.resolve()
    venv_path, is_repo_local = resolve_runtime_venv(repo_resolved)
    sandbox_path = (
        f"{venv_path / 'bin'}:/usr/local/bin:/usr/bin:/bin"
        if venv_path
        else "/usr/local/bin:/usr/bin:/bin"
    )
    resolved = resolve_executable(clean_exec, venv_path, sandbox_path)
    if not resolved:
        return f"Error: executable '{clean_exec}' is not available or not found in PATH."

    sandbox_home = "/tmp/sandbox-home"
    bwrap_cmd: list[str] = [
        bwrap_bin,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ]
    bwrap_cmd.extend(get_bwrap_proc_flags(bwrap_bin))

    for sys_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
        if os.path.isdir(sys_dir):
            bwrap_cmd.extend(["--ro-bind-try", sys_dir, sys_dir])

    # Repository is the only writable host tree exposed
    bwrap_cmd.extend(["--bind", str(repo_resolved), str(repo_resolved)])

    # Protect repo-local .venv if present
    if (repo_resolved / ".venv").exists():
        bwrap_cmd.extend(["--ro-bind", str(repo_resolved / ".venv"), str(repo_resolved / ".venv")])

    # If runtime venv is outside repo, mount it read-only
    if venv_path and not is_repo_local and venv_path.exists():
        bwrap_cmd.extend(["--ro-bind", str(venv_path), str(venv_path)])

    # Protect .git metadata read-only
    if (repo_resolved / ".git").exists():
        bwrap_cmd.extend(["--ro-bind", str(repo_resolved / ".git"), str(repo_resolved / ".git")])
        if (repo_resolved / ".git").is_file():
            try:
                git_content = (repo_resolved / ".git").read_text(encoding="utf-8", errors="ignore").strip()
                if git_content.startswith("gitdir:"):
                    gitdir_raw = git_content.split(":", 1)[1].strip()
                    gitdir_path = Path(gitdir_raw)
                    if not gitdir_path.is_absolute():
                        gitdir_path = (repo_resolved / gitdir_path).resolve()
                    else:
                        gitdir_path = gitdir_path.resolve()
                    if gitdir_path.exists():
                        bwrap_cmd.extend(["--ro-bind", str(gitdir_path), str(gitdir_path)])
                        commondir_file = gitdir_path / "commondir"
                        if commondir_file.is_file():
                            commondir_raw = commondir_file.read_text(encoding="utf-8", errors="ignore").strip()
                            commondir_path = Path(commondir_raw)
                            if not commondir_path.is_absolute():
                                commondir_path = (gitdir_path / commondir_path).resolve()
                            else:
                                commondir_path = commondir_path.resolve()
                            if commondir_path.exists():
                                bwrap_cmd.extend(["--ro-bind", str(commondir_path), str(commondir_path)])
            except Exception:
                pass

    # Synthetic HOME not equal to host HOME
    bwrap_cmd.extend([
        "--dir", sandbox_home,
        "--setenv", "HOME", sandbox_home,
        "--setenv", "PATH", sandbox_path,
    ])

    for k in ("LANG", "LC_ALL"):
        if k in os.environ:
            bwrap_cmd.extend(["--setenv", k, os.environ[k]])

    bwrap_cmd.extend(["--chdir", str(repo_resolved)])
    bwrap_cmd.extend([resolved, *raw_args])

    env = get_scrubbed_env(repo_resolved, sandbox_home=sandbox_home)
    env["PATH"] = sandbox_path

    try:
        proc = subprocess.run(
            bwrap_cmd,
            shell=False,
            cwd=str(repo_resolved),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout_bounded = proc.stdout[:32768]
        stderr_bounded = proc.stderr[:32768]
        return (
            f"exit code: {proc.returncode}\n"
            f"stdout:\n{stdout_bounded}\n"
            f"stderr:\n{stderr_bounded}"
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds."
    except Exception as exc:
        return f"Error executing command: {exc}"



TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents within repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file inside repository"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or modify a file within repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file inside repository"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a query string across repository files",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for"},
                    "path": {"type": "string", "description": "Relative path of directory to search in, defaults to '.'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_process",
            "description": "Execute an allowlisted command with structured arguments within repository root",
            "parameters": {
                "type": "object",
                "properties": {
                    "executable": {
                        "type": "string",
                        "description": "Allowlisted executable: 'pytest', 'python', 'python3', 'git', or 'ruff'",
                    },
                    "arguments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of command arguments",
                    },
                },
                "required": ["executable"],
            },
        },
    },
]


class OpenRouterWorker:
    def __init__(
        self,
        repo_root: Path,
        model: str,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        task: str = "",
        task_kind: str = "implementation",
        max_turns: int = 30,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.task = task
        self.task_kind = task_kind
        self.max_turns = max_turns
        self.cumulative_usage: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/development-bridge",
                "X-Title": "Development Bridge",
                "User-Agent": "Development-Bridge-OpenRouter-Worker/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body)

    def _execute_tool(self, name: str, arguments_str: str) -> str:
        try:
            args = json.loads(arguments_str) if arguments_str else {}
        except Exception as exc:
            return f"Error: failed to parse tool arguments: {exc}"

        if name == "read_file":
            return read_file(self.repo_root, args.get("path", ""))
        elif name == "write_file":
            return write_file(self.repo_root, args.get("path", ""), args.get("content", ""))
        elif name == "search_files":
            return search_files(self.repo_root, args.get("query", ""), args.get("path", "."))
        elif name == "run_process":
            return run_process(
                self.repo_root,
                executable=args.get("executable", ""),
                arguments=args.get("arguments"),
                task=self.task,
            )
        else:
            return f"Error: unknown tool '{name}'"

    def run(self) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are executing one bounded Development Bridge repository task. "
                    "Follow all repository invariants. Do not push, deploy, or mutate remotes."
                ),
            },
            {"role": "user", "content": self.task},
        ]

        final_response: str | None = None
        for _ in range(self.max_turns):
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            }
            try:
                resp = self._post_chat(payload)
            except Exception as exc:
                return {
                    "status": "ERROR",
                    "error": f"OpenRouter API call failed: {exc}",
                    "usage": self.cumulative_usage,
                }

            # Accumulate usage
            usage = resp.get("usage") or {}
            self.cumulative_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.cumulative_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.cumulative_usage["total_tokens"] += usage.get("total_tokens", 0)
            if "cost" in usage and usage["cost"] is not None:
                self.cumulative_usage["cost"] = (
                    self.cumulative_usage.get("cost", 0.0) + float(usage["cost"])
                )

            choices = resp.get("choices") or []
            if not choices:
                return {
                    "status": "ERROR",
                    "error": "Empty choices returned by OpenRouter",
                    "usage": self.cumulative_usage,
                }

            choice = choices[0]
            message = choice.get("message") or {}
            messages.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                final_response = message.get("content") or ""
                break

            for tc in tool_calls:
                call_id = tc.get("id", "")
                func = tc.get("function") or {}
                fn_name = func.get("name", "")
                fn_args = func.get("arguments", "")
                tool_output = self._execute_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output,
                })

        if final_response is None:
            final_response = "Execution reached maximum turns limit."

        return {
            "status": "SUCCESS",
            "response": final_response,
            "usage": self.cumulative_usage,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenRouter standalone executor worker")
    parser.add_argument("--model", required=True, help="Allowlisted model to invoke")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1", help="OpenRouter base URL")
    parser.add_argument("--task-kind", default="implementation", help="Task kind")
    args = parser.parse_args()

    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("DEVELOPMENT_BRIDGE_OPENROUTER_API_KEY")
    )
    if not api_key:
        result = {
            "status": "ERROR",
            "error": "OPENROUTER_API_KEY environment variable is missing",
            "usage": {},
        }
        sys.stdout.write(json.dumps(result) + "\n")
        sys.exit(1)

    task_prompt = sys.stdin.read()
    repo_root = Path.cwd()

    worker = OpenRouterWorker(
        repo_root=repo_root,
        model=args.model,
        api_key=api_key,
        base_url=args.base_url,
        task=task_prompt,
        task_kind=args.task_kind,
    )
    result = worker.run()
    sys.stdout.write(json.dumps(result) + "\n")
    if result["status"] != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()

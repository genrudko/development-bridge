from __future__ import annotations

import argparse
import json
import os
import re
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
        matches: list[str] = []
        for root, dirs, files in os.walk(search_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for fname in sorted(files):
                file_path = Path(root) / fname
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


FORBIDDEN_COMMAND_PATTERNS = [
    r"\bgit\s+push\b",
    r"\bgit\s+remote\b",
    r"\bgh\b",
    r"\bsudo\b",
    r"\bsystemctl\b",
    r"\bservice\b",
    r"\bssh\b",
    r"\bscp\b",
    r"\bsftp\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bnc\b",
    r"\bnetcat\b",
    r"\bsocat\b",
    r"\bdocker\b",
    r"\bpodman\b",
    r"\bkubectl\b",
    r"\bhelm\b",
    r"\bterraform\b",
    r"\bansible\b",
]


def run_process(repo_root: Path, command: str, task: str = "", timeout: float = 60.0) -> str:
    # Check for path escapes in command line
    if ".." in command:
        # Check if .. is used for directory traversal
        if re.search(r"(?:^|\s|\/)\.\.(?:\/|\s|$)", command):
            return "Error: command rejected due to path traversal ('..')."

    # Check forbidden commands
    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Error: command rejected by policy (matches forbidden pattern {pattern})."

    # Check git commit / add constraints
    if re.search(r"\bgit\s+commit\b", command, re.IGNORECASE):
        if "commit" not in task.lower():
            return "Error: git commit is permitted only when the task explicitly asks for commit."

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(repo_root.resolve()),
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
            "description": "Execute a bounded command within repository root",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"}
                },
                "required": ["command"],
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
            return run_process(self.repo_root, args.get("command", ""), task=self.task)
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

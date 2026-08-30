from __future__ import annotations

from app.executors.models import TaskKind

PROMPT_TEMPLATE = """You are executing one bounded Development Bridge repository task.
Read and obey AGENTS.md before changing files.
Task:
{task}
Invariants:
- Work only inside the current repository.
- Do not change Git remotes, SSH configuration, credentials, or repository registration.
- Do not expose secrets or Bridge-native GitHub credentials.
- Do not push or deploy.
- Do not start background schedulers or delegate the task.
{verification}
Stop conditions:
- Stop on an authentication, quota, permission, or environment blocker.
- Return concise evidence: files changed, tests run, and remaining blocker.
"""


def format_verification(task_kind: TaskKind) -> str:
    if task_kind.value == "implementation":
        return (
            "Verification:\n- Run targeted tests for changed behavior.\n"
            "- Run the full test suite only when the task or repository rules require it."
        )
    if task_kind.value == "review":
        return "Verification:\n- Do not run test suites unless the task explicitly asks."
    return "Verification:\n- Run only the checks needed to answer the bounded task."


def build_task_prompt(task: str, task_kind: TaskKind) -> str:
    return PROMPT_TEMPLATE.format(task=task, verification=format_verification(task_kind))

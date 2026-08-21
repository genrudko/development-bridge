from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


JOB_TOOLS = {
    "task_list",
    "task_start",
    "job_status",
    "job_output",
    "job_cancel",
    "job_artifact_list",
}


def test_job_tools_are_registered_with_closed_repository_scoped_schemas():
    registry = build_tool_registry(build_container(BridgeSettings()))
    tools = {
        tool.name: tool for tool in registry.definitions if tool.name in JOB_TOOLS
    }

    assert set(tools) == JOB_TOOLS
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert all(
        tool.input_schema["required"][:2] == ["project_id", "repository_id"]
        for tool in tools.values()
    )
    assert tools["task_start"].input_schema["required"] == [
        "project_id",
        "repository_id",
        "task_id",
    ]
    for name in ("job_status", "job_output", "job_cancel", "job_artifact_list"):
        assert tools[name].input_schema["required"] == [
            "project_id",
            "repository_id",
            "job_id",
        ]

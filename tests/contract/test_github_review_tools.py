from app.container import build_container
from app.settings import BridgeSettings
from app.tools.registry import build_tool_registry


NEW_REVIEW_TOOLS = {
    "github_issue_comments": "issue_number",
    "github_pull_request_review_comments": "pull_number",
    "github_pull_request_files": "pull_number",
}


def test_github_review_read_tool_contracts_are_bounded_and_closed():
    registry = build_tool_registry(build_container(BridgeSettings()))

    for name, number_field in NEW_REVIEW_TOOLS.items():
        schema = registry.get(name).definition.input_schema
        assert schema["required"] == [
            "project_id",
            "repository_id",
            number_field,
        ]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["limit"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
        }

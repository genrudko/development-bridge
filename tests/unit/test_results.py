import json

from app.api.errors import BridgeError, ErrorCode
from app.api.results import failure, success, to_mcp_result


def test_success_result_is_structured_json():
    result = to_mcp_result(success("req_1", {"value": 42}, revision="rev_1"))
    payload = json.loads(result.content[0].text)
    assert payload["api_version"] == "1.0"
    assert payload["request_id"] == "req_1"
    assert payload["data"] == {"value": 42}
    assert payload["revision"] == "rev_1"
    assert result.is_error is False


def test_error_result_sets_mcp_error_flag():
    error = BridgeError(
        ErrorCode.REPOSITORY_NOT_FOUND,
        "Repository is not registered",
        details={"repository_id": "missing"},
    )
    result = to_mcp_result(failure("req_2", error))
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "REPOSITORY_NOT_FOUND"
    assert result.is_error is True


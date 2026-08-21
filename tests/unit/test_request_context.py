from app.api.context import new_request_context


def test_request_ids_are_unique_and_prefixed():
    first = new_request_context().request_id
    second = new_request_context().request_id
    assert first.startswith("req_")
    assert first != second


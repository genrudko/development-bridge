from types import SimpleNamespace

from app.chatgpt_host import chatgpt_session_fingerprint, chatgpt_session_key


def _key():
    return "openai" + "/" + "session"


def test_reads_request_context_meta():
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(meta={_key(): "conv-correlation-1"})
    )
    assert chatgpt_session_key(ctx) == "conv-correlation-1"


def test_falls_back_to_direct_meta_for_low_level_context():
    ctx = SimpleNamespace(meta={_key(): "conv-correlation-2"})
    assert chatgpt_session_key(ctx) == "conv-correlation-2"


def test_scans_multiple_sources_in_order():
    first = SimpleNamespace(meta={})
    second = SimpleNamespace(meta={_key(): "conv-correlation-3"})
    assert chatgpt_session_key(first, second) == "conv-correlation-3"


def test_missing_or_non_string_value_is_absent():
    assert chatgpt_session_key(SimpleNamespace()) is None
    assert chatgpt_session_key(SimpleNamespace(meta={_key(): 123})) is None


def test_fingerprint_is_stable_opaque_and_session_specific():
    one = SimpleNamespace(meta={_key(): "conv-correlation-1"})
    same = SimpleNamespace(meta={_key(): "conv-correlation-1"})
    other = SimpleNamespace(meta={_key(): "conv-correlation-2"})

    first = chatgpt_session_fingerprint(one)
    assert first is not None
    assert first == chatgpt_session_fingerprint(same)
    assert first != chatgpt_session_fingerprint(other)
    assert len(first) == 64
    assert "conv-correlation-1" not in first

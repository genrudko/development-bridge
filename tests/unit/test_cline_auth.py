import json
from pathlib import Path

from app.executors.cline_auth import load_configured_providers, local_auth_configured


def providers_file(config_dir: Path) -> Path:
    path = config_dir / "data" / "settings" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_local_auth_configured_true_when_provider_present(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({"version": 1, "lastUsedProvider": "cline-pass", "providers": ["cline-pass"]}),
        encoding="utf-8",
    )
    assert load_configured_providers(config) == ("cline-pass",)
    assert local_auth_configured(config) is True


def test_local_auth_configured_true_with_dict_shaped_providers(tmp_path):
    # providers.json on the real account stores providers as a dict keyed by
    # provider id (e.g. {"cline": {...}, "cline-pass": {...}}), not a list.
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({
            "version": 1,
            "lastUsedProvider": "cline-pass",
            "providers": {"cline": {"tokenSource": "local"}, "cline-pass": {"tokenSource": "local"}},
        }),
        encoding="utf-8",
    )
    assert load_configured_providers(config) == ("cline", "cline-pass")
    assert local_auth_configured(config) is True


def test_local_auth_configured_false_when_only_unrelated_provider_present(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({"version": 1, "providers": {"openai": {"tokenSource": "local"}}}),
        encoding="utf-8",
    )
    assert local_auth_configured(config) is False


def test_local_auth_configured_true_when_last_used_is_cline_pass(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({
            "version": 1,
            "lastUsedProvider": "cline-pass",
            "providers": {"openai": {"tokenSource": "local"}},
        }),
        encoding="utf-8",
    )
    assert local_auth_configured(config) is True


def test_local_auth_configured_true_from_last_used_provider_evidence(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({"version": 1, "lastUsedProvider": "cline-pass"}), encoding="utf-8"
    )
    assert local_auth_configured(config) is True


def test_local_auth_configured_false_when_missing(tmp_path):
    assert load_configured_providers(tmp_path / "missing") == ()
    assert local_auth_configured(tmp_path / "missing") is False


def test_local_auth_configured_false_when_malformed(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text("{not-json", encoding="utf-8")
    assert load_configured_providers(config) == ()
    assert local_auth_configured(config) is False


def test_local_auth_configured_false_when_no_provider_entries(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(json.dumps({"version": 1, "providers": {}}), encoding="utf-8")
    assert local_auth_configured(config) is False
    providers_file(config).write_text(json.dumps({"version": 1, "providers": []}), encoding="utf-8")
    assert local_auth_configured(config) is False


def test_load_configured_providers_ignores_non_string_entries(tmp_path):
    config = tmp_path / "cline"
    providers_file(config).write_text(
        json.dumps({"providers": ["cline", 5, None]}), encoding="utf-8"
    )
    assert load_configured_providers(config) == ("cline",)

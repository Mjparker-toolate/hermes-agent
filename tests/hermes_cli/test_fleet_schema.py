"""Fleet document invariants: cap, loopback callbacks, secrets-as-names."""

from __future__ import annotations

import pytest

from hermes_cli.config_defaults import DEFAULT_CONFIG, OPTIONAL_ENV_VARS
from hermes_cli.fleet_schema import (
    V1_MAX_CONCURRENCY,
    FleetConfigError,
    example_fleet_config,
    is_loopback_url,
    load_fleet_document,
    normalize_fleet_config,
)


def _doc(**overrides):
    data = example_fleet_config()
    data.update(overrides)
    return data


def test_example_config_normalizes_and_stays_at_or_under_v1_cap():
    normalized = normalize_fleet_config(example_fleet_config())
    assert normalized["fleet_id"] == "local-dev"
    assert 1 <= normalized["max_concurrency"] <= V1_MAX_CONCURRENCY
    assert normalized["replicas"] <= normalized["max_concurrency"]
    assert normalized["kill_switch"] is False
    assert normalized["secrets_ref"] == ["OPENROUTER_API_KEY"]
    assert is_loopback_url(normalized["webhook_callback_url"])


def test_default_config_fleet_cap_matches_schema_ceiling():
    """config.yaml default and the schema share one v1 ceiling — not a frozen version."""
    assert DEFAULT_CONFIG["fleet"]["max_concurrency"] == V1_MAX_CONCURRENCY
    assert DEFAULT_CONFIG["fleet"]["http"]["host"] == "127.0.0.1"
    assert OPTIONAL_ENV_VARS["FLEET_HTTP_TOKEN"]["password"] is True
    assert OPTIONAL_ENV_VARS["FLEET_HTTP_TOKEN"]["category"] == "setting"


def test_max_concurrency_above_v1_ceiling_is_refused():
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(max_concurrency=V1_MAX_CONCURRENCY + 1))
    assert exc.value.code == "concurrency_cap"


def test_replicas_cannot_exceed_max_concurrency():
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(max_concurrency=2, replicas=3))
    assert exc.value.code == "concurrency_cap"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://10.0.0.1/hook",
        "ftp://127.0.0.1/hook",
        "http://192.168.1.10:5678/webhook",
    ],
)
def test_non_loopback_callback_is_refused(url):
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(webhook_callback_url=url))
    assert exc.value.code == "callback_not_loopback"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:5678/webhook/hermes-fleet",
        "http://localhost:8080/cb",
        "https://[::1]/hook",
    ],
)
def test_loopback_callback_is_accepted(url):
    normalized = normalize_fleet_config(_doc(webhook_callback_url=url))
    assert normalized["webhook_callback_url"] == url


def test_embedded_api_key_value_is_rejected():
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(api_key="sk-live-not-a-name"))
    assert exc.value.code == "secrets_embedded"


def test_secrets_ref_rejects_key_equals_value():
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(secrets_ref=["OPENROUTER_API_KEY=sk-secret"]))
    assert exc.value.code == "secrets_embedded"


def test_secrets_ref_rejects_lowercase_or_value_shaped_names():
    with pytest.raises(FleetConfigError) as exc:
        normalize_fleet_config(_doc(secrets_ref=["not-an-env"]))
    assert exc.value.code == "secrets_embedded"


def test_yaml_and_json_documents_round_trip_to_the_same_shape():
    json_text = """
    {"fleet_id": "from-json", "max_concurrency": 2, "replicas": 1,
     "secrets_ref": ["OPENROUTER_API_KEY"]}
    """
    yaml_text = """
fleet_id: from-yaml
max_concurrency: 2
replicas: 1
secrets_ref:
  - OPENROUTER_API_KEY
"""
    from_json = load_fleet_document(json_text, source="json")
    from_yaml = load_fleet_document(yaml_text, source="yaml")
    assert from_json["fleet_id"] == "from-json"
    assert from_yaml["fleet_id"] == "from-yaml"
    assert from_json["max_concurrency"] == from_yaml["max_concurrency"] == 2
    assert from_json["retry"]["max_attempts"] == from_yaml["retry"]["max_attempts"]


def test_unknown_keys_and_invalid_role_are_rejected():
    with pytest.raises(FleetConfigError, match="Unknown"):
        normalize_fleet_config(_doc(cloud_workers=4))
    with pytest.raises(FleetConfigError, match="role"):
        normalize_fleet_config(_doc(worker_template={"role": "root"}))


def test_retry_max_attempts_zero_is_valid():
    normalized = normalize_fleet_config(_doc(retry={"max_attempts": 0}))
    assert normalized["retry"]["max_attempts"] == 0

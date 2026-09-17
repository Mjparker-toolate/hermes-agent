"""Fleet config schema and validation for the v1 Hermes↔orchestrator glue.

A fleet document is YAML or JSON. Secrets are **names only** (``secrets_ref``);
values never belong in the document. v1 hard-caps ``max_concurrency`` at 5 and
refuses non-loopback callback URLs so a local n8n/ClawHub caller cannot fan
out to paid cloud or an open SSRF sink.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

V1_MAX_CONCURRENCY = 5
DEFAULT_MAX_CONCURRENCY = 5
FLEET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_EMBEDDED_SECRET_KEYS = frozenset({
    "secret", "token", "password", "api_key", "apikey", "authorization",
    "access_token", "private_key", "client_secret",
})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "ip6-localhost", "ip6-loopback"})

# Worker statuses counted against the concurrency cap.
LIVE_WORKER_STATUSES = frozenset({"pending", "idle", "running", "draining"})
TERMINAL_WORKER_STATUSES = frozenset({"stopped", "failed"})

DEFAULT_WORKER_TEMPLATE = {
    "model": "",
    "provider": "",
    "tools": [],
    "skills": [],
    "role": "leaf",
    "goal": "",
}

DEFAULT_BACKOFF = {
    "initial_seconds": 1.0,
    "max_seconds": 30.0,
    "multiplier": 2.0,
}

DEFAULT_RETRY = {
    "max_attempts": 2,
}


class FleetConfigError(ValueError):
    """The fleet document is structurally invalid or violates a v1 invariant."""

    def __init__(self, message: str, *, code: str = "invalid_config") -> None:
        super().__init__(message)
        self.code = code


def is_loopback_host(host: str | None) -> bool:
    """True when *host* can only accept same-machine connections."""
    if not host:
        return False
    cleaned = host.strip().lower().strip("[]")
    if cleaned in _LOOPBACK_HOSTS:
        return True
    try:
        return bool(ipaddress.ip_address(cleaned).is_loopback)
    except ValueError:
        return False


def is_loopback_url(url: str) -> bool:
    """True when *url* is http(s) targeting a loopback host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return is_loopback_host(parsed.hostname)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FleetConfigError(f"{label} must be a mapping.")
    return dict(value)


def _optional_str(value: Any, label: str, *, allow_empty: bool = True) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FleetConfigError(f"{label} must be a string.")
    text = value.strip()
    if not text and not allow_empty:
        raise FleetConfigError(f"{label} must be a non-empty string.")
    return text


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
        return items
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FleetConfigError(f"{label} must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _positive_number(value: Any, label: str, *, default: float, minimum: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FleetConfigError(f"{label} must be a number.")
    number = float(value)
    if number < minimum:
        raise FleetConfigError(f"{label} must be >= {minimum}.")
    return number


def _forbid_embedded_secrets(document: Mapping[str, Any], *, path: str = "") -> None:
    """Reject credential values anywhere except ``secrets_ref`` names."""
    for key, value in document.items():
        here = f"{path}.{key}" if path else key
        lowered = str(key).lower()
        if lowered in _EMBEDDED_SECRET_KEYS and here != "secrets_ref":
            if isinstance(value, str) and value.strip():
                raise FleetConfigError(
                    f"{here} embeds a secret value; list the env-var name under secrets_ref instead.",
                    code="secrets_embedded",
                )
            if isinstance(value, (dict, list)) and value:
                raise FleetConfigError(
                    f"{here} must not carry secret material; use secrets_ref names only.",
                    code="secrets_embedded",
                )
        if isinstance(value, Mapping):
            _forbid_embedded_secrets(value, path=here)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    _forbid_embedded_secrets(item, path=f"{here}[{index}]")


def _worker_template(raw: Any) -> dict[str, Any]:
    template = dict(DEFAULT_WORKER_TEMPLATE)
    if raw is None:
        return template
    data = _require_mapping(raw, "worker_template")
    unknown = set(data) - set(DEFAULT_WORKER_TEMPLATE)
    if unknown:
        raise FleetConfigError(
            f"worker_template has unknown keys: {sorted(unknown)}."
        )
    template["model"] = _optional_str(data.get("model"), "worker_template.model")
    template["provider"] = _optional_str(data.get("provider"), "worker_template.provider")
    template["tools"] = _string_list(data.get("tools"), "worker_template.tools")
    template["skills"] = _string_list(data.get("skills"), "worker_template.skills")
    role = _optional_str(data.get("role"), "worker_template.role") or "leaf"
    if role not in {"leaf", "orchestrator"}:
        raise FleetConfigError("worker_template.role must be 'leaf' or 'orchestrator'.")
    template["role"] = role
    template["goal"] = _optional_str(data.get("goal"), "worker_template.goal")
    return template


def _backoff(raw: Any) -> dict[str, float]:
    data = _require_mapping(raw, "backoff") if raw is not None else {}
    unknown = set(data) - set(DEFAULT_BACKOFF)
    if unknown:
        raise FleetConfigError(f"backoff has unknown keys: {sorted(unknown)}.")
    initial = _positive_number(
        data.get("initial_seconds"), "backoff.initial_seconds",
        default=DEFAULT_BACKOFF["initial_seconds"], minimum=0.1,
    )
    maximum = _positive_number(
        data.get("max_seconds"), "backoff.max_seconds",
        default=DEFAULT_BACKOFF["max_seconds"], minimum=initial,
    )
    multiplier = _positive_number(
        data.get("multiplier"), "backoff.multiplier",
        default=DEFAULT_BACKOFF["multiplier"], minimum=1.0,
    )
    return {
        "initial_seconds": initial,
        "max_seconds": maximum,
        "multiplier": multiplier,
    }


def _retry(raw: Any) -> dict[str, int]:
    data = _require_mapping(raw, "retry") if raw is not None else {}
    unknown = set(data) - set(DEFAULT_RETRY)
    if unknown:
        raise FleetConfigError(f"retry has unknown keys: {sorted(unknown)}.")
    attempts = data.get("max_attempts", DEFAULT_RETRY["max_attempts"])
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise FleetConfigError("retry.max_attempts must be an integer >= 0.")
    if attempts > 8:
        raise FleetConfigError("retry.max_attempts cannot exceed 8 in v1.")
    return {"max_attempts": attempts}


def _secrets_ref(raw: Any) -> list[str]:
    names = _string_list(raw, "secrets_ref")
    for name in names:
        if not SECRET_NAME_RE.fullmatch(name):
            raise FleetConfigError(
                f"secrets_ref entry {name!r} is not an env-var name "
                "(A-Z, digits, underscore; names only, never values).",
                code="secrets_embedded",
            )
        if "=" in name or ":" in name:
            raise FleetConfigError(
                "secrets_ref must be names only — never KEY=value.",
                code="secrets_embedded",
            )
    return names


def _max_concurrency(raw: Any) -> int:
    if raw is None:
        return DEFAULT_MAX_CONCURRENCY
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise FleetConfigError("max_concurrency must be an integer.")
    if raw < 1:
        raise FleetConfigError("max_concurrency must be >= 1.")
    if raw > V1_MAX_CONCURRENCY:
        raise FleetConfigError(
            f"max_concurrency cannot exceed {V1_MAX_CONCURRENCY} in v1.",
            code="concurrency_cap",
        )
    return raw


def normalize_fleet_config(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical fleet config dict or raise :class:`FleetConfigError`."""
    data = _require_mapping(document, "fleet config")
    _forbid_embedded_secrets(data)
    known = {
        "fleet_id", "max_concurrency", "worker_template", "webhook_callback_url",
        "secrets_ref", "backoff", "retry", "kill_switch", "replicas",
    }
    unknown = set(data) - known
    if unknown:
        raise FleetConfigError(f"Unknown fleet config keys: {sorted(unknown)}.")

    fleet_id = _optional_str(data.get("fleet_id"), "fleet_id", allow_empty=False)
    if not FLEET_ID_RE.fullmatch(fleet_id):
        raise FleetConfigError(
            "fleet_id must be 1-64 chars of [A-Za-z0-9._-] starting with alphanumeric."
        )

    callback = _optional_str(data.get("webhook_callback_url"), "webhook_callback_url")
    if callback and not is_loopback_url(callback):
        raise FleetConfigError(
            "webhook_callback_url must be an http(s) loopback URL in v1 "
            "(127.0.0.1 / localhost / ::1).",
            code="callback_not_loopback",
        )

    kill_switch = data.get("kill_switch", False)
    if not isinstance(kill_switch, bool):
        raise FleetConfigError("kill_switch must be a boolean.")

    replicas = data.get("replicas")
    max_concurrency = _max_concurrency(data.get("max_concurrency"))
    if replicas is None:
        replica_count = 1
    else:
        if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
            raise FleetConfigError("replicas must be an integer >= 0.")
        replica_count = replicas
    if replica_count > max_concurrency:
        raise FleetConfigError(
            f"replicas ({replica_count}) exceeds max_concurrency ({max_concurrency}).",
            code="concurrency_cap",
        )

    return {
        "fleet_id": fleet_id,
        "max_concurrency": max_concurrency,
        "worker_template": _worker_template(data.get("worker_template")),
        "webhook_callback_url": callback,
        "secrets_ref": _secrets_ref(data.get("secrets_ref")),
        "backoff": _backoff(data.get("backoff")),
        "retry": _retry(data.get("retry")),
        "kill_switch": kill_switch,
        "replicas": replica_count,
    }


def load_fleet_document(text: str, *, source: str = "document") -> dict[str, Any]:
    """Parse YAML or JSON text into a normalized fleet config."""
    stripped = text.strip()
    if not stripped:
        raise FleetConfigError(f"{source} is empty.")
    payload: Any
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - PyYAML is a runtime dep
            raise FleetConfigError(f"{source} is not JSON and PyYAML is unavailable.") from exc
        payload = yaml.safe_load(stripped)
    if not isinstance(payload, Mapping):
        raise FleetConfigError(f"{source} must be a YAML/JSON mapping.")
    return normalize_fleet_config(payload)


def example_fleet_config() -> dict[str, Any]:
    """Canonical example used by docs, the skill template, and tests."""
    return copy.deepcopy({
        "fleet_id": "local-dev",
        "max_concurrency": 3,
        "worker_template": {
            "model": "",
            "provider": "",
            "tools": ["terminal", "file"],
            "skills": ["hermes-fleet"],
            "role": "leaf",
            "goal": "",
        },
        "webhook_callback_url": "http://127.0.0.1:5678/webhook/hermes-fleet",
        "secrets_ref": ["OPENROUTER_API_KEY"],
        "backoff": dict(DEFAULT_BACKOFF),
        "retry": dict(DEFAULT_RETRY),
        "kill_switch": False,
        "replicas": 1,
    })

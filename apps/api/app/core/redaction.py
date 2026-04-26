from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus

from app.core.config import get_settings

SENSITIVE_REDACTION = "***"
SENSITIVE_QUERY_PARAM_NAMES = (
    "serviceKey",
    "certkey",
    "key",
    "apiKey",
    "api_key",
    "access_token",
    "token",
)


def redact_sensitive_text(
    value: str | None,
    *,
    extra_secret_values: Iterable[str | None] = (),
) -> str | None:
    if value is None:
        return None

    redacted = value
    for parameter_name in SENSITIVE_QUERY_PARAM_NAMES:
        redacted = re.sub(
            rf"(?i)(^|[?&;\s])({re.escape(parameter_name)}=)([^&;\s]+)",
            lambda match: f"{match.group(1)}{match.group(2)}{SENSITIVE_REDACTION}",
            redacted,
        )

    settings = get_settings()
    configured_secret_values = (
        settings.data_go_service_key,
        settings.opinet_api_key,
        settings.expressway_api_key,
    )
    for secret_value in (*configured_secret_values, *extra_secret_values):
        if not secret_value:
            continue
        stripped_secret = secret_value.strip()
        if len(stripped_secret) < 6:
            continue
        redacted = _replace_secret_variants(redacted, stripped_secret)
    return redacted


def _replace_secret_variants(value: str, secret: str) -> str:
    redacted = value
    for candidate in {secret, quote(secret, safe=""), quote_plus(secret, safe="")}:
        redacted = redacted.replace(candidate, SENSITIVE_REDACTION)
    return redacted

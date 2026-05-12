from __future__ import annotations

from krex import KexAuthError, KexClient

from app.core.config import Settings, get_settings


def build_kex_client(settings: Settings | None = None) -> KexClient:
    resolved_settings = settings or get_settings()
    ex_api_key = resolved_settings.kex_ex_api_key or resolved_settings.expressway_api_key
    go_api_key = resolved_settings.kex_go_api_key or resolved_settings.data_go_service_key
    if not ex_api_key and not go_api_key:
        raise KexAuthError(
            "TRIPMATE_KEX_EX_API_KEY/TRIPMATE_EXPRESSWAY_API_KEY or "
            "TRIPMATE_KEX_GO_API_KEY/TRIPMATE_DATA_GO_SERVICE_KEY is required."
        )
    return KexClient(
        ex_api_key=ex_api_key,
        go_api_key=go_api_key,
        timeout=resolved_settings.kex_timeout_seconds,
        strict_no_data=False,
        max_retries=resolved_settings.kex_max_retries,
        retry_backoff=resolved_settings.kex_retry_backoff_seconds,
    )

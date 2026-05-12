from __future__ import annotations

from visitkorea import KrTourApiClient, MobileOS, TourApiAuthError, TourApiHubClient

from app.core.config import Settings, get_settings


def build_kto_kor_client(settings: Settings | None = None) -> KrTourApiClient:
    resolved_settings = settings or get_settings()
    return KrTourApiClient(
        service_key=_service_key(resolved_settings),
        mobile_os=_mobile_os(resolved_settings.kto_mobile_os),
        mobile_app=resolved_settings.kto_mobile_app,
        timeout=resolved_settings.kto_timeout_seconds,
        retries=resolved_settings.kto_max_retries,
    )


def build_kto_hub_client(settings: Settings | None = None) -> TourApiHubClient:
    resolved_settings = settings or get_settings()
    return TourApiHubClient(
        service_key=_service_key(resolved_settings),
        mobile_os=_mobile_os(resolved_settings.kto_mobile_os),
        mobile_app=resolved_settings.kto_mobile_app,
        timeout=resolved_settings.kto_timeout_seconds,
        retries=resolved_settings.kto_max_retries,
    )


def _mobile_os(value: str) -> MobileOS:
    return MobileOS(value)


def _service_key(settings: Settings) -> str:
    if not settings.kto_service_key:
        raise TourApiAuthError("TRIPMATE_KTO_SERVICE_KEY is required.")
    return settings.kto_service_key

"""환경변수 + 설정 (pydantic-settings).

루트 `.env.example` 항목과 동기.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 환경
    pinvi_environment: str = Field(default="development")

    # Database
    pinvi_database_url: str = Field(
        default="postgresql+asyncpg://pinvi:pinvi_dev_password@localhost:5432/pinvi"
    )
    pinvi_database_pool_size: int = 10

    # JWT / 세션
    pinvi_jwt_secret_key: str = Field(default="pinvi-local-jwt-secret-change-me", min_length=32)
    pinvi_access_token_minutes: int = 15
    pinvi_refresh_token_days: int = 7
    pinvi_admin_session_ttl: int = 3600
    pinvi_mcp_jwt_secret: str = Field(default="pinvi-local-mcp-secret-change-me", min_length=32)
    pinvi_mcp_token_default_days: int = 30
    pinvi_mcp_rate_limit_per_minute: int = 60

    # Resend
    pinvi_resend_api_key: str = ""
    pinvi_resend_from_email: str = "Pinvi <noreply@send.pinvi.local>"
    pinvi_resend_timeout_seconds: int = 5
    pinvi_resend_webhook_secret: str = ""
    pinvi_resend_webhook_allow_unsigned: bool = False
    pinvi_web_base_url: str = "http://localhost:12505"
    pinvi_email_verification_path: str = "/verify-email"
    pinvi_auth_reset_path: str = Field(
        default="/reset-password",
        validation_alias="PINVI_PASSWORD_RESET_PATH",
    )

    # OAuth (Sprint 2부터 실제 사용)
    pinvi_google_oauth_client_id: str = ""
    pinvi_google_oauth_client_secret: str = ""
    pinvi_naver_oauth_client_id: str = ""
    pinvi_naver_oauth_client_secret: str = ""
    pinvi_kakao_oauth_rest_api_key: str = ""
    pinvi_kakao_oauth_client_secret: str = ""
    pinvi_oauth_callback_base_url: str = "http://localhost:12501"
    pinvi_oauth_state_ttl_seconds: int = 600
    pinvi_oauth_http_timeout_seconds: int = 5

    # RustFS (S3 호환 객체 저장소)
    pinvi_rustfs_endpoint_url: str = "http://localhost:12101"
    pinvi_rustfs_public_endpoint_url: str = "http://127.0.0.1:12101"
    pinvi_rustfs_bucket: str = "pinvi-media"
    pinvi_rustfs_access_key_id: str = "rustfsadmin"
    pinvi_rustfs_secret_access_key: str = "rustfsadmin"  # noqa: S105 - 로컬 dev 기본값
    pinvi_rustfs_presigned_url_expires_seconds: int = 900
    pinvi_rustfs_max_upload_bytes: int = 10_485_760
    pinvi_rustfs_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "video/mp4",
            "application/pdf",
        ]
    )
    pinvi_rustfs_public_base_url: str = ""
    # Trip/POI 첨부 개수 상한(남용 방지, T-105)
    pinvi_max_attachments_per_target: int = 30

    # kor-travel-map 독립 프로그램 (지도 feature OpenAPI HTTP, ADR-026/027)
    # `docs/integrations/kor-travel-map-rest-api.md` §1 — 전 표면 API/Admin API :12301.
    pinvi_kor_travel_map_api_base_url: str = "http://localhost:12301"
    # admin feature change(`/v1/admin/features*`, T-180)도 같은 호스트 :12301.
    pinvi_kor_travel_map_admin_base_url: str = "http://localhost:12301"
    # 인증은 인프라 계층(reverse proxy / IP allowlist). 설정 시 X-Kor-Travel-Map-Service-Token 전달.
    pinvi_kor_travel_map_service_token: str = ""
    # admin-path 전용 서비스 토큰(미설정 시 공용 service token fallback).
    # §7 확정(kor_travel_map T-217c): 운영 인증은 인프라 계층(SSO/IP allowlist) — token은 선택 pass-through.
    pinvi_kor_travel_map_admin_service_token: str = ""
    pinvi_kor_travel_map_timeout_seconds: float = 5.0
    pinvi_kor_travel_map_max_attempts: int = 3
    pinvi_kor_travel_map_batch_chunk_size: int = 200  # /v1/features/batch cap

    # kor-travel-geo v2 REST (geocoding/주소/행정구역, ADR-025) — `docs/integrations/kor-travel-geo.md`.
    pinvi_kor_travel_geo_base_url: str = "http://localhost:8888"
    pinvi_kor_travel_geo_timeout_seconds: float = 5.0
    pinvi_kor_travel_geo_max_attempts: int = 3

    # Telegram Bot 알림 (T-106) — `docs/integrations/telegram.md`.
    # bot token 원본은 DB 저장 X(§1), 로그는 mask_token으로만(§9).
    pinvi_telegram_api_base: str = "https://api.telegram.org"
    pinvi_telegram_timeout_seconds: float = 5.0
    pinvi_telegram_bot_token_default: str = ""  # 시스템/Admin 봇
    pinvi_telegram_admin_chat_id: str = ""
    # outbox drain worker (§8)
    pinvi_telegram_outbox_worker_enabled: bool = True
    pinvi_telegram_outbox_drain_interval_seconds: float = 5.0
    pinvi_telegram_outbox_batch_size: int = 50

    # 위치 감사 async outbox drain worker (T-146 / D-20)
    pinvi_location_audit_outbox_worker_enabled: bool = True
    pinvi_location_audit_outbox_drain_interval_seconds: float = 1.0
    pinvi_location_audit_outbox_batch_size: int = 200

    # Feature 조회 process-local TTL 캐시 (T-146 / D-26)
    pinvi_feature_cache_enabled: bool = True
    pinvi_feature_cache_ttl_seconds: float = 60.0
    pinvi_feature_cache_max_size: int = 10000

    # CORS
    pinvi_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:12505", "http://127.0.0.1:12505"]
    )

    # Geofencing (ADR-018) — 기본은 비활성, 운영에서 3차 fallback으로 활성.
    pinvi_geofence_enabled: bool = False
    pinvi_geofence_allowed_countries: list[str] = Field(default_factory=lambda: ["KR"])
    pinvi_geofence_country_header: str = "CF-IPCountry"
    pinvi_geofence_trusted_proxy_header: str = "X-Pinvi-Geofence-Proxy"
    pinvi_geofence_trusted_proxy_secret: str = ""
    pinvi_geofence_trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    pinvi_geofence_mtls_verified_header: str = ""
    pinvi_geofence_mtls_verified_value: str = "SUCCESS"
    pinvi_geofence_block_unknown: bool = False
    pinvi_geofence_bypass_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/health/db",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
    )

    # WebSocket safety guard (ADR-035)
    pinvi_ws_client_rate_per_second: int = 5
    pinvi_ws_client_rate_per_minute: int = 60
    pinvi_ws_rate_limit_close_grace_seconds: float = 30.0
    pinvi_ws_max_connections_per_trip: int = 10
    pinvi_ws_max_connections_total: int = 200
    pinvi_ws_send_timeout_seconds: float = 2.0

    # Sentry
    pinvi_sentry_dsn: str = ""
    pinvi_sentry_environment: str = "development"
    pinvi_sentry_release: str = ""
    pinvi_sentry_traces_sample_rate: float = 0.1
    pinvi_sentry_profiles_sample_rate: float = 0.0

    # Prometheus metrics (Sprint 5 observability)
    pinvi_prometheus_metrics_enabled: bool = True
    pinvi_prometheus_metrics_path: str = "/metrics"
    pinvi_prometheus_exclude_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/health/db", "/metrics"]
    )

    # 운영 부트스트랩
    pinvi_bootstrap_admin_email: str = "admin@ad.min"
    pinvi_bootstrap_admin_password: str = ""

    # Backup / Restore (ADR-022)
    pinvi_backup_dir: str = ".tmp/backups"
    pinvi_backup_script_path: str = "scripts/backup-db.sh"
    pinvi_restore_script_path: str = "scripts/restore-db.sh"
    pinvi_restore_hotswap_script_path: str = "scripts/restore-hotswap.sh"
    pinvi_backup_timeout_seconds: int = 900
    pinvi_restore_timeout_seconds: int = 3600
    pinvi_backup_schema: str = "app"
    pinvi_restore_database_url: str = ""
    pinvi_restore_hotswap_execute: bool = False
    pinvi_restore_drain_command: str = ""
    pinvi_restore_allow_no_drain: bool = False
    pinvi_restore_app_role: str = ""

    # Feature flag
    pinvi_enable_seed: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

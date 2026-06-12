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
    tripmate_environment: str = Field(default="development")

    # Database
    tripmate_database_url: str = Field(
        default="postgresql+asyncpg://tripmate:tripmate_dev_password@localhost:5432/tripmate"
    )
    tripmate_database_pool_size: int = 10

    # JWT / 세션
    tripmate_jwt_secret_key: str = Field(
        default="tripmate-local-jwt-secret-change-me", min_length=32
    )
    tripmate_access_token_minutes: int = 15
    tripmate_refresh_token_days: int = 7
    tripmate_admin_session_ttl: int = 3600
    tripmate_mcp_jwt_secret: str = Field(
        default="tripmate-local-mcp-secret-change-me", min_length=32
    )
    tripmate_mcp_token_default_days: int = 30
    tripmate_mcp_rate_limit_per_minute: int = 60

    # Resend
    tripmate_resend_api_key: str = ""
    tripmate_resend_from_email: str = "TripMate <noreply@send.tripmate.local>"
    tripmate_resend_timeout_seconds: int = 5
    tripmate_resend_webhook_secret: str = ""
    tripmate_resend_webhook_allow_unsigned: bool = False
    tripmate_web_base_url: str = "http://localhost:12505"
    tripmate_email_verification_path: str = "/verify-email"
    tripmate_auth_reset_path: str = Field(
        default="/reset-password",
        validation_alias="TRIPMATE_PASSWORD_RESET_PATH",
    )

    # OAuth (Sprint 2부터 실제 사용)
    tripmate_google_oauth_client_id: str = ""
    tripmate_google_oauth_client_secret: str = ""
    tripmate_naver_oauth_client_id: str = ""
    tripmate_naver_oauth_client_secret: str = ""
    tripmate_kakao_oauth_rest_api_key: str = ""
    tripmate_kakao_oauth_client_secret: str = ""
    tripmate_oauth_callback_base_url: str = "http://localhost:12501"
    tripmate_oauth_state_ttl_seconds: int = 600
    tripmate_oauth_http_timeout_seconds: int = 5

    # RustFS (S3 호환 객체 저장소)
    tripmate_rustfs_endpoint_url: str = "http://localhost:12101"
    tripmate_rustfs_public_endpoint_url: str = "http://127.0.0.1:12101"
    tripmate_rustfs_bucket: str = "tripmate-media"
    tripmate_rustfs_access_key_id: str = "rustfsadmin"
    tripmate_rustfs_secret_access_key: str = "rustfsadmin"  # noqa: S105 - 로컬 dev 기본값
    tripmate_rustfs_presigned_url_expires_seconds: int = 900
    tripmate_rustfs_max_upload_bytes: int = 10_485_760
    tripmate_rustfs_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "video/mp4",
            "application/pdf",
        ]
    )
    tripmate_rustfs_public_base_url: str = ""
    # Trip/POI 첨부 개수 상한(남용 방지, T-105)
    tripmate_max_attachments_per_target: int = 30

    # krtour-map 독립 프로그램 (지도 feature OpenAPI HTTP, ADR-026/027)
    # `docs/integrations/krtour-map-rest-api.md` §1 — 전 표면 API/Admin API :12301.
    tripmate_krtour_map_api_base_url: str = "http://localhost:12301"
    # admin feature change(`/v1/admin/features*`, T-180)도 같은 호스트 :12301.
    tripmate_krtour_map_admin_base_url: str = "http://localhost:12301"
    # 인증은 인프라 계층(reverse proxy / IP allowlist). 설정 시 X-Krtour-Service-Token 전달.
    tripmate_krtour_map_service_token: str = ""
    # admin-path 전용 서비스 토큰(미설정 시 공용 service token fallback).
    # §7 확정(krtour T-217c): 운영 인증은 인프라 계층(SSO/IP allowlist) — token은 선택 pass-through.
    tripmate_krtour_map_admin_service_token: str = ""
    tripmate_krtour_map_timeout_seconds: float = 5.0
    tripmate_krtour_map_max_attempts: int = 3
    tripmate_krtour_map_batch_chunk_size: int = 200  # /v1/features/batch cap

    # tripmate-agent 독립 프로그램 (후속 외부 연계, ADR-020 계열)
    tripmate_agent_api_base_url: str = "http://localhost:12401"

    # kraddr-geo v2 REST (geocoding/주소/행정구역, ADR-025) — `docs/integrations/kraddr-geo.md`.
    tripmate_kraddr_geo_base_url: str = "http://localhost:8888"
    tripmate_kraddr_geo_timeout_seconds: float = 5.0
    tripmate_kraddr_geo_max_attempts: int = 3

    # Telegram Bot 알림 (T-106) — `docs/integrations/telegram.md`.
    # bot token 원본은 DB 저장 X(§1), 로그는 mask_token으로만(§9).
    tripmate_telegram_api_base: str = "https://api.telegram.org"
    tripmate_telegram_timeout_seconds: float = 5.0
    tripmate_telegram_bot_token_default: str = ""  # 시스템/Admin 봇
    tripmate_telegram_admin_chat_id: str = ""
    # outbox drain worker (§8)
    tripmate_telegram_outbox_worker_enabled: bool = True
    tripmate_telegram_outbox_drain_interval_seconds: float = 5.0
    tripmate_telegram_outbox_batch_size: int = 50

    # 위치 감사 async outbox drain worker (T-146 / D-20)
    tripmate_location_audit_outbox_worker_enabled: bool = True
    tripmate_location_audit_outbox_drain_interval_seconds: float = 1.0
    tripmate_location_audit_outbox_batch_size: int = 200

    # Feature 조회 process-local TTL 캐시 (T-146 / D-26)
    tripmate_feature_cache_enabled: bool = True
    tripmate_feature_cache_ttl_seconds: float = 60.0
    tripmate_feature_cache_max_size: int = 10000

    # CORS
    tripmate_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:12505", "http://127.0.0.1:12505"]
    )

    # Geofencing (ADR-018) — 기본은 비활성, 운영에서 3차 fallback으로 활성.
    tripmate_geofence_enabled: bool = False
    tripmate_geofence_allowed_countries: list[str] = Field(default_factory=lambda: ["KR"])
    tripmate_geofence_country_header: str = "CF-IPCountry"
    tripmate_geofence_trusted_proxy_header: str = "X-TripMate-Geofence-Proxy"
    tripmate_geofence_trusted_proxy_secret: str = ""
    tripmate_geofence_trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    tripmate_geofence_mtls_verified_header: str = ""
    tripmate_geofence_mtls_verified_value: str = "SUCCESS"
    tripmate_geofence_block_unknown: bool = False
    tripmate_geofence_bypass_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/health/db", "/docs", "/redoc", "/openapi.json"]
    )

    # WebSocket safety guard (ADR-035)
    tripmate_ws_client_rate_per_second: int = 5
    tripmate_ws_client_rate_per_minute: int = 60
    tripmate_ws_rate_limit_close_grace_seconds: float = 30.0
    tripmate_ws_max_connections_per_trip: int = 10
    tripmate_ws_max_connections_total: int = 200
    tripmate_ws_send_timeout_seconds: float = 2.0

    # Sentry
    tripmate_sentry_dsn: str = ""
    tripmate_sentry_environment: str = "development"
    tripmate_sentry_release: str = ""
    tripmate_sentry_traces_sample_rate: float = 0.1
    tripmate_sentry_profiles_sample_rate: float = 0.0

    # 운영 부트스트랩
    tripmate_bootstrap_admin_email: str = "admin@ad.min"
    tripmate_bootstrap_admin_password: str = ""

    # Backup / Restore (ADR-022)
    tripmate_backup_dir: str = ".tmp/backups"
    tripmate_backup_script_path: str = "scripts/backup-db.sh"
    tripmate_restore_script_path: str = "scripts/restore-db.sh"
    tripmate_restore_hotswap_script_path: str = "scripts/restore-hotswap.sh"
    tripmate_backup_timeout_seconds: int = 900
    tripmate_restore_timeout_seconds: int = 3600
    tripmate_backup_schema: str = "app"
    tripmate_restore_database_url: str = ""
    tripmate_restore_hotswap_execute: bool = False
    tripmate_restore_drain_command: str = ""
    tripmate_restore_allow_no_drain: bool = False
    tripmate_restore_app_role: str = ""

    # Feature flag
    tripmate_enable_seed: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

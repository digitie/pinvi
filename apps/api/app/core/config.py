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
        default="postgresql+asyncpg://tripmate:tripmate_dev_password@localhost:55432/tripmate"
    )
    tripmate_database_pool_size: int = 10

    # JWT / 세션
    tripmate_jwt_secret_key: str = Field(
        default="tripmate-local-jwt-secret-change-me", min_length=32
    )
    tripmate_access_token_minutes: int = 15
    tripmate_refresh_token_days: int = 7
    tripmate_admin_session_ttl: int = 3600

    # Resend
    tripmate_resend_api_key: str = ""
    tripmate_resend_from_email: str = "TripMate <noreply@send.tripmate.local>"
    tripmate_resend_timeout_seconds: int = 5
    tripmate_resend_webhook_secret: str = ""
    tripmate_web_base_url: str = "http://localhost:9022"
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
    tripmate_oauth_callback_base_url: str = "http://localhost:9021"
    tripmate_oauth_state_ttl_seconds: int = 600
    tripmate_oauth_http_timeout_seconds: int = 5

    # CORS
    tripmate_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:9022", "http://127.0.0.1:9022"]
    )

    # Geofencing (ADR-018) — 기본은 비활성, 운영에서 3차 fallback으로 활성.
    tripmate_geofence_enabled: bool = False
    tripmate_geofence_allowed_countries: list[str] = Field(default_factory=lambda: ["KR"])
    tripmate_geofence_country_header: str = "CF-IPCountry"
    tripmate_geofence_block_unknown: bool = False
    tripmate_geofence_bypass_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/health/db", "/docs", "/redoc", "/openapi.json"]
    )

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
    tripmate_backup_timeout_seconds: int = 900
    tripmate_backup_schema: str = "app"

    # Feature flag
    tripmate_enable_seed: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

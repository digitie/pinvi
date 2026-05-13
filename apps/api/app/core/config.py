from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRIPMATE_",
        extra="ignore",
    )

    app_name: str = "TripMate API"
    app_version: str = "0.1.0"
    environment: str = "local"
    database_url: str = Field(
        default="postgresql+psycopg://tripmate:tripmate_dev_password@localhost:55432/tripmate"
    )
    access_token_cookie_name: str = "tripmate_access"
    refresh_token_cookie_name: str = "tripmate_refresh"
    jwt_secret_key: str = "tripmate-local-jwt-secret-change-me"
    jwt_issuer: str = "tripmate-api"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cors_origins: list[str] = [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    dagster_download_dir: str = ".tmp/dagster-downloads"
    dagster_log_dir: str = ".tmp/dagster-logs"
    etl_config_path: str = "config/etl-datasets.json"
    kma_mid_term_region_config_path: str = "config/kma-mid-term-regions.json"
    data_go_service_key: str | None = None
    kma_short_term_request_delay_seconds: float = 1.0
    kma_short_term_rate_limit_max_retries: int = 2
    kma_short_term_rate_limit_backoff_seconds: float = 300.0
    khoa_api_key: str | None = None
    mof_beach_service_key: str | None = None
    opinet_api_key: str | None = None
    opinet_timeout_seconds: float = 10.0
    opinet_max_retries: int = 2
    opinet_retry_backoff_seconds: float = 0.5
    expressway_api_key: str | None = None
    kto_service_key: str | None = None
    kto_mobile_app: str = "TripMate"
    kto_mobile_os: str = "WEB"
    kto_timeout_seconds: float = 10.0
    kto_max_retries: int = 2
    kex_ex_api_key: str | None = None
    kex_go_api_key: str | None = None
    kex_timeout_seconds: float = 10.0
    kex_max_retries: int = 2
    kex_retry_backoff_seconds: float = 0.5
    kma_tour_course_source_path: str | None = None
    arboretum_basic_csv_url: str | None = None
    arboretum_basic_csv_path: str | None = None
    web_base_url: str = "http://localhost:3001"
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    resend_timeout_seconds: float = 5.0
    email_verification_path: str = "/verify-email"
    rustfs_endpoint_url: str = "http://localhost:9000"
    rustfs_public_endpoint_url: str | None = None
    rustfs_public_base_url: str | None = None
    rustfs_region: str = "us-east-1"
    rustfs_bucket: str = "tripmate-media"
    rustfs_access_key_id: str | None = None
    rustfs_secret_access_key: str | None = None
    rustfs_presigned_url_expires_seconds: int = Field(default=900, ge=60, le=86_400)
    rustfs_max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    rustfs_allowed_content_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "video/mp4",
        "application/pdf",
    ]

    @property
    def enable_docs(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

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
    session_cookie_name: str = "tripmate_session"
    admin_session_hours: int = 12
    user_session_hours: int = 24 * 14
    cors_origins: list[str] = [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    airflow_download_dir: str = ".tmp/airflow-downloads"
    etl_config_path: str = "config/etl-datasets.json"
    kma_mid_term_region_config_path: str = "config/kma-mid-term-regions.json"
    data_go_service_key: str | None = None
    kma_short_term_request_delay_seconds: float = 1.0
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

    @property
    def enable_docs(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

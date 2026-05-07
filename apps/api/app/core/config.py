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
    opinet_api_key: str | None = None
    opinet_timeout_seconds: float = 10.0
    opinet_max_retries: int = 2
    opinet_retry_backoff_seconds: float = 0.5
    data_go_service_key: str | None = None
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

    @property
    def enable_docs(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

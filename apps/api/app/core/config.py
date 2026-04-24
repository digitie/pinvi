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

    @property
    def enable_docs(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

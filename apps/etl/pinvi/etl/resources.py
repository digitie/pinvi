"""Dagster resource 정의."""

from __future__ import annotations

from typing import Any

from dagster import ConfigurableResource
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class PinviDatabaseResource(ConfigurableResource[Any]):
    """Pinvi `app` schema에 접근하는 async DB resource."""

    dsn: str
    pool_size: int = 10

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(self.dsn, pool_size=self.pool_size, pool_pre_ping=True)


class KasiResource(ConfigurableResource[Any]):
    """`python-kasi-api` async client resource."""

    service_key: str
    timeout: float = 10.0
    retries: int = 3
    max_rps: float = 5.0

    def create_client(self) -> Any:
        from kasi import AsyncKasiClient

        return AsyncKasiClient(
            service_key=self.service_key,
            timeout=self.timeout,
            retries=self.retries,
            max_rps=self.max_rps,
        )

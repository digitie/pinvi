"""Dagster resource 정의."""

from __future__ import annotations

from dagster import ConfigurableResource
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class TripmateDatabaseResource(ConfigurableResource):
    """TripMate `app` schema에 접근하는 async DB resource."""

    dsn: str
    pool_size: int = 10

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(self.dsn, pool_size=self.pool_size, pool_pre_ping=True)


class KasiResource(ConfigurableResource):
    """`python-kasi-api` async client resource."""

    service_key: str
    timeout: float = 10.0
    retries: int = 3
    max_rps: float = 5.0

    def create_client(self):  # type: ignore[no-untyped-def]
        from kasi import AsyncKasiClient

        return AsyncKasiClient(
            service_key=self.service_key,
            timeout=self.timeout,
            retries=self.retries,
            max_rps=self.max_rps,
        )

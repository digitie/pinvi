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
    """`python-kasi-api` async client resource.

    라이브러리가 `AsyncKasiClient`/`KasiClient`(sync) 두 벌을 `KasiClient` 하나로
    통합(async-only)하면서 `AsyncKasiClient` export가 사라졌다(2026-09-14,
    "Unify KASI async-only clients" 커밋). 생성자 kwarg(`service_key`/`timeout`/
    `retries`/`max_rps`)는 그대로라 이름만 바꾸면 된다.
    """

    service_key: str
    timeout: float = 10.0
    retries: int = 3
    max_rps: float = 5.0

    def create_client(self) -> Any:
        from kasi import KasiClient

        return KasiClient(
            service_key=self.service_key,
            timeout=self.timeout,
            retries=self.retries,
            max_rps=self.max_rps,
        )

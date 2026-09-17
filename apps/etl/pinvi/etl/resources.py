"""Dagster resource 정의."""

from __future__ import annotations

from typing import Any

import httpx
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


class KorTravelWeatherResource(ConfigurableResource[Any]):
    """`kor-travel-weather` 공개 read 전용 최소 client resource.

    T-367 보존 지평 가드 전용이다. 인증이 없는 공개 read 표면만 호출하므로(§2.1,
    `docs/integrations/kor-travel-weather.md`) 별도 credential이 필요 없다. `apps/api`의
    풍부한 `KorTravelWeatherClient`(app.clients.kor_travel_weather)는 별도 Python
    패키지(apps/etl)에서 import할 수 없어, 여기서는 진단 목적에 필요한 최소한의 httpx
    client만 만든다 — decode는 asset 모듈이 담당한다(pinvi_kasi_special_days와 동일 원칙).
    """

    base_url: str
    timeout: float = 10.0

    def create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

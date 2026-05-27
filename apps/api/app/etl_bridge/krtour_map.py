"""`python-krtour-map` 라이브러리 lifespan + DI helper.

본 모듈의 역할:
1. `KrtourMapClient` **Protocol** 정의 — TripMate 측 type contract.
   라이브러리 측 `AsyncKrtourMapClient` (Sprint 2 라이브러리 작업 예정) 가
   본 Protocol에 부합. wrapper가 아닌 type interface 이므로 ADR-005 위반 X.
2. FastAPI lifespan에서 client 1회 생성 + close.
3. `get_krtour_map_client` 의존성 — 라이브러리 ready 전에는 503 응답.

참조:
- `docs/krtour-map-integration.md` §3, §4
- ADR-002 / ADR-003 / ADR-005
- SPRINT-4.md `apps/api/app/etl_bridge/krtour_map.py` 산출물
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Protocol, runtime_checkable

from fastapi import Depends, FastAPI, HTTPException, status

logger = logging.getLogger(__name__)

# 라이브러리 DTO를 TripMate가 직접 다루지 않도록 dict로 type alias.
# 실제 라이브러리 ready 시 `from krtour.map import Feature` 로 교체 가능.
type FeatureDTO = dict[str, Any]
type WeatherCardDTO = dict[str, Any]
type BBox = tuple[float, float, float, float]  # (lng_min, lat_min, lng_max, lat_max)


@runtime_checkable
class KrtourMapClient(Protocol):
    """라이브러리 client 인터페이스 (TripMate가 호출하는 메서드).

    `python-krtour-map` Sprint 2 가 본 시그니처에 맞춰 `AsyncKrtourMapClient`
    구현. 시그니처 변경 시 라이브러리 ADR + 본 Protocol 동기 갱신.
    """

    async def features_in_bounds(
        self,
        bbox: BBox,
        *,
        kinds: list[str],
        zoom: int,
        limit: int = 500,
    ) -> list[FeatureDTO]:
        """viewport 내 feature 목록. zoom별 라이브러리 측 클러스터링."""

    async def features_nearby(
        self,
        *,
        lng: float,
        lat: float,
        radius_m: int,
        kinds: list[str],
        limit: int = 100,
    ) -> list[FeatureDTO]:
        """반경 검색 — `coord_5179` 기반 (라이브러리 책임)."""

    async def get_feature(self, feature_id: uuid.UUID) -> FeatureDTO | None:
        """feature 1건 상세."""

    async def features_by_ids(self, feature_ids: list[uuid.UUID]) -> list[FeatureDTO]:
        """ID batch 조회 — trip POI snapshot 갱신용."""

    async def build_weather_card(
        self,
        feature_id: uuid.UUID,
        *,
        asof: datetime,
    ) -> WeatherCardDTO:
        """KMA 시간축 + sources 배열."""

    async def search(
        self,
        *,
        q: str,
        kinds: list[str] | None = None,
        bbox: BBox | None = None,
        limit: int = 50,
    ) -> list[FeatureDTO]:
        """자유 텍스트 검색 (라이브러리 측 FTS5 또는 pg_trgm)."""

    async def request_feature(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        title: str,
        coord: tuple[float, float],
        note: str | None,
    ) -> uuid.UUID:
        """사용자 feature 요청 큐 적재 (Sprint 6 ADMIN approve 후 라이브러리에 반영)."""

    async def close(self) -> None:
        """리소스 정리 — engine.dispose 등."""


# Lifespan에 의해 set/close 되는 module-level slot.
# `None` = 라이브러리 미주입 (Sprint 2 라이브러리 ready 전).
_client_singleton: KrtourMapClient | None = None


def _set_client(client: KrtourMapClient | None) -> None:
    """lifespan / 테스트 fixture에서만 호출."""
    global _client_singleton
    _client_singleton = client


@asynccontextmanager
async def krtour_map_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — `python-krtour-map` client lifecycle 관리.

    라이브러리 측 `AsyncKrtourMapClient` 가 ready 전이므로 본 lifespan은
    import를 lazy로 시도하고 실패 시 `None` 으로 두고 통과. 라이브러리 ready
    후에는 본 함수가 실제 client 생성을 수행.

    Usage:
        app = FastAPI(lifespan=krtour_map_lifespan)
    """
    client: KrtourMapClient | None = None
    try:
        # NOTE: 라이브러리 Sprint 2가 채울 진입점. ready 전에는 ImportError.
        from krtour.map.client import AsyncKrtourMapClient  # type: ignore[attr-defined]
    except ImportError:
        logger.warning(
            "python-krtour-map client not available — features API will return 503. "
            "라이브러리 Sprint 2 머지 후 ready 예정."
        )
    else:
        # 실 client 생성 (라이브러리 ready 시) — engine / providers / file_store 주입.
        # `docs/krtour-map-integration.md` §3 패턴.
        from app.db.session import async_session_factory  # noqa: F401 — 라이브러리 ready 시 사용

        # TODO(sprint-4-PR-B2): 라이브러리 ready 후 실제 인스턴스 생성:
        #   client = AsyncKrtourMapClient(
        #       engine=engine,
        #       providers=await get_provider_clients(),
        #       file_store=await get_file_store(),
        #   )
        #   await client.__aenter__()
        _ = AsyncKrtourMapClient  # 미사용 경고 회피
        logger.info("python-krtour-map client placeholder — 실제 인스턴스 미생성")

    _set_client(client)
    try:
        yield
    finally:
        if _client_singleton is not None:
            await _client_singleton.close()
        _set_client(None)


async def get_krtour_map_client_dep() -> KrtourMapClient:
    """FastAPI 의존성 — client 가져오기. 미주입 시 503."""
    if _client_singleton is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "LIBRARY_NOT_READY",
                "message": "지도 라이브러리가 아직 활성화되지 않았습니다. "
                "관리자에게 문의 또는 잠시 후 다시 시도하세요.",
            },
        )
    return _client_singleton


KrtourMapClientDep = Annotated[KrtourMapClient, Depends(get_krtour_map_client_dep)]

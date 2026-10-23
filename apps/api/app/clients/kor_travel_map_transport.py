"""kor-travel-map transport 상태 표면 client — `/v1/service/transport/*` (Map ADR-114, PinVi ADR-076).

`KorTravelMapClient`와 **같은 httpx client·service token·API 호출 로깅·엄격한 JSON 해석**을 쓴다(감싼 인스턴스의
`_send`·`_decode_envelope` — 같은 패키지의 협력). 새 연결을 만들지 않는다. 다른 점은 오류 의미다(ADR-076 D2):

- 재시도 0회. 503 ``TRANSPORT_STATE_NOT_LOADED``는 결정적이고, 지도 요청은 다음 이동이 곧 재시도다.
- 5xx는 problem ``code``를 실은 ``KorTravelMapTransportUnavailable``, 401/403은 ``code="UPSTREAM_AUTH"``.
- 404는 ``KorTravelMapFeatureNotFound``, 409는 rate limit이 아니라 cursor 세대 만료
  (``KorTravelMapTransportCursorExpired``), 그 밖 4xx는 ``KorTravelMapBadRequest``.
- service 표면이라 public API key로 fallback하지 않는다.

응답은 envelope의 ``data`` dict다(transport-only). PinVi schema 투영은 `services/transport_layers.py`.

**경로는 이 모듈의 문자열 리터럴로만 둔다** — 계약 게이트(`test_kor_travel_map_transport_contract.py`)가
이 소스의 ``"/v1/..."`` 리터럴을 읽어 vendored OpenAPI와 양방향 대조한다(런타임에 조립하면 게이트가 못 본다).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final, Literal

import httpx
from fastapi import status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapUnavailable,
    _error_code,
)

logger = logging.getLogger(__name__)

TransportDatasetPath = Literal["fuel-stations", "rest-areas", "highway-incidents", "airports"]

_LIST_PATHS: Final[dict[TransportDatasetPath, str]] = {
    "fuel-stations": "/v1/service/transport/fuel-stations",
    "rest-areas": "/v1/service/transport/rest-areas",
    "highway-incidents": "/v1/service/transport/highway-incidents",
    "airports": "/v1/service/transport/airports",
}
_DETAIL_PATHS: Final[dict[TransportDatasetPath, str]] = {
    "fuel-stations": "/v1/service/transport/fuel-stations/{feature_id}",
    "rest-areas": "/v1/service/transport/rest-areas/{feature_id}",
    "highway-incidents": "/v1/service/transport/highway-incidents/{feature_id}",
    "airports": "/v1/service/transport/airports/{feature_id}",
}
_PRICE_HISTORY_PATH: Final = "/v1/service/transport/fuel-stations/{feature_id}/price-history"
_STATUS_PATH: Final = "/v1/service/transport/status"


class KorTravelMapTransportUnavailable(KorTravelMapError):
    """transport 상태 표면을 지금 읽을 수 없음.

    ``code``는 Map problem ``code``(``TRANSPORT_STATE_NOT_LOADED``·``TRANSPORT_STATE_UNAVAILABLE`` 등),
    401/403이면 ``UPSTREAM_AUTH``, timeout·연결 실패면 ``None``이다.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapTransportCursorExpired(KorTravelMapError):
    """409 ``TRANSPORT_STATE_GENERATION_EXPIRED`` — cursor의 세대가 사라졌다. 처음부터 다시."""


class KorTravelMapTransportClient:
    """Map `/v1/service/transport/*` 읽기. 감싼 `KorTravelMapClient`의 연결을 공유한다."""

    def __init__(self, map_client: KorTravelMapClient) -> None:
        self._map = map_client

    def _data(self, resp: httpx.Response) -> tuple[dict[str, Any], dict[str, Any]]:
        sc = resp.status_code
        path = resp.request.url.path
        if sc >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise KorTravelMapTransportUnavailable(
                f"kor-travel-map transport {sc} ({path})", code=_error_code(resp)
            )
        if sc in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            # 운영 Map은 service token을 강제한다 — 토큰 미주입(Manager compose)이 가장 흔한 원인.
            logger.warning("kor_travel_map.transport_auth_rejected", extra={"status": sc})
            raise KorTravelMapTransportUnavailable(
                f"kor-travel-map transport {sc} ({path})", code="UPSTREAM_AUTH"
            )
        if sc == status.HTTP_404_NOT_FOUND:
            raise KorTravelMapFeatureNotFound(
                "transport 항목을 찾을 수 없습니다.", code=_error_code(resp)
            )
        if sc == status.HTTP_409_CONFLICT:
            raise KorTravelMapTransportCursorExpired(f"kor-travel-map transport 409 ({path})")
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelMapBadRequest(f"kor-travel-map transport {sc}", code=_error_code(resp))
        return self._map._decode_envelope(resp)

    async def _get(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            resp = await self._map._send("GET", path, params=params, retry=False)
        except KorTravelMapUnavailable as exc:
            raise KorTravelMapTransportUnavailable(str(exc)) from exc
        return self._data(resp)

    async def list_items(
        self,
        dataset: TransportDatasetPath,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        near: tuple[float, float, float] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """목록. data = ``{items, truncated, freshness, ...}`` + threaded ``next_cursor``.

        ``bbox = (min_lon, min_lat, max_lon, max_lat)``, ``near = (lon, lat, radius_m)``. Map은 둘을 함께
        받지 않고 cursor는 조건 없는 순회에만 받는다(422) — 그 조합을 여기서 먼저 막는다.
        """
        if bbox is not None and near is not None:
            raise ValueError("bbox와 near는 함께 쓸 수 없습니다.")
        if cursor is not None and (bbox is not None or near is not None):
            raise ValueError("cursor는 조건 없는 목록 순회에만 씁니다.")
        params: dict[str, Any] = {}
        if bbox is not None:
            params.update(
                {"min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3]}
            )
        if near is not None:
            params.update({"lon": near[0], "lat": near[1], "radius_m": near[2]})
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        data, meta = await self._get(_LIST_PATHS[dataset], params)
        return self._map._thread_page(data, meta)

    async def detail(self, dataset: TransportDatasetPath, feature_id: str) -> dict[str, Any]:
        """단건. data = ``{item, freshness, ...}``. 404 → ``KorTravelMapFeatureNotFound``."""
        data, _meta = await self._get(_DETAIL_PATHS[dataset].format(feature_id=feature_id))
        return data

    async def fuel_price_history(
        self,
        feature_id: str,
        *,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """주유소 가격 추이. ``history.status``가 ``unavailable``이어도 200이다."""
        params: dict[str, Any] = {}
        if since is not None:
            if since.tzinfo is None:
                raise ValueError("since는 aware datetime이어야 합니다.")
            params["since"] = since.isoformat()
        if limit is not None:
            params["limit"] = limit
        data, _meta = await self._get(_PRICE_HISTORY_PATH.format(feature_id=feature_id), params)
        return data

    async def status(self) -> dict[str, Any]:
        """Valkey 연결과 데이터셋별 적재·신선도. data = ``{store, datasets}``."""
        data, _meta = await self._get(_STATUS_PATH)
        return data

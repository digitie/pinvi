"""통합 검색 응답 schema — `PlaceSearchResult`(source-tagged) — `docs/api/search.md`.

ADR-054: `GET /search`는 feature/my_poi/address/kakao/naver를 **단일 source-tagged 리스트**로
합쳐 반환한다. Kakao/Naver row의 `phone`/`category` 등 provider 파생 콘텐츠는 표시 전용이며
POI/feature-request로 넘어가 저장하는 것은 user-authored name+coord+note + `external_ref`뿐이다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PlaceSearchSource = Literal["feature", "my_poi", "address", "kakao", "naver"]


class PlaceCoord(BaseModel):
    lon: float
    lat: float


class PlaceSearchResult(BaseModel):
    """자동완성/통합 검색의 한 행. source에 따라 채워지는 필드가 다르다."""

    source: PlaceSearchSource
    name: str
    # 좌표 미상(주소만 있는 후보 등)은 리스트 표시는 하되 지도 핀은 못 찍는다.
    coord: PlaceCoord | None = None
    # 정본 feature 참조(source=feature 또는 feature-linked my_poi).
    feature_id: str | None = None
    # 내 POI 참조(source=my_poi).
    poi_id: str | None = None
    trip_id: str | None = None
    trip_title: str | None = None
    # 외부 provider opaque id(source=kakao/naver). 저장 대상은 external_ref만(ADR-054 §7).
    external_id: str | None = None
    address: str | None = None
    road_address: str | None = None
    category: str | None = None
    marker_color: str | None = None
    marker_icon: str | None = None
    # 카카오맵/네이버 지도 back-link(표시 전용, attribution 필수).
    provider_url: str | None = None
    # provider 전화 — 표시 전용, 절대 저장하지 않는다(ADR-054 §7).
    phone: str | None = None


class PlaceSearchResponse(BaseModel):
    """통합 검색 응답 — internal(feature+my_poi+address) 우선 → kakao → naver 순 정렬."""

    results: list[PlaceSearchResult] = Field(default_factory=list)
    # 5xx/타임아웃/키 미설정/쿼터로 비운 소스명(예: features, addresses, kakao, naver).
    degraded_sources: list[str] = Field(default_factory=list)

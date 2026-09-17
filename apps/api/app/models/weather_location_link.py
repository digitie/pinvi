"""날씨 소스 이관(ADR-068) `feature_id` ↔ `kor-travel-weather` `location_id` 해석 캐시.

T-361(P2). `kor-travel-weather` `/v1/weather/resolve`는 좌표 해석 1회당 3.1 MB급
응답이라 조회 경로에 둘 수 없다 — 결과를 이 테이블에 캐시한다.

`source_location_ids`를 **통째로 저장**하는 이유: `/resolve`의 대표 `location` 하나만
캐시하면 기상청 예보가 조용히 누락된다(설계 문서 §3.3 — 서울시청 실측에서 대표
location은 AirKorea 측정소였고 KMA 예보는 다른 source location에 있었다). 조회 시
`source_location_ids` 전체를 합쳐 사용한다.

이 모델은 T-361 시점에 아직 어떤 라우터에서도 쓰이지 않는다 — 해석기(서비스 계층)와
Alembic migration만 갖춘다. T-362/T-363이 처음 읽는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, DateTime, Float, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WeatherLocationLink(Base, TimestampMixin):
    """`feature_id`(kor-travel-map, opaque string) → `kor-travel-weather` location 해석 결과."""

    __tablename__ = "weather_location_links"

    feature_id: Mapped[str] = mapped_column(Text(), primary_key=True)
    location_id: Mapped[str] = mapped_column(Text(), nullable=False)
    source_location_ids: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    lat: Mapped[float] = mapped_column(Float(), nullable=False)
    lon: Mapped[float] = mapped_column(Float(), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float(), nullable=False)
    measurement_point: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(astext_type=Text()), nullable=True
    )
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))

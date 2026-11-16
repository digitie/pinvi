"""여행 장소(POI)에 붙는 영업 정보(영업시간·휴무일·전화·웹사이트) 사본.

전역 장소 데이터로 영구 보관하지 않는다 — 여행에 넣은 장소 하나에만 붙는다. 장소를 처음 열 때 한 번
받아 저장하고, 장소를 지우면 함께 지운다(soft delete는 서비스가, 영구 삭제는 FK CASCADE가). 같은 곳을
다시 넣으면 새 POI라 다시 받는다. 사용자가 "다시 읽어오기"로 언제든 덮어쓸 수 있다.

출처는 공식 API만 쓴다. 현재 저장 출처는 kor-travel-map feature(공공데이터) 하나다 — Kakao/Naver
Local은 응답 저장이 금지(ADR-054)이고, Google Places는 콘텐츠 캐시 금지·비 Google 지도 표시 금지 약관
때문에 쓰지 않는다(`docs/api/pois.md` 장소 영업 정보 절).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TripPoiPlaceDetail(Base, TimestampMixin):
    __tablename__ = "trip_poi_place_details"
    __table_args__ = (CheckConstraint("status IN ('ready', 'empty')", name="status"),)

    poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trip_day_pois.attachment_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # ready = 하나 이상 받음, empty = 출처를 조회했지만 줄 값이 없음(다시 묻지 않는다).
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # 요일별 영업시간 표시 줄(예: "월요일: 09:00~18:00").
    opening_hours: Mapped[list[str]] = mapped_column(
        JSONB(astext_type=Text()), nullable=False, server_default=text("'[]'::jsonb")
    )
    closed_days: Mapped[str | None] = mapped_column(Text())
    phone: Mapped[str | None] = mapped_column(Text())
    website: Mapped[str | None] = mapped_column(Text())
    # 필드 → 출처(provider) 이름. 예: {"phone": "kor_travel_map"}.
    sources: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

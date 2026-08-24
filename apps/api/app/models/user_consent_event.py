"""`app.user_consent_events` — 동의/철회 이벤트 이력 (T-326).

`app.user_consents`는 type당 1행의 **현재 상태**만 담는다. 그 row는 재동의 시 in-place로
되살아나므로(`withdrawn_at → None`, `agreed_at` 덮어쓰기) "언제 동의했고 언제 철회했는가"가
남지 않는다. `docs/legal/terms-of-service.md` 제4조는 이용자에게 "동의 이력은 시점·버전과 함께
기록된다"고 고지하므로, 그 진술을 참으로 만드는 append 전용 이벤트 테이블을 둔다.

현재 상태 테이블을 다행(多行)으로 바꾸지 않은 이유는 소비자 계약이다 — 웹·모바일 설정 화면이
`consents.find(...)`로 type당 첫 행을 고르고, 마케팅 발송 게이트는 `withdrawn_at IS NULL` 행의
**존재**만 본다. 다행으로 바꾸면 유효한 동의가 "철회됨"으로 표시되거나 철회자에게 메일이 나간다.

hash chain(`admin_audit_log` 패턴)은 쓰지 않는다. append-only 트리거를 걸면 PIPA 계정 파기 시
삭제가 막히고, 테스트 하네스의 TRUNCATE 격리도 우회하지 못한다. 이 테이블의 목적은 법정 무결성
증명이 아니라 이벤트 유실 방지다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CONSENT_EVENTS = ("agreed", "withdrawn")
CONSENT_EVENT_SOURCES = ("register", "profile_complete", "settings", "backfill")


class UserConsentEvent(Base):
    __tablename__ = "user_consent_events"
    __table_args__ = (
        Index(
            "ix_user_consent_events_user_type_time",
            "user_id",
            "consent_type",
            "occurred_at",
        ),
        {"schema": "app"},
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 동의 당시의 약관 버전. 허용 목록 CHECK는 두지 않는다 — 과거 데이터의 버전 표기가
    # 드리프트해 있고, 이력은 "그때 무엇에 동의했는가"를 있는 그대로 남겨야 한다.
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

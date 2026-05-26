"""`app.api_call_log` — 외부 provider 호출 추적."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiCallLog(Base):
    __tablename__ = "api_call_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text(), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text())
    request_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

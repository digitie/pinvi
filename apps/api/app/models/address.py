from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, utc_now


class AddressRawJusoRoadAddress(Base):
    __tablename__ = "address_raw_juso_road_address"
    __table_args__ = (
        UniqueConstraint(
            "source_file_hash",
            "row_number",
            name="uq_address_raw_juso_road_address_source_file_hash_row_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year_month: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    delimiter: Mapped[str] = mapped_column(String(8), nullable=False)
    road_address_management_no: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_dong_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    road_name_code: Mapped[str] = mapped_column(String(12), nullable=False)
    administrative_dong_code: Mapped[str | None] = mapped_column(String(10))
    effective_date: Mapped[str] = mapped_column(String(8), nullable=False)
    change_reason_code: Mapped[str] = mapped_column(String(2), nullable=False)
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)


class AddressCodeStandard(TimestampMixin, Base):
    __tablename__ = "address_code_standard"

    legal_dong_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    sigungu_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_eupmyeondong_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    full_legal_dong_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_effective_date: Mapped[str] = mapped_column(String(8), nullable=False)
    source_change_reason_code: Mapped[str] = mapped_column(String(2), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year_month: Mapped[str] = mapped_column(String(6), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

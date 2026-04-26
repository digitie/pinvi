from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


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
    ingested_at: Mapped[datetime] = mapped_column(nullable=False, default=kst_now)


class AddressServingJusoRoadAddress(TimestampMixin, Base):
    __tablename__ = "address_serving_juso_road_address"

    road_address_management_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    legal_dong_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("address_code_standard.legal_dong_code", name="fk_asjra_legal_code"),
        index=True,
        nullable=False,
    )
    road_name_code: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    administrative_dong_code: Mapped[str | None] = mapped_column(String(10), index=True)
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    sigungu_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_eupmyeondong_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    road_name: Mapped[str] = mapped_column(String(120), nullable=False)
    administrative_dong_name: Mapped[str | None] = mapped_column(String(80))
    mountain_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    jibun_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    jibun_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    underground_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    building_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    building_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(5))
    previous_road_address: Mapped[str | None] = mapped_column(String(255))
    apartment_yn: Mapped[str | None] = mapped_column(String(1))
    building_registry_name: Mapped[str | None] = mapped_column(String(255))
    sigungu_building_name: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    full_legal_dong_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_road_address: Mapped[str] = mapped_column(String(255), nullable=False)
    source_effective_date: Mapped[str] = mapped_column(String(8), nullable=False)
    source_change_reason_code: Mapped[str] = mapped_column(String(2), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year_month: Mapped[str] = mapped_column(String(6), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AddressRawJusoRelatedJibun(Base):
    __tablename__ = "address_raw_juso_related_jibun"
    __table_args__ = (
        UniqueConstraint(
            "source_file_hash",
            "row_number",
            name="uq_address_raw_juso_related_jibun_source_file_hash_row_number",
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
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    sigungu_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_eupmyeondong_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    mountain_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    jibun_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    jibun_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    road_name_code: Mapped[str] = mapped_column(String(12), nullable=False)
    underground_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    building_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    building_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(nullable=False, default=kst_now)


class AddressServingJusoRelatedJibun(TimestampMixin, Base):
    __tablename__ = "address_serving_juso_related_jibun"
    __table_args__ = (
        Index("ix_asjrj_ramno", "road_address_management_no"),
        UniqueConstraint(
            "road_address_management_no",
            "legal_dong_code",
            "mountain_yn",
            "jibun_main_no",
            "jibun_sub_no",
            name="uq_address_serving_juso_related_jibun_relation",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    road_address_management_no: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "address_serving_juso_road_address.road_address_management_no",
            name="fk_addr_serv_rel_jibun_ramno",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    legal_dong_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("address_code_standard.legal_dong_code", name="fk_asjrj_legal_code"),
        index=True,
        nullable=False,
    )
    road_name_code: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    sigungu_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_eupmyeondong_name: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    mountain_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    jibun_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    jibun_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    underground_yn: Mapped[str] = mapped_column(String(1), nullable=False)
    building_main_no: Mapped[str] = mapped_column(String(16), nullable=False)
    building_sub_no: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    full_legal_dong_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_jibun_address: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year_month: Mapped[str] = mapped_column(String(6), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AddressCodeStandard(TimestampMixin, Base):
    __tablename__ = "address_code_standard"

    legal_dong_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    code_level: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sido_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    sigungu_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    sido_name: Mapped[str | None] = mapped_column(String(40))
    sigungu_name: Mapped[str | None] = mapped_column(String(80))
    legal_eupmyeondong_name: Mapped[str | None] = mapped_column(String(80))
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    full_legal_dong_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_effective_date: Mapped[str] = mapped_column(String(8), nullable=False)
    source_change_reason_code: Mapped[str] = mapped_column(String(2), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year_month: Mapped[str] = mapped_column(String(6), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sort_order: Mapped[int | None] = mapped_column(Integer)
    source_created_date: Mapped[str | None] = mapped_column(String(10))
    source_deleted_date: Mapped[str | None] = mapped_column(String(10))
    previous_legal_dong_code: Mapped[str | None] = mapped_column(String(10), index=True)
    is_discontinued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AddressRawLegalDongCode(Base):
    __tablename__ = "address_raw_legal_dong_code"
    __table_args__ = (UniqueConstraint("source_file_hash", "row_number", name="uq_arlc_file_row"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_dong_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    legal_dong_name: Mapped[str] = mapped_column(String(255), nullable=False)
    discontinued_status: Mapped[str] = mapped_column(String(40), nullable=False)
    sido_name: Mapped[str | None] = mapped_column(String(40))
    sigungu_name: Mapped[str | None] = mapped_column(String(80))
    legal_eupmyeondong_name: Mapped[str | None] = mapped_column(String(80))
    legal_ri_name: Mapped[str | None] = mapped_column(String(80))
    source_sort_order: Mapped[int | None] = mapped_column(Integer)
    source_created_date: Mapped[str | None] = mapped_column(String(10))
    source_deleted_date: Mapped[str | None] = mapped_column(String(10))
    previous_legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(nullable=False, default=kst_now)


class RegionBoundaryImportBatch(TimestampMixin, Base):
    __tablename__ = "region_boundary_import_batch"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    layer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    boundary_level: Mapped[str] = mapped_column(String(32), nullable=False)
    source_encoding: Mapped[str] = mapped_column(String(16), nullable=False)
    source_srid: Mapped[int] = mapped_column(Integer, nullable=False)
    serving_srid: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class RegionRawVWorldBoundary(Base):
    __tablename__ = "region_raw_vworld_boundary"
    __table_args__ = (
        Index("ix_rrvb_batch_id", "import_batch_id"),
        Index("ix_rrvb_bjcd", "bjcd"),
        Index("ix_rrvb_geom", "geom", postgresql_using="gist"),
        UniqueConstraint("import_batch_id", "ufid", name="uq_rrvb_batch_ufid"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_batch_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("region_boundary_import_batch.id", name="fk_rrvb_batch", ondelete="CASCADE"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    boundary_level: Mapped[str] = mapped_column(String(32), nullable=False)
    ufid: Mapped[str] = mapped_column(String(34), nullable=False)
    bjcd: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    divi: Mapped[str] = mapped_column(String(20), nullable=False)
    scls: Mapped[str] = mapped_column(String(8), nullable=False)
    fmta: Mapped[str] = mapped_column(String(9), nullable=False)
    raw_attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=5179, spatial_index=False),
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(nullable=False, default=kst_now)


class RegionServingBoundary(TimestampMixin, Base):
    __tablename__ = "region_serving_boundary"
    __table_args__ = (
        Index("ix_rsb_level_code", "boundary_level", "region_code"),
        Index("ix_rsb_sido_code", "sido_code"),
        Index("ix_rsb_sigungu_code", "sigungu_code"),
        Index("ix_rsb_legal_dong_code", "legal_dong_code"),
        Index("ix_rsb_geom", "geom", postgresql_using="gist"),
        UniqueConstraint("boundary_level", "region_code", name="uq_rsb_level_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    raw_boundary_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("region_raw_vworld_boundary.id", name="fk_rsb_raw_boundary", ondelete="CASCADE"),
        nullable=False,
    )
    import_batch_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("region_boundary_import_batch.id", name="fk_rsb_batch", ondelete="CASCADE"),
        nullable=False,
    )
    layer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    boundary_level: Mapped[str] = mapped_column(String(32), nullable=False)
    region_code: Mapped[str] = mapped_column(String(10), nullable=False)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sido_code: Mapped[str] = mapped_column(String(10), nullable=False)
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    parent_region_code: Mapped[str | None] = mapped_column(String(10))
    full_region_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_code_standard_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_rsb_address_code_standard",
            ondelete="SET NULL",
        ),
    )
    address_code_matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )

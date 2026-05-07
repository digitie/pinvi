from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli.opinet_fuel import _resolve_region_codes
from app.etl.opinet.client import OPINET_FUEL_SPECS, OpiNetApiClient, OpiNetApiError
from app.etl.opinet.loader import (
    find_opinet_region_code_for_legal_dong,
    list_opinet_sigungu_region_codes_for_periodic_collection,
    load_opinet_avg_prices,
    load_opinet_lowest_stations,
    load_opinet_region_codes,
)
from app.models.address import AddressCodeStandard
from app.models.fuel import (
    FuelRawAvgPrice,
    FuelRawLowestStation,
    FuelRawOpiNetRegionCode,
    FuelRegionLegalDongMapping,
    FuelServingAvgPrice,
    FuelServingLowestStation,
    FuelServingOpiNetRegionCode,
)
from app.services.fuel_report import get_latest_daily_fuel_averages, get_nearby_fuel_summary

KST = ZoneInfo("Asia/Seoul")


class FakeOpiNetClient:
    def fetch_region_codes(self, *, area_code: str | None = None) -> list[dict[str, str]]:
        if area_code is None:
            return [{"AREA_CD": "01", "AREA_NM": "서울"}]
        if area_code == "01":
            return [{"AREA_CD": "0101", "AREA_NM": "종로구"}]
        return []

    def fetch_avg_all_prices(self) -> list[dict[str, str]]:
        return [
            {"PRODCD": "B027", "PRICE": "1674.12", "DIFF": "-1.50", "TRADE_DT": "20260426"},
            {"PRODCD": "B034", "PRICE": "1890", "DIFF": "0", "TRADE_DT": "20260426"},
            {"PRODCD": "C004", "PRICE": "1200", "DIFF": "0", "TRADE_DT": "20260426"},
        ]

    def fetch_lowest_stations(
        self,
        *,
        provider_region_code: str,
        provider_fuel_code: str,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        assert provider_region_code == "0101"
        assert provider_fuel_code == "B027"
        assert limit == 20
        return [
            {
                "UNI_ID": "A0001",
                "OS_NM": "종로셀프",
                "PRICE": "1600",
                "POLL_DIV_CD": "SKE",
                "VAN_ADR": "서울 종로구 청운동 1",
                "NEW_ADR": "서울 종로구 청운로 1",
                "GIS_X_COOR": "198000.123456",
                "GIS_Y_COOR": "452000.654321",
            },
            {
                "UNI_ID": "A0002",
                "OS_NM": "종로주유소",
                "PRICE": "1610",
                "POLL_DIV_CD": "GSC",
                "VAN_ADR": "서울 종로구 청운동 2",
                "NEW_ADR": "서울 종로구 청운로 2",
                "GIS_X_COOR": "198100.123456",
                "GIS_Y_COOR": "452100.654321",
            },
        ]


class EmptyOpiNetClient(FakeOpiNetClient):
    def fetch_region_codes(self, *, area_code: str | None = None) -> list[dict[str, str]]:
        return []

    def fetch_avg_all_prices(self) -> list[dict[str, str]]:
        return []


def test_opinet_region_loader_maps_provider_codes_to_address_standard(
    db_session: Session,
) -> None:
    _add_address_codes(db_session)

    result = load_opinet_region_codes(
        db_session,
        FakeOpiNetClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(
        select(FuelServingOpiNetRegionCode).order_by(
            FuelServingOpiNetRegionCode.provider_region_code
        )
    ).all()
    mappings = db_session.scalars(
        select(FuelRegionLegalDongMapping).order_by(FuelRegionLegalDongMapping.provider_region_code)
    ).all()

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.mapped_row_count == 2
    assert db_session.scalar(select(FuelRawOpiNetRegionCode)) is not None
    assert [(row.provider_region_code, row.address_code_standard_code) for row in serving_rows] == [
        ("01", "1100000000"),
        ("0101", "1111000000"),
    ]
    assert [(row.provider_region_code, row.legal_dong_code) for row in mappings] == [
        ("01", "1100000000"),
        ("0101", "1111000000"),
    ]


def test_opinet_region_loader_rejects_zero_row_provider_response(
    db_session: Session,
) -> None:
    with pytest.raises(OpiNetApiError, match="zero sido rows"):
        load_opinet_region_codes(
            db_session,
            EmptyOpiNetClient(),  # type: ignore[arg-type]
            collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
        )


def test_opinet_avg_loader_stores_supported_fuels_and_daily_summary(
    db_session: Session,
) -> None:
    result = load_opinet_avg_prices(
        db_session,
        FakeOpiNetClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 30, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(FuelRawAvgPrice)).all()
    serving_rows = db_session.scalars(
        select(FuelServingAvgPrice).order_by(FuelServingAvgPrice.fuel_type)
    ).all()
    summary = get_latest_daily_fuel_averages(db_session)

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.skipped_row_count == 1
    assert len(raw_rows) == 2
    assert [(row.fuel_type, row.price, row.price_unit) for row in serving_rows] == [
        ("gasoline", Decimal("1674.12"), "KRW_PER_LITER"),
        ("premium_gasoline", Decimal("1890.00"), "KRW_PER_LITER"),
    ]
    assert serving_rows[0].timestamp == datetime(2026, 4, 26, 0, 0, tzinfo=KST)
    assert [(row.fuel_type, row.price) for row in summary] == [
        ("gasoline", Decimal("1674.12")),
        ("premium_gasoline", Decimal("1890.00")),
    ]


def test_opinet_avg_loader_rejects_zero_row_provider_response(
    db_session: Session,
) -> None:
    with pytest.raises(OpiNetApiError, match="zero rows"):
        load_opinet_avg_prices(
            db_session,
            EmptyOpiNetClient(),  # type: ignore[arg-type]
            collected_at=datetime(2026, 4, 26, 6, 30, tzinfo=KST),
        )


def test_opinet_lowest_station_loader_uses_address_mapping_for_nearby_summary(
    db_session: Session,
) -> None:
    _add_address_codes(db_session)
    load_opinet_region_codes(db_session, FakeOpiNetClient())  # type: ignore[arg-type]
    load_opinet_avg_prices(db_session, FakeOpiNetClient())  # type: ignore[arg-type]

    result = load_opinet_lowest_stations(
        db_session,
        FakeOpiNetClient(),  # type: ignore[arg-type]
        provider_region_codes=["0101"],
        provider_fuel_codes=["B027"],
        collected_at=datetime(2026, 4, 26, 7, 0, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(FuelRawLowestStation)).all()
    serving_rows = db_session.scalars(
        select(FuelServingLowestStation).order_by(FuelServingLowestStation.price)
    ).all()
    summary = get_nearby_fuel_summary(
        db_session,
        legal_dong_code="1111010100",
        fuel_type="gasoline",
    )

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert len(raw_rows) == 2
    assert [row.legal_dong_code for row in serving_rows] == ["1111000000", "1111000000"]
    assert find_opinet_region_code_for_legal_dong(db_session, "1111010100") == "0101"
    assert summary.provider_region_code == "0101"
    assert summary.station_count == 2
    assert summary.lowest_price == Decimal("1600.00")
    assert summary.nearby_average_price == Decimal("1605.00")
    assert summary.lowest_candidate_average_price == Decimal("1605.00")
    assert summary.candidate_average_price == Decimal("1605.00")
    assert summary.national_average_price == Decimal("1674.12")


def test_periodic_lowest_station_collection_uses_only_matched_active_sigungu(
    db_session: Session,
) -> None:
    _add_address_codes(db_session)
    load_opinet_region_codes(db_session, FakeOpiNetClient())  # type: ignore[arg-type]
    db_session.add_all(
        [
            FuelServingOpiNetRegionCode(
                provider_region_code="0199",
                provider_region_name="미매핑구",
                region_level="sigungu",
                parent_provider_region_code="01",
                address_code_standard_code=None,
                mapping_status="unmatched",
                mapping_source="fixture",
                raw_payload={},
                collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
                is_active=True,
            ),
            FuelServingOpiNetRegionCode(
                provider_region_code="0198",
                provider_region_name="비활성구",
                region_level="sigungu",
                parent_provider_region_code="01",
                address_code_standard_code="1111000000",
                mapping_status="matched",
                mapping_source="fixture",
                raw_payload={},
                collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
                is_active=False,
            ),
        ]
    )
    db_session.flush()

    region_codes = list_opinet_sigungu_region_codes_for_periodic_collection(db_session)

    assert region_codes == ["0101"]


def test_opinet_cli_resolves_legal_dong_to_provider_region(db_session: Session) -> None:
    _add_address_codes(db_session)
    load_opinet_region_codes(db_session, FakeOpiNetClient())  # type: ignore[arg-type]
    db_session.commit()

    region_codes = _resolve_region_codes(
        lambda: db_session,
        provider_region_codes=["0101"],
        legal_dong_codes=["1111010100"],
    )

    assert region_codes == ["0101"]


def test_opinet_client_requires_api_key() -> None:
    client = OpiNetApiClient(api_key="")

    with pytest.raises(OpiNetApiError, match="API key"):
        client.fetch_avg_all_prices()


def test_opinet_fuel_specs_keep_provider_codes_and_internal_enum() -> None:
    assert OPINET_FUEL_SPECS["B027"].fuel_type == "gasoline"
    assert OPINET_FUEL_SPECS["B034"].fuel_type == "premium_gasoline"
    assert OPINET_FUEL_SPECS["D047"].fuel_type == "diesel"
    assert OPINET_FUEL_SPECS["K015"].fuel_type == "lpg"


def _add_address_codes(db_session: Session) -> None:
    db_session.add_all(
        [
            AddressCodeStandard(
                legal_dong_code="1100000000",
                code_level="sido",
                code_name="서울특별시",
                sido_code="1100000000",
                sigungu_code="1100000000",
                sido_name="서울특별시",
                sigungu_name=None,
                legal_eupmyeondong_name=None,
                legal_ri_name=None,
                full_legal_dong_name="서울특별시",
                source_effective_date="20240101",
                source_change_reason_code="00",
                source_provider="fixture",
                source_status="active",
                source_file_name="fixture.csv",
                source_year_month="202401",
                source_file_hash="fixture",
                is_discontinued=False,
                is_active=True,
            ),
            AddressCodeStandard(
                legal_dong_code="1111000000",
                code_level="sigungu",
                code_name="종로구",
                sido_code="1100000000",
                sigungu_code="1111000000",
                sido_name="서울특별시",
                sigungu_name="종로구",
                legal_eupmyeondong_name=None,
                legal_ri_name=None,
                full_legal_dong_name="서울특별시 종로구",
                source_effective_date="20240101",
                source_change_reason_code="00",
                source_provider="fixture",
                source_status="active",
                source_file_name="fixture.csv",
                source_year_month="202401",
                source_file_hash="fixture",
                is_discontinued=False,
                is_active=True,
            ),
            AddressCodeStandard(
                legal_dong_code="1111010100",
                code_level="legal_dong",
                code_name="청운동",
                sido_code="1100000000",
                sigungu_code="1111000000",
                sido_name="서울특별시",
                sigungu_name="종로구",
                legal_eupmyeondong_name="청운동",
                legal_ri_name=None,
                full_legal_dong_name="서울특별시 종로구 청운동",
                source_effective_date="20240101",
                source_change_reason_code="00",
                source_provider="fixture",
                source_status="active",
                source_file_name="fixture.csv",
                source_year_month="202401",
                source_file_hash="fixture",
                is_discontinued=False,
                is_active=True,
            ),
        ]
    )
    db_session.flush()

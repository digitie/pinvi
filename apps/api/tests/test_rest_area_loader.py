from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.rest_area.loader import (
    load_rest_area_master,
    load_rest_area_oil_prices,
    load_rest_area_services,
)
from app.models.rest_area import (
    RestAreaRawMaster,
    RestAreaRawOilPrice,
    RestAreaRawService,
    RestAreaServingMaster,
    RestAreaServingOilPrice,
    RestAreaServingService,
)

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class _FakeKexPage:
    items: tuple[dict[str, str], ...]
    total_count: int | None = None


class FakeKexClient:
    def __init__(self) -> None:
        self.restarea = self

    def route_facilities(self, *, num_of_rows: int, page_no: int) -> _FakeKexPage:
        _ = num_of_rows
        rows = self._route_facility_rows() if page_no == 1 else []
        return _FakeKexPage(items=tuple(rows), total_count=len(rows))

    def fuel_prices(self, *, num_of_rows: int, page_no: int) -> _FakeKexPage:
        _ = num_of_rows
        rows = self._fuel_price_rows() if page_no == 1 else []
        return _FakeKexPage(items=tuple(rows), total_count=len(rows))

    def convenience_facilities(self, *, num_of_rows: int, page_no: int) -> _FakeKexPage:
        _ = num_of_rows
        rows = self._service_rows() if page_no == 1 else []
        return _FakeKexPage(items=tuple(rows), total_count=len(rows))

    def _route_facility_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "A00001",
                "serviceAreaCode2": "000001",
                "serviceAreaName": "서울만남(부산)휴게소",
                "routeCode": "0010",
                "routeName": "경부선",
                "direction": "부산",
                "telNo": "02-578-3372",
                "svarAddr": "서울 서초구 원지동 10-16",
                "convenience": "수유실|쉼터",
                "brand": "탐앤탐스",
                "maintenanceYn": "X",
                "truckSaYn": "X",
                "batchMenu": "라면",
            },
            {
                "serviceAreaCode": "A99999",
                "serviceAreaName": "코드없는휴게소",
            },
        ]

    def _fuel_price_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "B00001",
                "serviceAreaCode2": "000001",
                "serviceAreaName": "서울만남(부산)주유소",
                "routeCode": "0010",
                "routeName": "경부선",
                "direction": "부산",
                "oilCompany": "AD",
                "lpgYn": "Y",
                "gasolinePrice": "1,994원",
                "diselPrice": "1,993원",
                "lpgPrice": "1,087원",
            },
            {
                "serviceAreaCode": "B99999",
                "serviceAreaCode2": "999999",
                "serviceAreaName": "미매핑주유소",
                "gasolinePrice": "1,700원",
            },
        ]

    def _service_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "A00001",
                "serviceAreaCode2": "000001",
                "serviceAreaName": "서울만남(부산)휴게소",
                "routeCode": "0010",
                "routeName": "경부선",
                "direction": "부산",
                "convenience": "수유실|쉼터",
            },
            {
                "serviceAreaCode": "A99999",
                "serviceAreaCode2": "999999",
                "serviceAreaName": "미매핑휴게소",
                "convenience": "샤워실",
            },
        ]


class DuplicateMasterKexClient(FakeKexClient):
    def _route_facility_rows(self) -> list[dict[str, str]]:
        rows = super()._route_facility_rows()
        return [
            rows[0],
            {
                **rows[0],
                "serviceAreaCode": "AR00001",
                "direction": "서울",
            },
            rows[1],
        ]


class OffsetOilStationCodeKexClient(FakeKexClient):
    def _route_facility_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "A00001",
                "serviceAreaCode2": "000001",
                "serviceAreaName": "\uc11c\uc6b8\ub9cc\ub0a8(\ubd80\uc0b0)\ud734\uac8c\uc18c",
                "routeName": "\uacbd\ubd80\uc120",
                "direction": "\ubd80\uc0b0",
            }
        ]

    def _fuel_price_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "B00001",
                "serviceAreaCode2": "000002",
                "serviceAreaName": "\uc11c\uc6b8\ub9cc\ub0a8(\ubd80\uc0b0)\uc8fc\uc720\uc18c",
                "routeName": "\uacbd\ubd80\uc120",
                "direction": "\ubd80\uc0b0",
                "gasolinePrice": "1,900\uc6d0",
            }
        ]


class RawFuelPriceKexClient(FakeKexClient):
    def _page_ex(
        self,
        path: str,
        params: dict[str, object],
        parser: object,
    ) -> _FakeKexPage:
        assert path == "/openapi/business/curStateStation"
        assert params["numOfRows"] == 1000
        assert params["pageNo"] == 1
        assert parser is dict
        rows = self._fuel_price_rows()
        return _FakeKexPage(items=tuple(rows), total_count=len(rows))

    def fuel_prices(self, *args: object, **kwargs: object) -> _FakeKexPage:
        raise AssertionError("rest area oil loader should use raw fuel price rows")

    def _fuel_price_rows(self) -> list[dict[str, str]]:
        return [
            {
                "serviceAreaCode": "B00001",
                "serviceAreaCode2": "000001",
                "serviceAreaName": "raw-price-station",
                "routeCode": "0010",
                "routeName": "raw-route",
                "direction": "up",
                "oilCompany": "AD",
                "lpgYn": "X",
                "gasolinePrice": "X",
                "diselPrice": "1,880원",
                "lpgPrice": "X",
            }
        ]


def test_rest_area_master_loader_stores_raw_and_serving_rows(db_session: Session) -> None:
    result = load_rest_area_master(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(RestAreaRawMaster)).all()
    serving_rows = db_session.scalars(select(RestAreaServingMaster)).all()

    assert result.raw_row_count == 2
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 1
    assert len(raw_rows) == 2
    assert len(serving_rows) == 1
    assert serving_rows[0].svar_cd == "000001"
    assert serving_rows[0].provider_service_area_code == "A00001"
    assert serving_rows[0].name == "서울만남(부산)휴게소"


def test_rest_area_master_loader_merges_duplicate_join_codes(db_session: Session) -> None:
    result = load_rest_area_master(
        db_session,
        DuplicateMasterKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 0, tzinfo=KST),
    )
    db_session.commit()

    serving_row = db_session.get(RestAreaServingMaster, "000001")

    assert result.raw_row_count == 3
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 1
    assert serving_row is not None
    assert serving_row.provider_service_area_code == "A00001|AR00001"
    assert serving_row.direction == "부산|서울"
    assert len(serving_row.raw_payload["merged_rows"]) == 2


def test_rest_area_oil_loader_skips_fk_mismatch_and_writes_jsonl(
    db_session: Session,
    tmp_path: Path,
) -> None:
    load_rest_area_master(db_session, FakeKexClient())  # type: ignore[arg-type]

    result = load_rest_area_oil_prices(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
        fk_mismatch_log_dir=tmp_path,
        run_id="dagster-run-1",
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(RestAreaRawOilPrice)).all()
    serving_rows = db_session.scalars(
        select(RestAreaServingOilPrice).order_by(RestAreaServingOilPrice.provider_fuel_code)
    ).all()
    log_path = tmp_path / "rest_area_oil_price" / "dagster-run-1.jsonl"
    logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert result.raw_row_count == 2
    assert result.serving_row_count == 3
    assert result.skipped_row_count == 1
    assert len(raw_rows) == 2
    assert [(row.fuel_type, row.price_per_liter_krw) for row in serving_rows] == [
        ("diesel", 1993),
        ("gasoline", 1994),
        ("lpg", 1087),
    ]
    assert serving_rows[0].price_time_source == "collected_at"
    assert result.fk_mismatch_log_path == str(log_path)
    assert logged == [
        {
            "collected_at": "2026-04-26T06:10:00+09:00",
            "dataset": "rest_area_oil_price",
            "reason": "missing_rest_area_master_fk",
            "serviceAreaCode2": "999999",
            "source_endpoint": "business/curStateStation",
            "source_key": "999999",
        }
    ]


def test_rest_area_oil_loader_maps_offset_station_code_by_name_route_direction(
    db_session: Session,
) -> None:
    client = OffsetOilStationCodeKexClient()
    load_rest_area_master(db_session, client)  # type: ignore[arg-type]

    result = load_rest_area_oil_prices(
        db_session,
        client,  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
    )
    db_session.commit()

    serving_row = db_session.scalar(select(RestAreaServingOilPrice))

    assert result.raw_row_count == 1
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 0
    assert serving_row is not None
    assert serving_row.svar_cd == "000001"
    assert serving_row.price_per_liter_krw == 1900


def test_rest_area_oil_loader_uses_raw_rows_for_provider_x_prices(
    db_session: Session,
) -> None:
    client = RawFuelPriceKexClient()
    load_rest_area_master(db_session, client)  # type: ignore[arg-type]

    result = load_rest_area_oil_prices(
        db_session,
        client,  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(select(RestAreaServingOilPrice)).all()

    assert result.raw_row_count == 1
    assert result.serving_row_count == 1
    assert serving_rows[0].fuel_type == "diesel"
    assert serving_rows[0].price_per_liter_krw == 1880


def test_rest_area_oil_loader_keeps_multiple_daily_snapshots(db_session: Session) -> None:
    load_rest_area_master(db_session, FakeKexClient())  # type: ignore[arg-type]

    load_rest_area_oil_prices(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
    )
    load_rest_area_oil_prices(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 18, 10, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(
        select(RestAreaServingOilPrice).order_by(
            RestAreaServingOilPrice.collected_at,
            RestAreaServingOilPrice.provider_fuel_code,
        )
    ).all()

    assert len(serving_rows) == 6
    assert len({row.collected_at for row in serving_rows}) == 2


def test_rest_area_oil_loader_reuses_same_collected_at_snapshot(db_session: Session) -> None:
    load_rest_area_master(db_session, FakeKexClient())  # type: ignore[arg-type]
    collected_at = datetime(2026, 4, 26, 6, 10, tzinfo=KST)

    load_rest_area_oil_prices(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=collected_at,
    )
    load_rest_area_oil_prices(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=collected_at,
    )
    db_session.commit()

    serving_rows = db_session.scalars(select(RestAreaServingOilPrice)).all()

    assert len(serving_rows) == 3


def test_rest_area_service_loader_splits_convenience_and_skips_fk_mismatch(
    db_session: Session,
    tmp_path: Path,
) -> None:
    load_rest_area_master(db_session, FakeKexClient())  # type: ignore[arg-type]

    result = load_rest_area_services(
        db_session,
        FakeKexClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 20, tzinfo=KST),
        fk_mismatch_log_dir=tmp_path,
        run_id="dagster-run-2",
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(RestAreaRawService)).all()
    serving_rows = db_session.scalars(
        select(RestAreaServingService).order_by(RestAreaServingService.provider_service_name)
    ).all()
    log_path = tmp_path / "rest_area_svcs" / "dagster-run-2.jsonl"

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.skipped_row_count == 1
    assert len(raw_rows) == 2
    assert [row.provider_service_name for row in serving_rows] == ["쉼터", "수유실"]
    assert [row.display_name for row in serving_rows] == ["쉼터", "수유실"]
    assert result.fk_mismatch_log_path == str(log_path)
    assert "999999" in log_path.read_text(encoding="utf-8")

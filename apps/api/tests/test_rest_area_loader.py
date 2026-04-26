from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.rest_area.client import ExpresswayApiClient, ExpresswayApiError
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


class FakeExpresswayClient:
    def fetch_rest_area_master(self) -> list[dict[str, str]]:
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

    def fetch_rest_area_oil_prices(self) -> list[dict[str, str]]:
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

    def fetch_rest_area_services(self) -> list[dict[str, str]]:
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


class DuplicateMasterExpresswayClient(FakeExpresswayClient):
    def fetch_rest_area_master(self) -> list[dict[str, str]]:
        rows = super().fetch_rest_area_master()
        return [
            rows[0],
            {
                **rows[0],
                "serviceAreaCode": "AR00001",
                "direction": "서울",
            },
            rows[1],
        ]


def test_rest_area_master_loader_stores_raw_and_serving_rows(db_session: Session) -> None:
    result = load_rest_area_master(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
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
        DuplicateMasterExpresswayClient(),  # type: ignore[arg-type]
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
    load_rest_area_master(db_session, FakeExpresswayClient())  # type: ignore[arg-type]

    result = load_rest_area_oil_prices(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
        fk_mismatch_log_dir=tmp_path,
        run_id="dag-run-1",
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(RestAreaRawOilPrice)).all()
    serving_rows = db_session.scalars(
        select(RestAreaServingOilPrice).order_by(RestAreaServingOilPrice.provider_fuel_code)
    ).all()
    log_path = tmp_path / "rest_area_oil_price" / "dag-run-1.jsonl"
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


def test_rest_area_oil_loader_keeps_multiple_daily_snapshots(db_session: Session) -> None:
    load_rest_area_master(db_session, FakeExpresswayClient())  # type: ignore[arg-type]

    load_rest_area_oil_prices(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 10, tzinfo=KST),
    )
    load_rest_area_oil_prices(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
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
    load_rest_area_master(db_session, FakeExpresswayClient())  # type: ignore[arg-type]
    collected_at = datetime(2026, 4, 26, 6, 10, tzinfo=KST)

    load_rest_area_oil_prices(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
        collected_at=collected_at,
    )
    load_rest_area_oil_prices(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
        collected_at=collected_at,
    )
    db_session.commit()

    serving_rows = db_session.scalars(select(RestAreaServingOilPrice)).all()

    assert len(serving_rows) == 3


def test_rest_area_service_loader_splits_convenience_and_skips_fk_mismatch(
    db_session: Session,
    tmp_path: Path,
) -> None:
    load_rest_area_master(db_session, FakeExpresswayClient())  # type: ignore[arg-type]

    result = load_rest_area_services(
        db_session,
        FakeExpresswayClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 6, 20, tzinfo=KST),
        fk_mismatch_log_dir=tmp_path,
        run_id="dag-run-2",
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(RestAreaRawService)).all()
    serving_rows = db_session.scalars(
        select(RestAreaServingService).order_by(RestAreaServingService.provider_service_name)
    ).all()
    log_path = tmp_path / "rest_area_svcs" / "dag-run-2.jsonl"

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.skipped_row_count == 1
    assert len(raw_rows) == 2
    assert [row.provider_service_name for row in serving_rows] == ["쉼터", "수유실"]
    assert [row.display_name for row in serving_rows] == ["쉼터", "수유실"]
    assert result.fk_mismatch_log_path == str(log_path)
    assert "999999" in log_path.read_text(encoding="utf-8")


def test_expressway_client_requires_api_key() -> None:
    client = ExpresswayApiClient(api_key="")

    with pytest.raises(ExpresswayApiError, match="API key"):
        client.fetch_rest_area_master()


def test_expressway_client_paginates_with_key_and_json_type() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        page_no = request.url.params["pageNo"]
        if page_no == "1":
            return httpx.Response(
                200,
                json={
                    "code": "SUCCESS",
                    "list": [{"serviceAreaCode2": f"{index:06d}"} for index in range(1, 101)],
                },
            )
        return httpx.Response(200, json={"code": "SUCCESS", "list": []})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://data.ex.co.kr") as http_client:
        client = ExpresswayApiClient(api_key="local-test-key", client=http_client)
        rows = client.fetch_rest_area_master()

    assert rows[0] == {"serviceAreaCode2": "000001"}
    assert rows[-1] == {"serviceAreaCode2": "000100"}
    assert len(rows) == 100
    assert [request.url.params["pageNo"] for request in seen_requests] == ["1", "2"]
    assert all(request.url.params["key"] == "local-test-key" for request in seen_requests)
    assert all(request.url.params["type"] == "json" for request in seen_requests)
    assert all(request.url.params["numOfRows"] == "100" for request in seen_requests)

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.etl.tour import public_cultural_festival as festival_module
from app.etl.tour.public_cultural_festival import (
    DataGoPublicCulturalFestivalClient,
    load_public_cultural_festivals,
)
from app.main import create_app
from app.models.address import (
    AddressCodeStandard,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.models.tour import (
    TourRawPublicCulturalFestival,
    TourServingPublicCulturalFestival,
)

KST = ZoneInfo("Asia/Seoul")


class FakePublicCulturalFestivalClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetch_rows(self) -> list[dict[str, Any]]:
        return self._rows


def test_data_go_public_cultural_festival_client_fetches_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(festival_module, "MAX_PAGE_SIZE", 1)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_no = request.url.params["pageNo"]
        row = {
            "1": {"fstvlNm": "첫 축제", "fstvlStartDate": "2026-04-01"},
            "2": {"fstvlNm": "두 번째 축제", "fstvlStartDate": "2026-05-01"},
        }[page_no]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"totalCount": "2", "items": [row]},
                }
            },
        )

    client = DataGoPublicCulturalFestivalClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows()

    assert [row["fstvlNm"] for row in rows] == ["첫 축제", "두 번째 축제"]
    assert len(requests) == 2
    assert requests[0].url.path.endswith("/tn_pubr_public_cltur_fstvl_api")
    assert requests[0].url.params["serviceKey"] == "test-key"
    assert requests[0].url.params["numOfRows"] == "1"
    assert requests[0].url.params["type"] == "json"


def test_data_go_public_cultural_festival_client_treats_no_data_as_empty() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "03", "resultMsg": "NO_DATA"},
                    "body": {"totalCount": "0", "items": None},
                }
            },
        )

    client = DataGoPublicCulturalFestivalClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows()

    assert rows == []


def test_data_go_public_cultural_festival_client_retries_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(festival_module, "REQUEST_RETRY_SECONDS", 0)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"totalCount": "1", "items": [{"fstvlNm": "재시도 축제"}]},
                }
            },
        )

    client = DataGoPublicCulturalFestivalClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows()

    assert calls == 2
    assert rows[0]["fstvlNm"] == "재시도 축제"


def test_public_cultural_festival_loader_maps_road_address_and_is_idempotent(
    db_session: Session,
) -> None:
    _seed_juso_address(db_session)
    rows = [
        {
            "fstvlNm": " <b>서울 봄 축제</b> ",
            "opar": "광장 일대",
            "fstvlStartDate": "2026-04-01",
            "fstvlEndDate": "2026-04-05",
            "fstvlCo": "거리 공연<br>전시",
            "mnnstNm": "서울특별시",
            "auspcInsttNm": "서울특별시",
            "phoneNumber": "02-123-4567",
            "homepageUrl": "festival.example",
            "rdnmadr": "서울특별시 종로구 세종대로 1",
            "lnmadr": "서울특별시 종로구 청운동 1",
            "latitude": "37.500000",
            "longitude": "127.000000",
            "referenceDate": "2026-03-16",
            "instt_code": "1111000",
            "instt_nm": "서울특별시 종로구",
        },
        {"opar": "이름 없는 row"},
    ]

    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(rows),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    second_result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(rows),
        collected_at=datetime(2026, 4, 2, 9, 5, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(TourRawPublicCulturalFestival)).all()
    festivals = db_session.scalars(select(TourServingPublicCulturalFestival)).all()

    assert result.raw_row_count == 1
    assert result.serving_row_count == 1
    assert result.mapped_row_count == 1
    assert result.road_address_mapped_count == 1
    assert result.skipped_row_count == 1
    assert second_result.raw_row_count == 0
    assert second_result.serving_row_count == 1
    assert len(raw_rows) == 1
    assert len(festivals) == 1

    festival = festivals[0]
    assert festival.festival_name == "서울 봄 축제"
    assert festival.normalized_festival_name == "서울 봄 축제"
    assert festival.event_start_date == date(2026, 4, 1)
    assert festival.event_end_date == date(2026, 4, 5)
    assert festival.event_status == "ongoing"
    assert festival.festival_content == "거리 공연 전시"
    assert festival.homepage_url == "https://festival.example"
    assert festival.legal_dong_code == "1111010100"
    assert festival.road_name_code == "111103000001"
    assert festival.road_address_management_no == "1111010100100010000000001"
    assert festival.sigungu_code == "1111000000"
    assert festival.sido_code == "1100000000"
    assert festival.address_mapping_method == "juso_road_address_exact"
    assert festival.place_join_key.startswith("data_go_kr:public_cultural_festival:")
    assert festival.is_active is True


def test_public_cultural_festival_loader_deduplicates_source_rows_in_single_fetch(
    db_session: Session,
) -> None:
    row = {
        "fstvlNm": "Duplicate Festival",
        "opar": "Central Park",
        "fstvlStartDate": "2026-04-01",
        "fstvlEndDate": "2026-04-05",
        "rdnmadr": "Unknown Road Address",
    }

    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient([row, dict(row)]),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(TourRawPublicCulturalFestival)).all()
    festivals = db_session.scalars(select(TourServingPublicCulturalFestival)).all()

    assert result.raw_row_count == 1
    assert result.serving_row_count == 1
    assert result.duplicate_row_count == 1
    assert len(raw_rows) == 1
    assert len(festivals) == 1
    assert festivals[0].festival_name == "Duplicate Festival"


def test_public_cultural_festival_loader_appends_raw_snapshot_when_source_changes(
    db_session: Session,
) -> None:
    first_row = {
        "fstvlNm": "서울 봄 축제",
        "opar": "광장 일대",
        "fstvlStartDate": "2026-04-01",
        "fstvlEndDate": "2026-04-05",
        "fstvlCo": "거리 공연",
        "rdnmadr": "매칭되지 않는 도로명주소",
    }
    changed_row = {**first_row, "fstvlCo": "거리 공연과 전시"}

    first_result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient([first_row]),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    second_result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient([changed_row]),
        collected_at=datetime(2026, 4, 3, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(
        select(TourRawPublicCulturalFestival).order_by(
            TourRawPublicCulturalFestival.collected_at.asc()
        )
    ).all()
    festivals = db_session.scalars(select(TourServingPublicCulturalFestival)).all()

    assert first_result.raw_row_count == 1
    assert second_result.raw_row_count == 1
    assert len(raw_rows) == 2
    assert raw_rows[0].source_record_id == raw_rows[1].source_record_id
    assert raw_rows[0].response_hash != raw_rows[1].response_hash
    assert len(festivals) == 1
    assert festivals[0].festival_content == "거리 공연과 전시"
    assert festivals[0].collected_at == datetime(2026, 4, 3, 9, 0, tzinfo=KST)
    assert festivals[0].is_active is True


def test_public_cultural_festival_loader_deactivates_missing_source_rows(
    db_session: Session,
) -> None:
    _seed_legal_code(db_session)
    stale = _festival("stale", "지난 축제", date(2026, 3, 1), date(2026, 3, 2))
    db_session.add(stale)
    db_session.flush()

    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(
            [
                {
                    "fstvlNm": "새 축제",
                    "opar": "광장 일대",
                    "fstvlStartDate": "2026-04-01",
                    "fstvlEndDate": "2026-04-05",
                }
            ]
        ),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    stale_row = db_session.get(TourServingPublicCulturalFestival, stale.id)
    active_names = db_session.scalars(
        select(TourServingPublicCulturalFestival.festival_name)
        .where(TourServingPublicCulturalFestival.is_active.is_(True))
        .order_by(TourServingPublicCulturalFestival.festival_name.asc())
    ).all()

    assert result.serving_row_count == 1
    assert stale_row is not None
    assert stale_row.is_active is False
    assert active_names == ["새 축제"]


def test_public_cultural_festival_loader_falls_back_to_coordinate_mapping(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)

    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(
            [
                {
                    "fstvlNm": "좌표 축제",
                    "fstvlStartDate": "2026-05-01",
                    "fstvlEndDate": "2026-05-03",
                    "rdnmadr": "매칭되지 않는 도로명주소",
                    "lnmadr": "매칭되지 않는 지번주소",
                    "latitude": "37.500000",
                    "longitude": "127.000000",
                }
            ]
        ),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    festival = db_session.scalar(select(TourServingPublicCulturalFestival))

    assert result.coordinate_mapped_count == 1
    assert festival is not None
    assert festival.legal_dong_code == "1111010100"
    assert festival.address_mapping_method == "postgis_point_in_polygon"


def test_public_cultural_festival_loader_maps_jibun_address_without_fuzzy_matching(
    db_session: Session,
) -> None:
    _seed_juso_address(db_session)

    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(
            [
                {
                    "fstvlNm": "지번 축제",
                    "fstvlStartDate": "2026-05-01",
                    "fstvlEndDate": "2026-05-03",
                    "rdnmadr": "서울특별시 종로구 세종대로 999",
                    "lnmadr": "서울특별시 종로구 청운동 1",
                }
            ]
        ),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    festival = db_session.scalar(select(TourServingPublicCulturalFestival))

    assert result.jibun_address_mapped_count == 1
    assert festival is not None
    assert festival.legal_dong_code == "1111010100"
    assert festival.road_name_code == "111103000001"
    assert festival.road_address_management_no == "1111010100100010000000001"
    assert festival.address_mapping_method == "juso_jibun_address_exact"


def test_public_cultural_festival_loader_keeps_unmapped_rows(
    db_session: Session,
) -> None:
    result = load_public_cultural_festivals(
        db_session,
        FakePublicCulturalFestivalClient(
            [
                {
                    "fstvlNm": "매핑 보류 축제",
                    "fstvlStartDate": "2026-05-01",
                    "fstvlEndDate": "2026-05-03",
                    "rdnmadr": "주소 매칭 실패",
                    "lnmadr": "지번 매칭 실패",
                    "latitude": "좌표 아님",
                    "longitude": "좌표 아님",
                }
            ]
        ),
        collected_at=datetime(2026, 4, 2, 9, 0, tzinfo=KST),
    )
    db_session.commit()

    festival = db_session.scalar(select(TourServingPublicCulturalFestival))

    assert result.mapped_row_count == 0
    assert festival is not None
    assert festival.legal_dong_code is None
    assert festival.address_mapping_method == "unmapped"
    assert festival.is_active is True


def test_public_festival_monthly_api_returns_month_counts_and_rows(
    db_session: Session,
) -> None:
    _seed_legal_code(db_session)
    db_session.add_all(
        [
            _festival("spring", "봄 축제", date(2026, 4, 24), date(2026, 5, 5)),
            _festival("summer", "여름 축제", date(2026, 7, 1), date(2026, 7, 3)),
        ]
    )
    db_session.commit()
    client = _build_client(db_session)

    response = client.get("/public/festivals/monthly", params={"year": 2026, "month": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["month"] == 5
    assert payload["months"][3]["count"] == 1
    assert payload["months"][4]["count"] == 1
    assert [row["festival_name"] for row in payload["festivals"]] == ["봄 축제"]
    assert payload["festivals"][0]["id"]


def test_public_festival_detail_and_marker_api_exposes_map_layer_contract(
    db_session: Session,
) -> None:
    _seed_legal_code(db_session)
    festival = _festival(
        "spring",
        "봄 축제",
        date(2026, 4, 24),
        date(2026, 5, 5),
        longitude=Decimal("126.97800000"),
        latitude=Decimal("37.56650000"),
    )
    db_session.add(festival)
    db_session.commit()
    client = _build_client(db_session)

    detail_response = client.get(f"/public/festivals/{festival.id}")
    marker_response = client.get("/public/festivals/map-markers")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == str(festival.id)
    assert detail_payload["festival_name"] == "봄 축제"
    assert detail_payload["marker_color"] == "#ff5a5f"
    assert detail_payload["marker_icon"] == "music"

    assert marker_response.status_code == 200
    marker_payload = marker_response.json()
    assert marker_payload["layer_key"] == "festival"
    assert marker_payload["display_name"] == "축제"
    assert marker_payload["markers"][0]["id"] == str(festival.id)
    assert marker_payload["markers"][0]["title"] == "봄 축제"
    assert marker_payload["markers"][0]["marker_icon"] == "music"


def test_public_festival_marker_api_hides_inactive_and_unlocated_rows(
    db_session: Session,
) -> None:
    _seed_legal_code(db_session)
    active = _festival(
        "active",
        "지도 표시 축제",
        date(2026, 4, 24),
        date(2026, 5, 5),
        longitude=Decimal("126.97800000"),
        latitude=Decimal("37.56650000"),
    )
    inactive = _festival(
        "inactive",
        "비활성 축제",
        date(2026, 4, 24),
        date(2026, 5, 5),
        longitude=Decimal("126.97900000"),
        latitude=Decimal("37.56750000"),
    )
    inactive.is_active = False
    unlocated = _festival("unlocated", "좌표 없는 축제", date(2026, 4, 24), date(2026, 5, 5))
    db_session.add_all([active, inactive, unlocated])
    db_session.commit()
    client = _build_client(db_session)

    response = client.get("/public/festivals/map-markers")

    assert response.status_code == 200
    payload = response.json()
    assert [marker["title"] for marker in payload["markers"]] == ["지도 표시 축제"]


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed_juso_address(session: Session) -> None:
    _seed_legal_code(session)
    session.add(
        AddressServingJusoRoadAddress(
            road_address_management_no="1111010100100010000000001",
            legal_dong_code="1111010100",
            road_name_code="111103000001",
            administrative_dong_code="1111051500",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name="청운동",
            legal_ri_name=None,
            road_name="세종대로",
            administrative_dong_name="청운효자동",
            mountain_yn="0",
            jibun_main_no="1",
            jibun_sub_no="0",
            underground_yn="0",
            building_main_no="1",
            building_sub_no="0",
            postal_code="03000",
            previous_road_address=None,
            apartment_yn="0",
            building_registry_name=None,
            sigungu_building_name=None,
            note=None,
            full_legal_dong_name="서울특별시 종로구 청운동",
            full_road_address="서울특별시 종로구 세종대로 1",
            source_effective_date="20260401",
            source_change_reason_code="00",
            source_file_name="rnaddrkor_test.txt",
            source_year_month="202604",
            source_file_hash="road-hash",
            is_active=True,
        )
    )
    session.flush()
    session.add(
        AddressServingJusoRelatedJibun(
            road_address_management_no="1111010100100010000000001",
            legal_dong_code="1111010100",
            road_name_code="111103000001",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name="청운동",
            legal_ri_name=None,
            mountain_yn="0",
            jibun_main_no="1",
            jibun_sub_no="0",
            underground_yn="0",
            building_main_no="1",
            building_sub_no="0",
            note=None,
            full_legal_dong_name="서울특별시 종로구 청운동",
            full_jibun_address="서울특별시 종로구 청운동 1",
            source_file_name="jibun_rnaddrkor_test.txt",
            source_year_month="202604",
            source_file_hash="jibun-hash",
            is_active=True,
        )
    )
    session.flush()


def _seed_legal_boundary(session: Session) -> None:
    _seed_legal_code(session)
    batch = RegionBoundaryImportBatch(
        source_file_name="boundary.zip",
        source_file_hash="boundary-hash",
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        source_encoding="cp949",
        source_srid=5179,
        serving_srid=4326,
        row_count=1,
        status="loaded",
    )
    session.add(batch)
    session.flush()
    raw = RegionRawVWorldBoundary(
        import_batch_id=batch.id,
        row_number=1,
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        ufid="UFID-1",
        bjcd="1111010100",
        name="청운동",
        divi="HJD",
        scls="0",
        fmta="0",
        raw_attributes={"A1": "서울특별시"},
        source_file_name="boundary.zip",
        source_file_hash="boundary-hash",
        geom=WKTElement(
            "MULTIPOLYGON(((126.9 37.4, 127.1 37.4, 127.1 37.6, 126.9 37.6, 126.9 37.4)))",
            srid=5179,
        ),
    )
    session.add(raw)
    session.flush()
    session.add(
        RegionServingBoundary(
            raw_boundary_id=raw.id,
            import_batch_id=batch.id,
            layer_code="N3A_G0110000",
            boundary_level="legal_dong",
            region_code="1111010100",
            region_name="청운동",
            sido_code="1100000000",
            sigungu_code="1111000000",
            legal_dong_code="1111010100",
            parent_region_code="1111000000",
            full_region_name="서울특별시 종로구 청운동",
            address_code_standard_code="1111010100",
            address_code_matched=True,
            source_file_name="boundary.zip",
            source_file_hash="boundary-hash",
            geom=WKTElement(
                "MULTIPOLYGON(((126.9 37.4, 127.1 37.4, 127.1 37.6, 126.9 37.6, 126.9 37.4)))",
                srid=4326,
            ),
        )
    )
    session.flush()


def _seed_legal_code(session: Session) -> None:
    if session.get(AddressCodeStandard, "1111010100") is not None:
        return
    session.add(
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
            source_effective_date="20260401",
            source_change_reason_code="00",
            source_provider="test",
            source_status="active",
            source_file_name="test.csv",
            source_year_month="202604",
            source_file_hash="hash",
            source_sort_order=None,
            source_created_date=None,
            source_deleted_date=None,
            previous_legal_dong_code=None,
            is_discontinued=False,
            is_active=True,
        )
    )
    session.flush()


def _festival(
    source_record_id: str,
    festival_name: str,
    start_date: date,
    end_date: date,
    *,
    longitude: Decimal | None = None,
    latitude: Decimal | None = None,
) -> TourServingPublicCulturalFestival:
    return TourServingPublicCulturalFestival(
        provider="data_go_kr",
        source_record_id=source_record_id,
        place_join_key=f"data_go_kr:public_cultural_festival:{source_record_id}",
        festival_name=festival_name,
        normalized_festival_name=festival_name,
        venue_name="테스트 광장",
        event_start_date=start_date,
        event_end_date=end_date,
        event_status="upcoming",
        festival_content="축제",
        mnnst_name=None,
        auspc_instt_name=None,
        suprt_instt_name=None,
        phone_number=None,
        homepage_url=None,
        related_info=None,
        road_address="서울특별시 종로구 세종대로 1",
        jibun_address=None,
        address_snapshot="서울특별시 종로구 세종대로 1",
        longitude=longitude,
        latitude=latitude,
        geom=None,
        legal_dong_code="1111010100",
        road_name_code=None,
        road_address_management_no=None,
        sigungu_code="1111000000",
        sido_code="1100000000",
        address_mapping_method="test",
        provider_institution_code=None,
        provider_institution_name=None,
        reference_date=date(2026, 3, 16),
        raw_payload={},
        collected_at=datetime(2026, 4, 28, 9, 0, tzinfo=KST),
        is_active=True,
    )

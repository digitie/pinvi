"""Map `/v1/service/transport/*` 응답 fixture (ADR-076).

모든 fixture는 vendored `contract/kor-travel-map-openapi-service.json`의 응답 schema에 맞는다 —
`tests/unit/test_kor_travel_map_transport_contract.py`가 매번 대조한다(낡은 대역이 계약 파손을 가리지
않게). 단위·통합 테스트가 함께 쓴다.
"""

from __future__ import annotations

import copy
from typing import Any

FUEL_STATION_ID = "f_x_place_0123456789abcdef"
REST_AREA_ID = "f_x_place_fedcba9876543210"
INCIDENT_ID = "f_x_notice_00aa11bb22cc33dd"
AIRPORT_ID = "f_x_place_a1b2c3d4e5f60718"


def freshness(dataset: str, *, stale: bool = False, collected: bool = True) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "generation": "g-20261023T0900",
        "source_collected_at": "2026-10-23T09:00:00+09:00" if collected else None,
        "loaded_at": "2026-10-23T09:05:00+09:00",
        "age_seconds": 600,
        "max_age_seconds": 172800,
        "stale": stale,
        "item_count": 1,
    }


def meta(*, page: bool = True, next_cursor: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"duration_ms": 3, "request_id": "req-1"}
    if page:
        out["page"] = {"page_size": 200, "next_cursor": next_cursor}
    return out


_FUEL_STATION: dict[str, Any] = {
    "feature_id": FUEL_STATION_ID,
    "kind": "place",
    "category": "06020000",
    "marker_icon": "fuel",
    "marker_color": "P-08",
    "name": "PinVi 셀프주유소",
    "natural_key": "A0001234",
    "coord": {"lon": 127.0276, "lat": 37.4979},
    "address": {"road": "서울 강남구 테헤란로 1", "jibun": None, "bjd_code": "1168010100"},
    "brand_code": "SKE",
    "brand_name": "SK에너지",
    "phone": "02-000-0000",
    "is_self": True,
    "is_24h": False,
    "has_carwash": True,
    "has_cvs": None,
    "has_maintenance": False,
    "lpg_available": False,
    "prices": [
        {
            "product_key": "gasoline",
            "product_code": "B027",
            "product_name": "휘발유",
            "price": 1689.0,
            "unit": "KRW/L",
            "collected_at": "2026-10-23T09:00:00+09:00",
            "provider_updated_at": "2026-10-23T06:00:00+09:00",
        },
        {
            "product_key": "diesel",
            "product_code": "D047",
            "product_name": "경유",
            "price": None,
            "unit": "KRW/L",
            "collected_at": "2026-10-23T09:00:00+09:00",
            "provider_updated_at": None,
        },
    ],
    "source_last_seen_at": "2026-10-23T09:00:00+09:00",
    "distance_m": None,
}

_REST_AREA: dict[str, Any] = {
    "feature_id": REST_AREA_ID,
    "kind": "place",
    "category": "06040101",
    "marker_icon": "fast-food",
    "marker_color": "P-06",
    "name": "망향휴게소",
    "natural_key": "망향휴게소::경부선::부산",
    "coord": {"lon": 127.2, "lat": 36.9},
    "address": {"road": "충남 천안시 서북구", "jibun": None, "bjd_code": None},
    "route_name": "경부선",
    "direction": "부산",
    "phone": None,
    "has_gas_station": True,
    "has_lpg_station": False,
    "has_ev_charger": True,
    "fuel_prices": {
        "feature_id": "f_x_price_1111222233334444",
        "kind": "price",
        "service_area_code": "A00001",
        "service_area_name": "망향",
        "match_key": "망향휴게소::경부선::부산",
        "route_name": "경부선",
        "direction": "부산",
        "address": None,
        "phone": None,
        "oil_company": "GS칼텍스",
        "gasoline_price": 1650,
        "diesel_price": 1540,
        "lpg_price": None,
        "unit": "KRW/L",
        "observed_at": "2026-10-23T08:00:00+09:00",
    },
    "distance_m": None,
}

_INCIDENT: dict[str, Any] = {
    "feature_id": INCIDENT_ID,
    "kind": "notice",
    "category": "99000000",
    "marker_icon": "roadblock",
    "marker_color": "P-13",
    "title": "경부선 사고",
    "notice_type": "highway_incident",
    "natural_key": "INC-1",
    "coord": {"lon": 127.1, "lat": 37.2},
    "message": "2차로 사고 처리 중",
    "incident_type": "사고",
    "incident_type_code": "1",
    "process_status": "처리중",
    "process_status_code": "2",
    "route_name": "경부선",
    "route_no": "0010",
    "direction": "서울",
    "point_name": "기흥IC",
    "congestion_length": 1.5,
    "occurred_at": "2026-10-23T08:40:00+09:00",
    "distance_m": None,
}

_AIRPORT: dict[str, Any] = {
    "feature_id": AIRPORT_ID,
    "kind": "place",
    "category": "06030100",
    "marker_icon": "airport",
    "marker_color": "P-10",
    "name": "김포국제공항",
    "name_english": "Gimpo International Airport",
    "iata_code": "GMP",
    "icao_code": "RKSS",
    "municipality": "서울",
    "coord": {"lon": 126.7906, "lat": 37.5583},
    "address": {"road": "서울 강서구 하늘길 112", "jibun": None, "bjd_code": None},
    "distance_m": None,
}

ITEMS: dict[str, dict[str, Any]] = {
    "fuel-stations": _FUEL_STATION,
    "rest-areas": _REST_AREA,
    "highway-incidents": _INCIDENT,
    "airports": _AIRPORT,
}

DATASET_NAMES: dict[str, str] = {
    "fuel-stations": "transport.fuel_stations",
    "rest-areas": "transport.rest_areas",
    "highway-incidents": "transport.highway_incidents",
    "airports": "transport.airports",
}

#: fixture 이름 → vendored OpenAPI 응답 schema 이름.
RESPONSE_SCHEMAS: dict[str, str] = {
    "list:fuel-stations": "FuelStationListResponse",
    "list:rest-areas": "RestAreaListResponse",
    "list:highway-incidents": "HighwayIncidentListResponse",
    "list:airports": "AirportListResponse",
    "detail:fuel-stations": "FuelStationDetailResponse",
    "detail:rest-areas": "RestAreaDetailResponse",
    "detail:highway-incidents": "HighwayIncidentDetailResponse",
    "detail:airports": "AirportDetailResponse",
    "history:available": "FuelStationPriceHistoryResponse",
    "history:unavailable": "FuelStationPriceHistoryResponse",
    "status": "TransportStatusResponse",
    "problem:not_loaded": "ProblemDetail",
}


def item(dataset: str) -> dict[str, Any]:
    return copy.deepcopy(ITEMS[dataset])


def list_body(dataset: str, *, truncated: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "items": [item(dataset)],
        "truncated": truncated,
        "freshness": freshness(DATASET_NAMES[dataset]),
    }
    if dataset == "rest-areas":
        data["fuel_price_freshness"] = freshness("transport.rest_area_fuel_prices")
    return {"data": data, "meta": meta()}


def detail_body(dataset: str) -> dict[str, Any]:
    data: dict[str, Any] = {"item": item(dataset), "freshness": freshness(DATASET_NAMES[dataset])}
    if dataset == "rest-areas":
        data["fuel_price_freshness"] = None
    return {"data": data, "meta": meta(page=False)}


def history_body(*, available: bool) -> dict[str, Any]:
    history: dict[str, Any] = (
        {
            "status": "available",
            "reason": None,
            "generated_at": "2026-10-23T09:10:00+09:00",
            "truncated": False,
            "items": [
                {
                    "product_key": "gasoline",
                    "product_code": "B027",
                    "product_name": "휘발유",
                    "price": 1689.0,
                    "provider_updated_at": "2026-10-23T06:00:00+09:00",
                    "observed_at": "2026-10-23T06:00:00+09:00",
                    "collected_at": "2026-10-23T09:00:00+09:00",
                },
                {
                    "product_key": "diesel",
                    "product_code": "D047",
                    "product_name": "경유",
                    "price": 1570.0,
                    "provider_updated_at": None,
                    "observed_at": "2026-10-22T06:00:00+09:00",
                    "collected_at": "2026-10-22T09:00:00+09:00",
                },
            ],
        }
        if available
        else {
            "status": "unavailable",
            "reason": "disabled",
            "generated_at": None,
            "truncated": False,
            "items": [],
        }
    )
    return {
        "data": {
            "feature_id": FUEL_STATION_ID,
            "natural_key": "A0001234",
            "current_prices": item("fuel-stations")["prices"],
            "history": history,
            "freshness": freshness("transport.fuel_stations"),
        },
        "meta": meta(page=False),
    }


def status_body(*, fuel_loaded: bool = False) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    for name in (
        "transport.fuel_stations",
        "transport.rest_areas",
        "transport.rest_area_fuel_prices",
        "transport.highway_incidents",
        "transport.airports",
    ):
        loaded = fuel_loaded or name != "transport.fuel_stations"
        datasets.append(
            {
                "dataset": name,
                "loaded": loaded,
                "freshness": freshness(name) if loaded else None,
                "error": None,
            }
        )
    return {"data": {"store": "ok", "datasets": datasets}, "meta": meta(page=False)}


def problem_body(status: int, code: str) -> dict[str, Any]:
    return {
        "type": f"https://kor-travel-map/errors/{code.lower()}",
        "title": code,
        "status": status,
        "detail": code,
        "code": code,
        "request_id": "req-1",
    }


def all_fixtures() -> dict[str, dict[str, Any]]:
    """계약 게이트가 대조하는 fixture 전부(`RESPONSE_SCHEMAS`와 같은 키)."""
    out: dict[str, dict[str, Any]] = {}
    for dataset in ITEMS:
        out[f"list:{dataset}"] = list_body(dataset)
        out[f"detail:{dataset}"] = detail_body(dataset)
    out["history:available"] = history_body(available=True)
    out["history:unavailable"] = history_body(available=False)
    out["status"] = status_body()
    out["problem:not_loaded"] = problem_body(503, "TRANSPORT_STATE_NOT_LOADED")
    return out

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from krex import (
    KexAuthError,
    KexClient,
    RestAreaFuelPrice,
    RestAreaRouteFacility,
)

from app.core.config import Settings
from app.core.kex import build_kex_client


class _FakeKexResponse:
    status_code = 200
    text = "{}"

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)

    def json(self) -> Mapping[str, Any]:
        return self._payload


class _FakeKexSession:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = dict(payload)
        self.calls: list[dict[str, Any]] = []

    @property
    def last_params(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.calls[-1]["params"])

    @property
    def last_url(self) -> str:
        return cast(str, self.calls[-1]["url"])

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        timeout: float,
    ) -> _FakeKexResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        return _FakeKexResponse(self.payload)


def test_kex_client_factory_returns_krex_client_without_adapter_layer() -> None:
    client = build_kex_client(
        Settings(
            kex_ex_api_key="dummy-ex-key",
            kex_go_api_key="dummy-go-key",
            kex_timeout_seconds=1.5,
            kex_max_retries=0,
            kex_retry_backoff_seconds=0.0,
        )
    )

    assert isinstance(client, KexClient)
    assert client.ex_api_key == "dummy-ex-key"
    assert client.go_api_key == "dummy-go-key"
    assert client.strict_no_data is False


def test_kex_client_factory_accepts_existing_tripmate_key_names() -> None:
    client = build_kex_client(
        Settings(
            expressway_api_key="legacy-ex-key",
            data_go_service_key="legacy-go-key",
            kex_ex_api_key=None,
            kex_go_api_key=None,
        )
    )

    assert client.ex_api_key == "legacy-ex-key"
    assert client.go_api_key == "legacy-go-key"


def test_kex_client_factory_requires_tripmate_prefixed_key() -> None:
    with pytest.raises(KexAuthError, match="TRIPMATE_EXPRESSWAY_API_KEY"):
        build_kex_client(
            Settings(
                kex_ex_api_key=None,
                kex_go_api_key=None,
                expressway_api_key=None,
                data_go_service_key=None,
            )
        )


def test_krex_restarea_route_facilities_preserve_master_key_fields() -> None:
    session = _FakeKexSession(
        _ex_payload(
            {
                "routeCode": "0010",
                "serviceAreaCode": "A0001",
                "routeName": "경부고속도로",
                "direction": "서울",
                "serviceAreaName": "죽전휴게소",
                "telNo": "031-000-0000",
                "maintenanceYn": "Y",
                "truckSaYn": "N",
                "batchMenu": "죽전라면",
            }
        )
    )
    client = KexClient(ex_api_key="dummy-ex-key", session=session, retry_backoff=0)

    page = client.restarea.route_facilities(
        route_code="0010",
        service_area_code="A0001",
        num_of_rows=100,
    )

    assert session.last_url.endswith("/openapi/business/serviceAreaRoute")
    assert session.last_params["routeCode"] == "0010"
    assert session.last_params["serviceAreaCode"] == "A0001"
    assert session.last_params["numOfRows"] == 100
    assert isinstance(page.items[0], RestAreaRouteFacility)
    assert page.items[0].service_area_code == "A0001"
    assert page.items[0].service_area_name == "죽전휴게소"
    assert page.items[0].has_maintenance is True
    assert page.items[0].is_truck_rest_area is False


def test_krex_restarea_fuel_prices_parse_provider_prices_directly() -> None:
    session = _FakeKexSession(
        _ex_payload(
            [
                {
                    "routeCode": "0010",
                    "serviceAreaCode": "A0001",
                    "routeName": "경부고속도로",
                    "direction": "서울",
                    "oilCompany": "EX-OIL",
                    "lpgYn": "Y",
                    "serviceAreaName": "죽전휴게소",
                    "telNo": "031-000-0000",
                    "gasolinePrice": "1,710",
                    "diselPrice": "1,599",
                    "lpgPrice": "1,010",
                }
            ]
        )
    )
    client = KexClient(ex_api_key="dummy-ex-key", session=session, retry_backoff=0)

    page = client.restarea.fuel_prices(
        service_area_code="A0001",
        oil_company="EX-OIL",
        num_of_rows=100,
    )

    assert session.last_url.endswith("/openapi/business/curStateStation")
    assert session.last_params["serviceAreaCode"] == "A0001"
    assert session.last_params["numOfRows"] == 100
    assert isinstance(page.items[0], RestAreaFuelPrice)
    assert page.items[0].service_area_code == "A0001"
    assert page.items[0].oil_company == "EX-OIL"
    assert page.items[0].has_lpg is True
    assert page.items[0].gasoline_price == 1710
    assert page.items[0].diesel_price == 1599
    assert page.items[0].lpg_price == 1010


def test_krex_convenience_facilities_keep_raw_rows_until_schema_is_verified() -> None:
    session = _FakeKexSession(_ex_payload([{"serviceAreaCode": "A0001", "facilityCode": "BABY"}]))
    client = KexClient(ex_api_key="dummy-ex-key", session=session, retry_backoff=0)

    page = client.restarea.convenience_facilities(service_area_name="죽전휴게소", num_of_rows=100)

    assert session.last_url.endswith("/openapi/business/conveniServiceArea")
    assert session.last_params["serviceAreaName"] == "죽전휴게소"
    assert session.last_params["numOfRows"] == 100
    assert page.items[0] == {"serviceAreaCode": "A0001", "facilityCode": "BABY"}


def _ex_payload(items: object) -> dict[str, object]:
    return {"code": "SUCCESS", "pageNo": "1", "numOfRows": "1000", "count": "1", "list": items}

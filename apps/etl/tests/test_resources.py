"""Dagster resource 생성 테스트.

`test_definitions.py::test_definitions_load`는 `Definitions` object가 resource를
*등록*만 확인하고 실제로 `create_client()`를 호출하지 않는다 — `python-kasi-api`가
`AsyncKasiClient` export를 없애고 `KasiClient`(async-only)로 통합했을 때
(2026-09-14, "Unify KASI async-only clients"), 그 import 실패를 어떤 기존 테스트도
잡지 못했다(직접 호출 없이는 `KasiResource.create_client()` 자체가 실행되지 않는다).
"""

from __future__ import annotations

import httpx

from pinvi.etl.resources import KasiResource, KorTravelWeatherResource


def test_kasi_resource_create_client_returns_client() -> None:
    resource = KasiResource(service_key="dummy-key-for-unit-test")

    client = resource.create_client()

    from kasi import KasiClient

    assert isinstance(client, KasiClient)


def test_kor_travel_weather_resource_create_client_returns_httpx_client() -> None:
    resource = KorTravelWeatherResource(base_url="http://weather.invalid")

    client = resource.create_client()

    assert isinstance(client, httpx.AsyncClient)
    assert str(client.base_url) == "http://weather.invalid"

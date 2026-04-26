from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings

KST = ZoneInfo("Asia/Seoul")
KMA_BASE_URL = "http://apis.data.go.kr/1360000"
AIRKOREA_BASE_URL = "http://apis.data.go.kr/B552584"
MAX_PAGE_SIZE = 1000
MAX_PAGE_GUARD = 1000


class DataGoApiError(RuntimeError):
    pass


class KmaWeatherApiClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        base_url: str = KMA_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = (
            service_key if service_key is not None else get_settings().data_go_service_key
        )
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_ultra_short_nowcast(
        self,
        *,
        nx: int,
        ny: int,
        base_date: str | None = None,
        base_time: str | None = None,
    ) -> list[dict[str, Any]]:
        resolved_date, resolved_time = _resolve_ultra_short_base_time(base_date, base_time)
        return self._fetch_all(
            "/VilageFcstInfoService_2.0/getUltraSrtNcst",
            {
                "dataType": "JSON",
                "base_date": resolved_date,
                "base_time": resolved_time,
                "nx": str(nx),
                "ny": str(ny),
            },
        )

    def fetch_weather_warnings(self, *, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return self._fetch_all(
            "/WthrWrnInfoService/getWthrWrnList",
            {
                "dataType": "JSON",
                "fromTmFc": from_date.strftime("%Y%m%d"),
                "toTmFc": to_date.strftime("%Y%m%d"),
            },
        )

    def fetch_weather_infos(self, *, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return self._fetch_all(
            "/WthrWrnInfoService/getWthrInfoList",
            {
                "dataType": "JSON",
                "fromTmFc": from_date.strftime("%Y%m%d"),
                "toTmFc": to_date.strftime("%Y%m%d"),
            },
        )

    def fetch_weather_breaking_news(
        self, *, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            "/WthrWrnInfoService/getWthrBrkNewsList",
            {
                "dataType": "JSON",
                "fromTmFc": from_date.strftime("%Y%m%d"),
                "toTmFc": to_date.strftime("%Y%m%d"),
            },
        )

    def _fetch_all(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return _fetch_all(
            base_url=self._base_url,
            endpoint=endpoint,
            params=params,
            service_key_param="ServiceKey",
            service_key=self._service_key,
            client=self._client,
        )


class AirKoreaApiClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        base_url: str = AIRKOREA_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = (
            service_key if service_key is not None else get_settings().data_go_service_key
        )
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_station_list(self, *, sido_name: str | None = None) -> list[dict[str, Any]]:
        params = {"returnType": "json"}
        if sido_name:
            params["addr"] = sido_name
        return self._fetch_all("/MsrstnInfoInqireSvc/getMsrstnList", params)

    def fetch_forecast_dispatches(self, *, inform_code: str | None = None) -> list[dict[str, Any]]:
        params = {"returnType": "json"}
        if inform_code:
            params["InformCode"] = inform_code
        return self._fetch_all("/ArpltnInforInqireSvc/getMinuDustFrcstDspth", params)

    def fetch_sido_measurements(self, *, sido_name: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            "/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty",
            {
                "returnType": "json",
                "sidoName": sido_name,
                "ver": "1.3",
            },
        )

    def _fetch_all(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return _fetch_all(
            base_url=self._base_url,
            endpoint=endpoint,
            params=params,
            service_key_param="serviceKey",
            service_key=self._service_key,
            client=self._client,
        )


def _fetch_all(
    *,
    base_url: str,
    endpoint: str,
    params: dict[str, str],
    service_key_param: str,
    service_key: str | None,
    client: httpx.Client | None,
    page_size: int = MAX_PAGE_SIZE,
) -> list[dict[str, Any]]:
    api_key = (service_key or "").strip()
    if not api_key:
        raise DataGoApiError("data.go.kr service key is not configured.")

    rows: list[dict[str, Any]] = []
    page_no = 1
    resolved_page_size = min(page_size, MAX_PAGE_SIZE)
    while page_no <= MAX_PAGE_GUARD:
        payload = _get_json(
            base_url=base_url,
            endpoint=endpoint,
            params={
                service_key_param: api_key,
                "pageNo": str(page_no),
                "numOfRows": str(resolved_page_size),
                **params,
            },
            client=client,
        )
        page_rows, total_count = _extract_rows(payload, endpoint)
        rows.extend(page_rows)
        if not page_rows or len(rows) >= total_count or len(page_rows) < resolved_page_size:
            return rows
        page_no += 1
    raise DataGoApiError(f"data.go.kr pagination exceeded guard for {endpoint}.")


def _get_json(
    *,
    base_url: str,
    endpoint: str,
    params: dict[str, str],
    client: httpx.Client | None,
) -> dict[str, Any]:
    owns_client = client is None
    resolved_client = client or httpx.Client(timeout=30.0)
    try:
        response = resolved_client.get(f"{base_url}{endpoint}", params=params)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            resolved_client.close()
    if not isinstance(payload, dict):
        raise DataGoApiError(f"data.go.kr response for {endpoint} is not an object.")
    return payload


def _extract_rows(payload: dict[str, Any], endpoint: str) -> tuple[list[dict[str, Any]], int]:
    response = payload.get("response")
    if not isinstance(response, dict):
        raise DataGoApiError(f"data.go.kr response for {endpoint} is missing response.")
    header = response.get("header")
    if isinstance(header, dict):
        result_code = str(header.get("resultCode", ""))
        result_msg = str(header.get("resultMsg", ""))
        if result_code in {"03", "NO_DATA"}:
            return [], 0
        if result_code not in {"", "00", "NORMAL_CODE"}:
            raise DataGoApiError(f"data.go.kr failed for {endpoint}: {result_code} {result_msg}")

    body = response.get("body")
    if not isinstance(body, dict):
        return [], 0
    total_count = _coerce_int(body.get("totalCount"), default=0)
    items = body.get("items")
    if not isinstance(items, dict):
        return [], total_count
    raw_item = items.get("item")
    if raw_item is None:
        return [], total_count
    if isinstance(raw_item, dict):
        return [raw_item], max(total_count, 1)
    if isinstance(raw_item, list):
        return [row for row in raw_item if isinstance(row, dict)], total_count or len(raw_item)
    raise DataGoApiError(f"data.go.kr response for {endpoint} has invalid item.")


def _resolve_ultra_short_base_time(
    base_date: str | None,
    base_time: str | None,
) -> tuple[str, str]:
    if base_date and base_time:
        return base_date, base_time
    now = datetime.now(KST) - timedelta(hours=1)
    return now.strftime("%Y%m%d"), f"{now.hour:02d}00"


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

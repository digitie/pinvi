from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pykma import DataGoKrClient, KmaClient, KmaError

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
        if base_date and base_time:
            return self._kma_items(
                "VilageFcstInfoService_2.0",
                "getUltraSrtNcst",
                {"base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny},
            )
        return self._call_pykma(
            lambda: _items_from_pykma_body(
                self._forecast_client().now(nx=nx, ny=ny).raw,
                endpoint="getUltraSrtNcst",
            )
        )

    def fetch_ultra_short_forecast(
        self,
        *,
        nx: int,
        ny: int,
        base_date: str | None = None,
        base_time: str | None = None,
    ) -> list[dict[str, Any]]:
        if base_date and base_time:
            return self._kma_items(
                "VilageFcstInfoService_2.0",
                "getUltraSrtFcst",
                {"base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny},
            )
        return self._call_pykma(
            lambda: [
                dict(item.raw) for item in self._forecast_client().forecast_short(nx=nx, ny=ny)
            ]
        )

    def fetch_village_forecast(
        self,
        *,
        nx: int,
        ny: int,
        base_date: str | None = None,
        base_time: str | None = None,
    ) -> list[dict[str, Any]]:
        if base_date and base_time:
            return self._kma_items(
                "VilageFcstInfoService_2.0",
                "getVilageFcst",
                {"base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny},
            )
        return self._call_pykma(
            lambda: [dict(item.raw) for item in self._forecast_client().forecast(nx=nx, ny=ny)]
        )

    def fetch_weather_warnings(self, *, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return self._kma_items(
            "WthrWrnInfoService",
            "getWthrWrnList",
            {"fromTmFc": from_date.strftime("%Y%m%d"), "toTmFc": to_date.strftime("%Y%m%d")},
        )

    def fetch_weather_infos(self, *, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return self._kma_items(
            "WthrWrnInfoService",
            "getWthrInfoList",
            {"fromTmFc": from_date.strftime("%Y%m%d"), "toTmFc": to_date.strftime("%Y%m%d")},
        )

    def fetch_weather_breaking_news(
        self, *, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        return self._kma_items(
            "WthrWrnInfoService",
            "getWthrBrkNewsList",
            {"fromTmFc": from_date.strftime("%Y%m%d"), "toTmFc": to_date.strftime("%Y%m%d")},
        )

    def fetch_mid_outlook(
        self,
        *,
        stn_id: str,
        tm_fc: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._kma_items(
            "MidFcstInfoService",
            "getMidFcst",
            {"stnId": stn_id, "tmFc": tm_fc or _resolve_mid_tm_fc()},
        )

    def fetch_mid_land_forecast(
        self,
        *,
        reg_id: str,
        tm_fc: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._kma_items(
            "MidFcstInfoService",
            "getMidLandFcst",
            {"regId": reg_id, "tmFc": tm_fc or _resolve_mid_tm_fc()},
        )

    def fetch_mid_temperature(
        self,
        *,
        reg_id: str,
        tm_fc: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._kma_items(
            "MidFcstInfoService",
            "getMidTa",
            {"regId": reg_id, "tmFc": tm_fc or _resolve_mid_tm_fc()},
        )

    def fetch_tour_spot_weather(
        self,
        *,
        course_id: str,
        current_date: str | None = None,
        hour: str | None = None,
    ) -> list[dict[str, Any]]:
        resolved_date, resolved_hour = _resolve_tour_weather_time(current_date, hour)
        return self._kma_items(
            "TourStnInfoService1",
            "getTourStnVilageFcst1",
            {"CURRENT_DATE": resolved_date, "HOUR": resolved_hour, "COURSE_ID": course_id},
        )

    def _forecast_client(self) -> KmaClient:
        return KmaClient(
            self._required_service_key(),
            base_url=f"{self._base_url}/VilageFcstInfoService_2.0",
            timeout=30,
            retries=0,
            session=self._client,
        )

    def _data_client(self) -> DataGoKrClient:
        return DataGoKrClient(
            self._required_service_key(),
            base_url=self._base_url,
            service_key_param="ServiceKey",
            timeout=30,
            retries=0,
            session=self._client,
        )

    def _kma_items(
        self,
        service: str,
        operation: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        def collect_pages() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            client = self._data_client()
            for body in client.iter_pages(
                service,
                operation,
                params,
                num_of_rows=MAX_PAGE_SIZE,
                max_pages=MAX_PAGE_GUARD,
            ):
                rows.extend(_items_from_pykma_body(body, endpoint=f"{service}/{operation}"))
            return rows

        return self._call_pykma(collect_pages)

    def _required_service_key(self) -> str:
        api_key = (self._service_key or "").strip()
        if not api_key:
            raise DataGoApiError("data.go.kr service key is not configured.")
        return api_key

    def _call_pykma(
        self,
        callback: Callable[[], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        try:
            return callback()
        except KmaError as exc:
            if exc.result_code in {"03", "NO_DATA"}:
                return []
            raise DataGoApiError(str(exc)) from exc
        except ValueError as exc:
            raise DataGoApiError(str(exc)) from exc


def _items_from_pykma_body(
    body: Mapping[str, Any],
    *,
    endpoint: str,
) -> list[dict[str, Any]]:
    items = body.get("items")
    raw_item: object
    if isinstance(items, Mapping):
        raw_item = items.get("item")
    else:
        raw_item = items

    if raw_item is None:
        return []
    if isinstance(raw_item, Mapping):
        return [dict(raw_item)]
    if isinstance(raw_item, list):
        return [dict(row) for row in raw_item if isinstance(row, Mapping)]
    raise DataGoApiError(f"data.go.kr response for {endpoint} has invalid item.")


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
    if isinstance(items, list):
        return [row for row in items if isinstance(row, dict)], total_count or len(items)
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


def _resolve_mid_tm_fc() -> str:
    now = datetime.now(KST) - timedelta(minutes=40)
    if now.hour >= 18:
        return now.strftime("%Y%m%d") + "1800"
    if now.hour >= 6:
        return now.strftime("%Y%m%d") + "0600"
    previous = now - timedelta(days=1)
    return previous.strftime("%Y%m%d") + "1800"


def _resolve_tour_weather_time(
    current_date: str | None,
    hour: str | None,
) -> tuple[str, str]:
    if current_date and hour:
        return current_date, hour
    now = datetime.now(KST) - timedelta(hours=1)
    return now.strftime("%Y%m%d"), f"{now.hour:02d}"


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

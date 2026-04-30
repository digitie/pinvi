from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

EXPRESSWAY_API_BASE_URL = "https://data.ex.co.kr/openapi"
MAX_PAGE_SIZE = 100
MAX_PAGE_GUARD = 1000


class ExpresswayApiError(RuntimeError):
    pass


class ExpresswayApiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = EXPRESSWAY_API_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else get_settings().expressway_api_key
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_rest_area_master(self) -> list[dict[str, Any]]:
        return self._fetch_all("business/serviceAreaRoute")

    def fetch_rest_area_oil_prices(self) -> list[dict[str, Any]]:
        return self._fetch_all("business/curStateStation")

    def fetch_rest_area_services(self) -> list[dict[str, Any]]:
        return self._fetch_all("business/conveniServiceArea")

    def _fetch_all(self, endpoint: str, *, page_size: int = MAX_PAGE_SIZE) -> list[dict[str, Any]]:
        resolved_page_size = min(page_size, MAX_PAGE_SIZE)
        rows: list[dict[str, Any]] = []
        page_no = 1
        while page_no <= MAX_PAGE_GUARD:
            page_rows = self._get_rows(
                endpoint,
                params={
                    "numOfRows": str(resolved_page_size),
                    "pageNo": str(page_no),
                },
            )
            rows.extend(page_rows)
            if len(page_rows) < resolved_page_size:
                return rows
            page_no += 1
        raise ExpresswayApiError(f"Expressway API pagination exceeded guard for {endpoint}.")

    def _get_rows(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        api_key = (self._api_key or "").strip()
        if not api_key:
            raise ExpresswayApiError("Expressway API key is not configured.")

        request_params = {
            "key": api_key,
            "type": "json",
            **params,
        }
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.get(f"{self._base_url}/{endpoint}", params=request_params)
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                client.close()

        code = str(payload.get("code", "")).upper()
        message = str(payload.get("message", ""))
        if code and code != "SUCCESS":
            raise ExpresswayApiError(f"Expressway API failed for {endpoint}: {code} {message}")

        raw_rows = payload.get("list", [])
        if raw_rows is None:
            return []
        if isinstance(raw_rows, dict):
            return [raw_rows]
        if isinstance(raw_rows, list):
            return [row for row in raw_rows if isinstance(row, dict)]
        raise ExpresswayApiError(f"Expressway API response for {endpoint} has invalid list.")

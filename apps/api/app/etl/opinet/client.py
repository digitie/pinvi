from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

OPINET_API_BASE_URL = "https://www.opinet.co.kr/api"


class OpiNetApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpiNetFuelSpec:
    provider_fuel_code: str
    provider_fuel_name: str
    fuel_type: str


OPINET_FUEL_SPECS: dict[str, OpiNetFuelSpec] = {
    "B027": OpiNetFuelSpec("B027", "휘발유", "gasoline"),
    "B034": OpiNetFuelSpec("B034", "고급휘발유", "premium_gasoline"),
    "D047": OpiNetFuelSpec("D047", "경유", "diesel"),
    "K015": OpiNetFuelSpec("K015", "LPG", "lpg"),
}


class OpiNetApiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = OPINET_API_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else get_settings().opinet_api_key
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_region_codes(self, *, area_code: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if area_code:
            params["area"] = area_code
        return self._get_oil_rows("areaCode.do", params)

    def fetch_avg_all_prices(self) -> list[dict[str, Any]]:
        return self._get_oil_rows("avgAllPrice.do", {})

    def fetch_lowest_stations(
        self,
        *,
        provider_region_code: str,
        provider_fuel_code: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if provider_fuel_code not in OPINET_FUEL_SPECS:
            raise ValueError(f"Unsupported OpiNet fuel code: {provider_fuel_code}.")
        params = {
            "area": provider_region_code,
            "prodcd": provider_fuel_code,
            "cnt": str(limit),
        }
        return self._get_oil_rows("lowTop10.do", params)

    def _get_oil_rows(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        api_key = (self._api_key or "").strip()
        if not api_key:
            raise OpiNetApiError("OpiNet API key is not configured.")

        request_params = {
            "out": "json",
            "certkey": api_key,
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

        result = payload.get("RESULT")
        if not isinstance(result, dict):
            raise OpiNetApiError(f"OpiNet response for {endpoint} is missing RESULT.")
        oil = result.get("OIL", [])
        if oil is None:
            return []
        if isinstance(oil, dict):
            return [oil]
        if isinstance(oil, list):
            return [row for row in oil if isinstance(row, dict)]
        raise OpiNetApiError(f"OpiNet response for {endpoint} has invalid OIL payload.")

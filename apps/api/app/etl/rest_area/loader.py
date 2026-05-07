from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from kex_openapi import KexClient, Page
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.rest_area import (
    RestAreaRawMaster,
    RestAreaRawOilPrice,
    RestAreaRawService,
    RestAreaServingMaster,
    RestAreaServingOilPrice,
    RestAreaServingService,
)

PROVIDER = "korea_expressway_corporation"
PRICE_UNIT = "KRW_PER_LITER"
MASTER_ENDPOINT = "business/serviceAreaRoute"
OIL_ENDPOINT = "business/curStateStation"
SERVICE_ENDPOINT = "business/conveniServiceArea"
MASTER_SOURCE_API_ID = "0615"
OIL_SOURCE_API_ID = "0312"
SERVICE_SOURCE_API_ID = "0316"
KST = ZoneInfo("Asia/Seoul")
KEX_PAGE_SIZE = 1000
KEX_MAX_PAGE_GUARD = 1000


@dataclass(frozen=True)
class RestAreaMasterLoadResult:
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class RestAreaOilPriceLoadResult:
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int
    fk_mismatch_log_path: str | None


@dataclass(frozen=True)
class RestAreaServiceLoadResult:
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int
    fk_mismatch_log_path: str | None


@dataclass(frozen=True)
class _FuelPriceSpec:
    provider_fuel_code: str
    provider_fuel_name: str
    fuel_type: str


@dataclass(frozen=True)
class _RestAreaMasterLookup:
    codes: set[str]
    name_keys: dict[tuple[str, str | None, str | None], str]


FUEL_PRICE_FIELDS = (
    _FuelPriceSpec("gasolinePrice", "휘발유", "gasoline"),
    _FuelPriceSpec("diselPrice", "경유", "diesel"),
    _FuelPriceSpec("lpgPrice", "LPG", "lpg"),
)


def _collect_kex_rows(fetch_page: Callable[[int], Page[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page_no in range(1, KEX_MAX_PAGE_GUARD + 1):
        page = fetch_page(page_no)
        page_rows = [_kex_item_raw(item) for item in page.items]
        rows.extend(page_rows)
        if page.total_count is not None and len(rows) >= page.total_count:
            return rows
        if len(page_rows) < KEX_PAGE_SIZE:
            return rows
    raise RuntimeError("pykex pagination exceeded guard for rest area dataset.")


def _kex_item_raw(item: object) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    raw = getattr(item, "raw", None)
    if isinstance(raw, dict):
        return dict(raw)
    raise TypeError(f"pykex rest area item does not expose raw payload: {type(item)!r}")


def load_rest_area_master(
    session: Session,
    client: KexClient,
    *,
    collected_at: datetime | None = None,
) -> RestAreaMasterLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    snapshot_date = resolved_collected_at.date()
    rows = _collect_kex_rows(
        lambda page_no: client.restarea.route_facilities(
            num_of_rows=KEX_PAGE_SIZE,
            page_no=page_no,
        )
    )
    serving_by_code: dict[str, RestAreaServingMaster] = {}
    raw_count = 0
    serving_count = 0
    skipped = 0

    session.execute(update(RestAreaServingMaster).values(is_active=False))
    for row in rows:
        source_key = _source_key(row)
        session.add(
            RestAreaRawMaster(
                provider=PROVIDER,
                endpoint=MASTER_ENDPOINT,
                source_api_id=MASTER_SOURCE_API_ID,
                source_key=source_key,
                source_snapshot_date=snapshot_date,
                raw_payload=dict(row),
                response_hash=_hash_payload(row),
                collected_at=resolved_collected_at,
            )
        )
        raw_count += 1

        svar_cd = _optional_text(row, "serviceAreaCode2")
        name = _optional_text(row, "serviceAreaName")
        if not svar_cd or not name:
            skipped += 1
            continue
        serving = _upsert_master(
            session,
            row=row,
            svar_cd=svar_cd,
            name=name,
            snapshot_date=snapshot_date,
            collected_at=resolved_collected_at,
            existing=serving_by_code.get(svar_cd),
        )
        if svar_cd not in serving_by_code:
            serving_count += 1
        serving_by_code[svar_cd] = serving

    session.flush()
    return RestAreaMasterLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped,
    )


def load_rest_area_oil_prices(
    session: Session,
    client: KexClient,
    *,
    collected_at: datetime | None = None,
    fk_mismatch_log_dir: Path | str | None = None,
    run_id: str | None = None,
) -> RestAreaOilPriceLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    snapshot_date = resolved_collected_at.date()
    rows = _collect_kex_rows(
        lambda page_no: client.restarea.fuel_prices(
            num_of_rows=KEX_PAGE_SIZE,
            page_no=page_no,
        )
    )
    master_lookup = _load_master_lookup(session)
    raw_count = 0
    serving_count = 0
    skipped = 0
    mismatch_logger = _FkMismatchLogger(
        dataset_key="rest_area_oil_price",
        endpoint=OIL_ENDPOINT,
        log_dir=fk_mismatch_log_dir,
        run_id=run_id,
        collected_at=resolved_collected_at,
    )

    for row in rows:
        source_key = _source_key(row)
        service_area_code2 = _optional_text(row, "serviceAreaCode2")
        session.add(
            RestAreaRawOilPrice(
                provider=PROVIDER,
                endpoint=OIL_ENDPOINT,
                source_api_id=OIL_SOURCE_API_ID,
                source_key=source_key,
                service_area_code2=service_area_code2,
                source_snapshot_date=snapshot_date,
                raw_payload=dict(row),
                response_hash=_hash_payload(row),
                collected_at=resolved_collected_at,
            )
        )
        raw_count += 1

        svar_cd = _resolve_master_svar_cd(row, service_area_code2, master_lookup)
        if svar_cd is None:
            skipped += 1
            mismatch_logger.write(row=row, reason="missing_rest_area_master_fk")
            continue

        for fuel_spec in FUEL_PRICE_FIELDS:
            price = _parse_price_krw(row.get(fuel_spec.provider_fuel_code))
            if price is None:
                continue
            _upsert_oil_price(
                session,
                row=row,
                svar_cd=svar_cd,
                fuel_spec=fuel_spec,
                price=price,
                snapshot_date=snapshot_date,
                collected_at=resolved_collected_at,
            )
            serving_count += 1

    session.flush()
    return RestAreaOilPriceLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped,
        fk_mismatch_log_path=mismatch_logger.path_as_string(),
    )


def load_rest_area_services(
    session: Session,
    client: KexClient,
    *,
    collected_at: datetime | None = None,
    fk_mismatch_log_dir: Path | str | None = None,
    run_id: str | None = None,
) -> RestAreaServiceLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    snapshot_date = resolved_collected_at.date()
    rows = _collect_kex_rows(
        lambda page_no: client.restarea.convenience_facilities(
            num_of_rows=KEX_PAGE_SIZE,
            page_no=page_no,
        )
    )
    master_lookup = _load_master_lookup(session)
    raw_count = 0
    serving_count = 0
    skipped = 0
    mismatch_logger = _FkMismatchLogger(
        dataset_key="rest_area_svcs",
        endpoint=SERVICE_ENDPOINT,
        log_dir=fk_mismatch_log_dir,
        run_id=run_id,
        collected_at=resolved_collected_at,
    )

    session.execute(
        delete(RestAreaServingService).where(
            RestAreaServingService.source_snapshot_date == snapshot_date
        )
    )
    for row in rows:
        source_key = _source_key(row)
        service_area_code2 = _optional_text(row, "serviceAreaCode2")
        session.add(
            RestAreaRawService(
                provider=PROVIDER,
                endpoint=SERVICE_ENDPOINT,
                source_api_id=SERVICE_SOURCE_API_ID,
                source_key=source_key,
                service_area_code2=service_area_code2,
                source_snapshot_date=snapshot_date,
                raw_payload=dict(row),
                response_hash=_hash_payload(row),
                collected_at=resolved_collected_at,
            )
        )
        raw_count += 1

        svar_cd = _resolve_master_svar_cd(row, service_area_code2, master_lookup)
        if svar_cd is None:
            skipped += 1
            mismatch_logger.write(row=row, reason="missing_rest_area_master_fk")
            continue

        service_names = _split_services(_optional_text(row, "convenience"))
        for service_name in service_names:
            provider_service_code = _service_code_from_name(service_name)
            session.add(
                RestAreaServingService(
                    svar_cd=svar_cd,
                    provider_service_area_code=_optional_text(row, "serviceAreaCode"),
                    route_code=_optional_text(row, "routeCode"),
                    route_name=_optional_text(row, "routeName"),
                    direction=_optional_text(row, "direction"),
                    provider_service_code=provider_service_code,
                    provider_service_name=service_name,
                    display_name=service_name,
                    available=True,
                    quantity=None,
                    status=None,
                    raw_payload=dict(row),
                    source_snapshot_date=snapshot_date,
                    collected_at=resolved_collected_at,
                )
            )
            serving_count += 1

    session.flush()
    return RestAreaServiceLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped,
        fk_mismatch_log_path=mismatch_logger.path_as_string(),
    )


class _FkMismatchLogger:
    def __init__(
        self,
        *,
        dataset_key: str,
        endpoint: str,
        log_dir: Path | str | None,
        run_id: str | None,
        collected_at: datetime,
    ) -> None:
        self._dataset_key = dataset_key
        self._endpoint = endpoint
        self._collected_at = collected_at
        if log_dir is None:
            self._path: Path | None = None
            return
        resolved_run_id = _safe_file_part(run_id or collected_at.strftime("%Y%m%dT%H%M%S"))
        base_dir = Path(log_dir) / dataset_key
        base_dir.mkdir(parents=True, exist_ok=True)
        self._path = base_dir / f"{resolved_run_id}.jsonl"

    def write(self, *, row: dict[str, Any], reason: str) -> None:
        if self._path is None:
            return
        payload = {
            "dataset": self._dataset_key,
            "source_endpoint": self._endpoint,
            "source_key": _source_key(row),
            "serviceAreaCode2": _optional_text(row, "serviceAreaCode2"),
            "collected_at": self._collected_at.isoformat(),
            "reason": reason,
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def path_as_string(self) -> str | None:
        return str(self._path) if self._path is not None and self._path.exists() else None


def _upsert_master(
    session: Session,
    *,
    row: dict[str, Any],
    svar_cd: str,
    name: str,
    snapshot_date: date,
    collected_at: datetime,
    existing: RestAreaServingMaster | None = None,
) -> RestAreaServingMaster:
    existing = existing or session.get(RestAreaServingMaster, svar_cd)
    values = {
        "provider_service_area_code": _optional_text(row, "serviceAreaCode"),
        "name": name,
        "direction": _optional_text(row, "direction"),
        "route_code": _optional_text(row, "routeCode"),
        "route_name": _optional_text(row, "routeName"),
        "address": _optional_text(row, "svarAddr"),
        "brand": _optional_text(row, "brand"),
        "convenience_raw": _optional_text(row, "convenience"),
        "phone": _optional_text(row, "telNo"),
        "maintenance_yn": _optional_text(row, "maintenanceYn"),
        "truck_sa_yn": _optional_text(row, "truckSaYn"),
        "representative_food": _optional_text(row, "batchMenu"),
        "lon": _optional_decimal(row.get("xValue")),
        "lat": _optional_decimal(row.get("yValue")),
        "raw_payload": dict(row),
        "source_snapshot_date": snapshot_date,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = RestAreaServingMaster(svar_cd=svar_cd, **values)
        session.add(existing)
    else:
        if existing.source_snapshot_date == snapshot_date and existing.collected_at == collected_at:
            values = _merge_duplicate_master_values(existing, values, row)
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _merge_duplicate_master_values(
    existing: RestAreaServingMaster,
    values: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(values)
    for key in (
        "provider_service_area_code",
        "name",
        "direction",
        "route_code",
        "route_name",
        "address",
        "brand",
        "convenience_raw",
        "phone",
        "maintenance_yn",
        "truck_sa_yn",
        "representative_food",
    ):
        merged[key] = _merge_text_values(getattr(existing, key), values.get(key))

    merged["lon"] = existing.lon or values.get("lon")
    merged["lat"] = existing.lat or values.get("lat")
    merged["raw_payload"] = _merge_raw_payload(existing.raw_payload, row)
    return merged


def _merge_text_values(left: Any, right: Any) -> str | None:
    parts: list[str] = []
    for value in (left, right):
        text = _optional_text_from_value(value)
        if text and text not in parts:
            parts.append(text)
    return "|".join(parts) if parts else None


def _merge_raw_payload(existing_payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    existing_rows = existing_payload.get("merged_rows")
    if isinstance(existing_rows, list):
        rows = [*existing_rows]
    else:
        rows = [existing_payload]
    rows.append(dict(row))
    return {"merged_rows": rows}


def _upsert_oil_price(
    session: Session,
    *,
    row: dict[str, Any],
    svar_cd: str,
    fuel_spec: _FuelPriceSpec,
    price: int,
    snapshot_date: date,
    collected_at: datetime,
) -> RestAreaServingOilPrice:
    existing = session.scalar(
        select(RestAreaServingOilPrice)
        .where(RestAreaServingOilPrice.svar_cd == svar_cd)
        .where(RestAreaServingOilPrice.provider_fuel_code == fuel_spec.provider_fuel_code)
        .where(RestAreaServingOilPrice.collected_at == collected_at)
    )
    values = {
        "provider_service_area_code": _optional_text(row, "serviceAreaCode"),
        "station_name": _optional_text(row, "serviceAreaName"),
        "route_code": _optional_text(row, "routeCode"),
        "route_name": _optional_text(row, "routeName"),
        "direction": _optional_text(row, "direction"),
        "oil_company": _optional_text(row, "oilCompany"),
        "lpg_yn": _optional_text(row, "lpgYn"),
        "provider_fuel_name": fuel_spec.provider_fuel_name,
        "fuel_type": fuel_spec.fuel_type,
        "price_per_liter_krw": price,
        "price_at": collected_at,
        "price_time_source": "collected_at",
        "price_unit": PRICE_UNIT,
        "raw_payload": dict(row),
        "collected_at": collected_at,
    }
    if existing is None:
        existing = RestAreaServingOilPrice(
            svar_cd=svar_cd,
            provider_fuel_code=fuel_spec.provider_fuel_code,
            source_snapshot_date=snapshot_date,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _load_master_lookup(session: Session) -> _RestAreaMasterLookup:
    rows = session.execute(
        select(
            RestAreaServingMaster.svar_cd,
            RestAreaServingMaster.name,
            RestAreaServingMaster.route_name,
            RestAreaServingMaster.direction,
        ).where(RestAreaServingMaster.is_active.is_(True))
    ).all()
    codes: set[str] = set()
    name_keys: dict[tuple[str, str | None, str | None], str] = {}
    ambiguous_keys: set[tuple[str, str | None, str | None]] = set()
    for svar_cd, name, route_name, direction in rows:
        codes.add(svar_cd)
        key = _rest_area_match_key(name, route_name, direction)
        if key is None or key in ambiguous_keys:
            continue
        existing = name_keys.get(key)
        if existing is not None and existing != svar_cd:
            name_keys.pop(key, None)
            ambiguous_keys.add(key)
            continue
        name_keys[key] = svar_cd
    return _RestAreaMasterLookup(codes=codes, name_keys=name_keys)


def _resolve_master_svar_cd(
    row: dict[str, Any],
    service_area_code2: str | None,
    lookup: _RestAreaMasterLookup,
) -> str | None:
    if service_area_code2 and service_area_code2 in lookup.codes:
        return service_area_code2
    key = _rest_area_match_key(
        _optional_text(row, "serviceAreaName"),
        _optional_text(row, "routeName"),
        _optional_text(row, "direction"),
    )
    if key is None:
        return None
    return lookup.name_keys.get(key)


def _rest_area_match_key(
    name: str | None,
    route_name: str | None,
    direction: str | None,
) -> tuple[str, str | None, str | None] | None:
    normalized_name = _normalize_rest_area_name(name)
    if normalized_name is None:
        return None
    return (
        normalized_name,
        _normalize_match_text(route_name),
        _normalize_match_text(direction),
    )


def _normalize_rest_area_name(value: str | None) -> str | None:
    normalized = _normalize_match_text(value)
    if normalized is None:
        return None
    for suffix in ("휴게소", "주유소", "LPG충전소", "충전소"):
        normalized = normalized.replace(suffix, "")
    return normalized or None


def _normalize_match_text(value: str | None) -> str | None:
    text = _optional_text_from_value(value)
    if text is None:
        return None
    return re.sub(r"\s+", "", text)


def _source_key(row: dict[str, Any]) -> str:
    for key in ("serviceAreaCode2", "serviceAreaCode", "serviceAreaName"):
        value = _optional_text(row, key)
        if value:
            return value
    return _hash_payload(row)[:24]


def _split_services(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _service_code_from_name(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.strip().lower())
    return re.sub(r"[^0-9a-zA-Z가-힣_]+", "_", normalized).strip("_") or _hash_text(value)[:16]


def _parse_price_krw(value: Any) -> int | None:
    text = _optional_text_from_value(value)
    if text is None or text in {"-", "X", "x"}:
        return None
    numeric = re.sub(r"[^0-9]", "", text)
    if not numeric:
        return None
    return int(numeric)


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    return _optional_text_from_value(row.get(key))


def _optional_text_from_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_decimal(value: Any) -> Decimal | None:
    text = _optional_text_from_value(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _resolve_collected_at(collected_at: datetime | None) -> datetime:
    if collected_at is None:
        return datetime.now(KST)
    if collected_at.tzinfo is None:
        return collected_at.replace(tzinfo=KST)
    return collected_at


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_file_part(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", value)

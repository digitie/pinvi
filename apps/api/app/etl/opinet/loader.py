from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.etl.juso.legal_dong_loader import _derive_sido_code, _derive_sigungu_code
from app.etl.opinet.client import OPINET_FUEL_SPECS, OpiNetApiClient, OpiNetFuelSpec
from app.models.address import AddressCodeStandard
from app.models.fuel import (
    FuelRawAvgPrice,
    FuelRawLowestStation,
    FuelRawOpiNetRegionCode,
    FuelRegionLegalDongMapping,
    FuelServingAvgPrice,
    FuelServingLowestStation,
    FuelServingOpiNetRegionCode,
)

KST = ZoneInfo("Asia/Seoul")
PRICE_UNIT = "KRW_PER_LITER"


@dataclass(frozen=True)
class OpiNetRegionCodeLoadResult:
    raw_row_count: int
    serving_row_count: int
    mapped_row_count: int
    unmatched_row_count: int


@dataclass(frozen=True)
class OpiNetAvgPriceLoadResult:
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class OpiNetLowestStationLoadResult:
    raw_row_count: int
    serving_row_count: int
    requested_region_count: int
    skipped_row_count: int


def load_opinet_region_codes(
    session: Session,
    client: OpiNetApiClient,
    *,
    collected_at: datetime | None = None,
) -> OpiNetRegionCodeLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    raw_rows: list[FuelRawOpiNetRegionCode] = []
    region_payloads: list[dict[str, Any]] = []

    sido_rows = client.fetch_region_codes()
    for sido_row in sido_rows:
        sido_code = _required_text(sido_row, "AREA_CD")
        raw_rows.append(
            _build_region_raw_row(
                row=sido_row,
                request_area_code=None,
                region_level="sido",
                parent_provider_region_code=None,
                collected_at=resolved_collected_at,
            )
        )
        region_payloads.append(
            {
                "row": sido_row,
                "region_level": "sido",
                "parent_provider_region_code": None,
            }
        )

        for sigungu_row in client.fetch_region_codes(area_code=sido_code):
            raw_rows.append(
                _build_region_raw_row(
                    row=sigungu_row,
                    request_area_code=sido_code,
                    region_level="sigungu",
                    parent_provider_region_code=sido_code,
                    collected_at=resolved_collected_at,
                )
            )
            region_payloads.append(
                {
                    "row": sigungu_row,
                    "region_level": "sigungu",
                    "parent_provider_region_code": sido_code,
                }
            )

    session.add_all(raw_rows)
    mappings = _build_region_mappings(session, region_payloads)
    provider_codes = [_required_text(payload["row"], "AREA_CD") for payload in region_payloads]
    if provider_codes:
        session.execute(
            delete(FuelRegionLegalDongMapping).where(
                FuelRegionLegalDongMapping.provider_region_code.in_(provider_codes)
            )
        )

    serving_rows = []
    mapping_rows = []
    for payload in region_payloads:
        row = payload["row"]
        provider_region_code = _required_text(row, "AREA_CD")
        provider_region_name = _required_text(row, "AREA_NM")
        region_level = payload["region_level"]
        parent_provider_region_code = payload["parent_provider_region_code"]
        mapping = mappings[provider_region_code]
        serving = _upsert_serving_region_code(
            session,
            provider_region_code=provider_region_code,
            provider_region_name=provider_region_name,
            region_level=region_level,
            parent_provider_region_code=parent_provider_region_code,
            legal_dong_code=mapping.legal_dong_code,
            mapping_source=mapping.mapping_source,
            mapping_status=mapping.mapping_status,
            raw_payload=row,
            collected_at=resolved_collected_at,
        )
        serving_rows.append(serving)
        mapping_rows.append(
            FuelRegionLegalDongMapping(
                provider_region_code=provider_region_code,
                provider_region_name=provider_region_name,
                region_level=region_level,
                legal_dong_code=mapping.legal_dong_code,
                mapping_source=mapping.mapping_source,
                mapping_status=mapping.mapping_status,
                confidence=mapping.confidence,
                notes=mapping.notes,
            )
        )

    # SQLAlchemy cannot infer ordering between these tables without ORM relationships.
    # Flush serving rows first so the mapping FK is satisfied on PostgreSQL.
    session.flush()
    session.add_all(mapping_rows)
    session.flush()
    mapped_row_count = sum(1 for mapping in mappings.values() if mapping.legal_dong_code)
    return OpiNetRegionCodeLoadResult(
        raw_row_count=len(raw_rows),
        serving_row_count=len(serving_rows),
        mapped_row_count=mapped_row_count,
        unmatched_row_count=len(region_payloads) - mapped_row_count,
    )


def load_opinet_avg_prices(
    session: Session,
    client: OpiNetApiClient,
    *,
    collected_at: datetime | None = None,
) -> OpiNetAvgPriceLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    rows = client.fetch_avg_all_prices()
    skipped = 0
    raw_count = 0
    serving_count = 0
    for row in rows:
        fuel_spec = OPINET_FUEL_SPECS.get(_required_text(row, "PRODCD"))
        if fuel_spec is None:
            skipped += 1
            continue

        trade_date = _optional_text(row, "TRADE_DT")
        timestamp = _parse_trade_date_timestamp(trade_date, resolved_collected_at)
        serving_trade_date = trade_date or timestamp.astimezone(KST).strftime("%Y%m%d")
        price = _decimal_from_value(_required_value(row, "PRICE"), "PRICE")
        diff = _optional_decimal(row.get("DIFF"))
        raw_payload = dict(row)
        session.add(
            FuelRawAvgPrice(
                endpoint="avgAllPrice.do",
                provider_region_code=None,
                legal_dong_code=None,
                trade_date=trade_date,
                timestamp=timestamp,
                provider_fuel_code=fuel_spec.provider_fuel_code,
                provider_fuel_name=fuel_spec.provider_fuel_name,
                fuel_type=fuel_spec.fuel_type,
                price=price,
                diff=diff,
                price_unit=PRICE_UNIT,
                raw_payload=raw_payload,
                response_hash=_hash_payload(raw_payload),
                collected_at=resolved_collected_at,
            )
        )
        raw_count += 1
        _upsert_avg_price(
            session,
            region_key="national",
            provider_region_code=None,
            legal_dong_code=None,
            trade_date=serving_trade_date,
            timestamp=timestamp,
            fuel_spec=fuel_spec,
            price=price,
            diff=diff,
            raw_payload=raw_payload,
            collected_at=resolved_collected_at,
        )
        serving_count += 1

    session.flush()
    return OpiNetAvgPriceLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped,
    )


def load_opinet_lowest_stations(
    session: Session,
    client: OpiNetApiClient,
    *,
    provider_region_codes: list[str],
    provider_fuel_codes: list[str] | None = None,
    collected_at: datetime | None = None,
    limit: int = 20,
) -> OpiNetLowestStationLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    fuel_codes = provider_fuel_codes or list(OPINET_FUEL_SPECS)
    skipped = 0
    raw_count = 0
    serving_count = 0

    region_mapping = _load_region_mapping(session, provider_region_codes)
    for provider_region_code in provider_region_codes:
        legal_dong_code = region_mapping.get(provider_region_code)
        for provider_fuel_code in fuel_codes:
            fuel_spec = OPINET_FUEL_SPECS.get(provider_fuel_code)
            if fuel_spec is None:
                skipped += 1
                continue
            rows = client.fetch_lowest_stations(
                provider_region_code=provider_region_code,
                provider_fuel_code=provider_fuel_code,
                limit=limit,
            )
            for row in rows:
                station_id = _resolve_station_id(row)
                price = _decimal_from_value(_required_value(row, "PRICE"), "PRICE")
                timestamp = resolved_collected_at
                raw_payload = dict(row)
                raw = FuelRawLowestStation(
                    endpoint="lowTop10.do",
                    provider_region_code=provider_region_code,
                    legal_dong_code=legal_dong_code,
                    timestamp=timestamp,
                    provider_fuel_code=fuel_spec.provider_fuel_code,
                    provider_fuel_name=fuel_spec.provider_fuel_name,
                    fuel_type=fuel_spec.fuel_type,
                    station_id=station_id,
                    station_name=_resolve_station_name(row),
                    price=price,
                    poll_div_code=_optional_text(row, "POLL_DIV_CD"),
                    van_address=_optional_text(row, "VAN_ADR"),
                    road_address=_optional_text(row, "NEW_ADR"),
                    gis_x=_optional_decimal(row.get("GIS_X_COOR")),
                    gis_y=_optional_decimal(row.get("GIS_Y_COOR")),
                    price_unit=PRICE_UNIT,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
                session.add(raw)
                raw_count += 1
                _upsert_lowest_station(
                    session,
                    provider_region_code=provider_region_code,
                    legal_dong_code=legal_dong_code,
                    timestamp=timestamp,
                    fuel_spec=fuel_spec,
                    station_id=station_id,
                    station_name=raw.station_name,
                    price=price,
                    poll_div_code=raw.poll_div_code,
                    van_address=raw.van_address,
                    road_address=raw.road_address,
                    gis_x=raw.gis_x,
                    gis_y=raw.gis_y,
                    raw_payload=raw_payload,
                    collected_at=resolved_collected_at,
                )
                serving_count += 1

    session.flush()
    return OpiNetLowestStationLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        requested_region_count=len(provider_region_codes),
        skipped_row_count=skipped,
    )


@dataclass(frozen=True)
class _ResolvedMapping:
    legal_dong_code: str | None
    mapping_source: str
    mapping_status: str
    confidence: int
    notes: str | None = None


def _build_region_mappings(
    session: Session,
    region_payloads: list[dict[str, Any]],
) -> dict[str, _ResolvedMapping]:
    active_codes = list(
        session.scalars(
            select(AddressCodeStandard).where(AddressCodeStandard.is_active.is_(True))
        ).all()
    )
    sido_by_name = _build_code_name_index(
        code for code in active_codes if code.code_level == "sido"
    )
    sigungu_by_sido_name: dict[tuple[str, str], list[AddressCodeStandard]] = {}
    for code in active_codes:
        if code.code_level != "sigungu":
            continue
        sigungu_by_sido_name.setdefault(
            (code.sido_code, _normalize_region_name(code.sigungu_name or "")),
            [],
        ).append(code)

    mappings: dict[str, _ResolvedMapping] = {}
    for payload in region_payloads:
        row = payload["row"]
        provider_region_code = _required_text(row, "AREA_CD")
        provider_region_name = _required_text(row, "AREA_NM")
        region_level = payload["region_level"]
        parent_provider_region_code = payload["parent_provider_region_code"]
        if region_level == "sido":
            mappings[provider_region_code] = _resolve_sido_mapping(
                provider_region_name,
                sido_by_name,
            )
            continue

        parent_mapping = mappings.get(parent_provider_region_code or "")
        parent_code = parent_mapping.legal_dong_code if parent_mapping else None
        candidates = (
            sigungu_by_sido_name.get(
                (parent_code, _normalize_region_name(provider_region_name)),
                [],
            )
            if parent_code
            else []
        )
        mappings[provider_region_code] = _select_mapping_candidate(
            candidates,
            mapping_source="name_sigungu_parent",
        )
    return mappings


def _resolve_sido_mapping(
    provider_region_name: str,
    sido_by_name: dict[str, list[AddressCodeStandard]],
) -> _ResolvedMapping:
    candidates = sido_by_name.get(_normalize_region_name(provider_region_name), [])
    return _select_mapping_candidate(candidates, mapping_source="name_sido")


def _select_mapping_candidate(
    candidates: list[AddressCodeStandard],
    *,
    mapping_source: str,
) -> _ResolvedMapping:
    if len(candidates) == 1:
        return _ResolvedMapping(
            legal_dong_code=candidates[0].legal_dong_code,
            mapping_source=mapping_source,
            mapping_status="matched",
            confidence=100,
        )
    if len(candidates) > 1:
        return _ResolvedMapping(
            legal_dong_code=None,
            mapping_source=mapping_source,
            mapping_status="ambiguous",
            confidence=0,
            notes="OpiNet 지역명과 주소 DB 후보가 2개 이상이다.",
        )
    return _ResolvedMapping(
        legal_dong_code=None,
        mapping_source=mapping_source,
        mapping_status="unmatched",
        confidence=0,
    )


def _build_code_name_index(
    codes: Iterable[AddressCodeStandard],
) -> dict[str, list[AddressCodeStandard]]:
    result: dict[str, dict[str, AddressCodeStandard]] = {}
    for code in codes:
        for name in (
            _normalize_region_name(code.code_name),
            _normalize_region_name(code.sido_name or ""),
            _normalize_region_name(code.full_legal_dong_name),
        ):
            if not name:
                continue
            result.setdefault(name, {})[code.legal_dong_code] = code
    return {name: list(values.values()) for name, values in result.items()}


def _normalize_region_name(value: str) -> str:
    normalized = value.replace(" ", "")
    aliases = {
        "서울": "서울특별시",
        "부산": "부산광역시",
        "대구": "대구광역시",
        "인천": "인천광역시",
        "광주": "광주광역시",
        "대전": "대전광역시",
        "울산": "울산광역시",
        "세종": "세종특별자치시",
        "경기": "경기도",
        "강원": "강원특별자치도",
        "충북": "충청북도",
        "충남": "충청남도",
        "전북": "전북특별자치도",
        "전남": "전라남도",
        "경북": "경상북도",
        "경남": "경상남도",
        "제주": "제주특별자치도",
    }
    return aliases.get(normalized, normalized)


def _upsert_serving_region_code(
    session: Session,
    *,
    provider_region_code: str,
    provider_region_name: str,
    region_level: str,
    parent_provider_region_code: str | None,
    legal_dong_code: str | None,
    mapping_source: str,
    mapping_status: str,
    raw_payload: dict[str, Any],
    collected_at: datetime,
) -> FuelServingOpiNetRegionCode:
    existing = session.get(FuelServingOpiNetRegionCode, provider_region_code)
    values = {
        "provider_region_name": provider_region_name,
        "region_level": region_level,
        "parent_provider_region_code": parent_provider_region_code,
        "address_code_standard_code": legal_dong_code,
        "mapping_status": mapping_status,
        "mapping_source": mapping_source,
        "raw_payload": raw_payload,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = FuelServingOpiNetRegionCode(
            provider_region_code=provider_region_code,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_avg_price(
    session: Session,
    *,
    region_key: str,
    provider_region_code: str | None,
    legal_dong_code: str | None,
    trade_date: str | None,
    timestamp: datetime,
    fuel_spec: OpiNetFuelSpec,
    price: Decimal,
    diff: Decimal | None,
    raw_payload: dict[str, Any],
    collected_at: datetime,
) -> FuelServingAvgPrice:
    existing = session.scalar(
        select(FuelServingAvgPrice)
        .where(FuelServingAvgPrice.region_key == region_key)
        .where(FuelServingAvgPrice.trade_date == trade_date)
        .where(FuelServingAvgPrice.fuel_type == fuel_spec.fuel_type)
    )
    values = {
        "provider_region_code": provider_region_code,
        "legal_dong_code": legal_dong_code,
        "timestamp": timestamp,
        "provider_fuel_code": fuel_spec.provider_fuel_code,
        "provider_fuel_name": fuel_spec.provider_fuel_name,
        "price": price,
        "diff": diff,
        "price_unit": PRICE_UNIT,
        "raw_payload": raw_payload,
        "collected_at": collected_at,
    }
    if existing is None:
        existing = FuelServingAvgPrice(
            region_key=region_key,
            trade_date=trade_date,
            fuel_type=fuel_spec.fuel_type,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_lowest_station(
    session: Session,
    *,
    provider_region_code: str,
    legal_dong_code: str | None,
    timestamp: datetime,
    fuel_spec: OpiNetFuelSpec,
    station_id: str,
    station_name: str,
    price: Decimal,
    poll_div_code: str | None,
    van_address: str | None,
    road_address: str | None,
    gis_x: Decimal | None,
    gis_y: Decimal | None,
    raw_payload: dict[str, Any],
    collected_at: datetime,
) -> FuelServingLowestStation:
    existing = session.scalar(
        select(FuelServingLowestStation)
        .where(FuelServingLowestStation.provider_region_code == provider_region_code)
        .where(FuelServingLowestStation.fuel_type == fuel_spec.fuel_type)
        .where(FuelServingLowestStation.station_id == station_id)
        .where(FuelServingLowestStation.timestamp == timestamp)
    )
    values = {
        "legal_dong_code": legal_dong_code,
        "provider_fuel_code": fuel_spec.provider_fuel_code,
        "provider_fuel_name": fuel_spec.provider_fuel_name,
        "station_name": station_name,
        "price": price,
        "poll_div_code": poll_div_code,
        "van_address": van_address,
        "road_address": road_address,
        "gis_x": gis_x,
        "gis_y": gis_y,
        "price_unit": PRICE_UNIT,
        "raw_payload": raw_payload,
        "collected_at": collected_at,
    }
    if existing is None:
        existing = FuelServingLowestStation(
            provider_region_code=provider_region_code,
            fuel_type=fuel_spec.fuel_type,
            station_id=station_id,
            timestamp=timestamp,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _build_region_raw_row(
    *,
    row: dict[str, Any],
    request_area_code: str | None,
    region_level: str,
    parent_provider_region_code: str | None,
    collected_at: datetime,
) -> FuelRawOpiNetRegionCode:
    raw_payload = dict(row)
    return FuelRawOpiNetRegionCode(
        endpoint="areaCode.do",
        request_area_code=request_area_code,
        provider_region_code=_required_text(row, "AREA_CD"),
        provider_region_name=_required_text(row, "AREA_NM"),
        region_level=region_level,
        parent_provider_region_code=parent_provider_region_code,
        raw_payload=raw_payload,
        response_hash=_hash_payload(raw_payload),
        collected_at=collected_at,
    )


def _load_region_mapping(
    session: Session,
    provider_region_codes: list[str],
) -> dict[str, str | None]:
    rows = session.scalars(
        select(FuelServingOpiNetRegionCode).where(
            FuelServingOpiNetRegionCode.provider_region_code.in_(provider_region_codes)
        )
    )
    return {row.provider_region_code: row.address_code_standard_code for row in rows}


def _resolve_station_id(row: dict[str, Any]) -> str:
    for key in ("UNI_ID", "OS_NM", "VAN_ADR", "NEW_ADR"):
        value = _optional_text(row, key)
        if value:
            return value
    return _hash_payload(row)[:24]


def _resolve_station_name(row: dict[str, Any]) -> str:
    return _optional_text(row, "OS_NM") or _resolve_station_id(row)


def _parse_trade_date_timestamp(
    trade_date: str | None,
    fallback: datetime,
) -> datetime:
    if not trade_date:
        return fallback
    try:
        date_value = datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        return fallback
    return datetime.combine(date_value, time.min, tzinfo=KST)


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


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _required_value(row, key)
    return str(value).strip()


def _required_value(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"OpiNet row is missing required field {key}.")
    return value


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal_from_value(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"OpiNet field {field_name} must be decimal-compatible.") from exc


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _decimal_from_value(value, "optional_decimal")


def legal_dong_to_opinet_mapping_candidates(legal_dong_code: str) -> list[str]:
    return [
        legal_dong_code,
        _derive_sigungu_code(legal_dong_code),
        _derive_sido_code(legal_dong_code),
    ]


def find_opinet_region_code_for_legal_dong(
    session: Session,
    legal_dong_code: str,
) -> str | None:
    candidates = legal_dong_to_opinet_mapping_candidates(legal_dong_code)
    rows = list(
        session.scalars(
            select(FuelServingOpiNetRegionCode).where(
                FuelServingOpiNetRegionCode.address_code_standard_code.in_(candidates)
            )
        ).all()
    )
    priority = {code: index for index, code in enumerate(candidates)}
    rows.sort(key=lambda row: priority.get(row.address_code_standard_code or "", 99))
    return rows[0].provider_region_code if rows else None


def list_opinet_sigungu_region_codes_for_periodic_collection(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(FuelServingOpiNetRegionCode.provider_region_code)
            .where(FuelServingOpiNetRegionCode.region_level == "sigungu")
            .where(FuelServingOpiNetRegionCode.mapping_status == "matched")
            .where(FuelServingOpiNetRegionCode.address_code_standard_code.is_not(None))
            .where(FuelServingOpiNetRegionCode.is_active.is_(True))
            .order_by(FuelServingOpiNetRegionCode.provider_region_code)
        ).all()
    )

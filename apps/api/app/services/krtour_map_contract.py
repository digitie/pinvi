from __future__ import annotations

from decimal import Decimal
from typing import Any

from krtour_map import (
    Address,
    Coordinate,
    Feature,
    FeatureStatus,
    FeatureUrls,
    RawDataRef,
)
from krtour_map import (
    ProviderSyncState as KrtourProviderSyncState,
)
from krtour_map import (
    SourceRecord as KrtourSourceRecord,
)

from app.models.etl import ProviderSyncState
from app.models.place import MapFeature, SourceRecord


class KrtourMapContractError(ValueError):
    """Raised when a TripMate ORM row cannot be exported to the map-library contract."""


def map_feature_to_krtour_feature(
    feature: MapFeature,
    *,
    raw_refs: list[RawDataRef] | None = None,
) -> Feature:
    if feature.longitude is None or feature.latitude is None:
        raise KrtourMapContractError("MapFeature needs longitude and latitude for export.")

    extra = feature.extra or {}
    detail = _without_none(
        {
            "tripmate_feature_id": str(feature.id) if feature.id is not None else None,
            "subtitle": feature.subtitle,
            "summary": feature.summary,
            "description": feature.description,
            "category_code": feature.category_code,
            "category_name": feature.category_name,
            "extra": extra or None,
        }
    )

    return Feature(
        feature_id=feature.public_id,
        kind=feature.feature_type,
        name=feature.display_name or feature.name,
        coord=Coordinate(
            lat=_decimal_to_float(feature.latitude, field_name="latitude"),
            lon=_decimal_to_float(feature.longitude, field_name="longitude"),
        ),
        address=Address.from_mapping(
            {
                "road_address": feature.road_address,
                "jibun_address": feature.jibun_address,
                "legal_dong_code": feature.legal_dong_code,
                "sido_code": feature.sido_code,
                "sigungu_code": feature.sigungu_code,
                "road_name_code": feature.road_name_code,
                "road_name_address_code": feature.road_address_management_no,
            }
        )
        or Address(),
        category=feature.category_name or feature.category_code or feature.feature_type,
        urls=_feature_urls(homepage=feature.website_url),
        marker_icon=str(extra.get("marker_icon") or feature.feature_type),
        marker_color=str(extra.get("marker_color") or "#2f6fed"),
        parent_feature_id=str(feature.parent_feature_id) if feature.parent_feature_id else None,
        detail=detail or None,
        raw_refs=raw_refs or [],
        status=_map_feature_status(feature.status),
        created_at=feature.first_seen_at,
        updated_at=feature.last_seen_at or feature.first_seen_at,
    )


def source_record_to_krtour_source(record: SourceRecord) -> KrtourSourceRecord:
    return KrtourSourceRecord(
        provider=record.provider,
        dataset_key=record.dataset_key,
        source_entity_type=record.source_entity_type,
        source_entity_id=record.source_entity_id,
        source_version=record.source_version,
        raw_name=record.raw_name,
        raw_address=record.raw_address,
        raw_longitude=record.raw_longitude,
        raw_latitude=record.raw_latitude,
        raw_data=record.raw_data,
        raw_payload_hash=record.raw_payload_hash,
        fetched_at=record.fetched_at,
        imported_at=record.imported_at,
        expires_at=record.expires_at,
    )


def raw_ref_from_source_record(record: SourceRecord, *, source_role: str = "primary") -> RawDataRef:
    return RawDataRef(
        provider=record.provider,
        dataset_key=record.dataset_key,
        source_entity_id=record.source_entity_id,
        source_role=source_role,
        fetched_at=record.fetched_at,
        payload_hash=record.raw_payload_hash,
    )


def provider_sync_state_to_krtour_state(state: ProviderSyncState) -> KrtourProviderSyncState:
    return KrtourProviderSyncState(
        provider=state.provider,
        dataset_key=state.dataset_key,
        sync_scope=state.sync_scope,
        status=state.status,
        cursor=state.cursor,
        last_success_at=state.last_success_at,
        last_attempt_at=state.last_attempt_at,
        next_run_after=state.next_run_after,
        last_error=state.last_error,
        last_error_at=state.last_error_at,
        extra=state.extra or {},
        updated_at=state.updated_at,
    )


def _map_feature_status(status: str) -> str:
    if status == "temporarily_closed":
        return FeatureStatus.INACTIVE.value
    return status


def _decimal_to_float(value: Decimal, *, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise KrtourMapContractError(f"Invalid {field_name}: {value}") from exc


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _feature_urls(*, homepage: str | None) -> FeatureUrls:
    return FeatureUrls.model_validate(_without_none({"homepage": homepage}))

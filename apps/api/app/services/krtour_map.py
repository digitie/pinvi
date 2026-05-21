from __future__ import annotations

from typing import Any, Protocol


class KrtourMapFeatureStore(Protocol):
    """Function-level subset of python-krtour-map feature store APIs used by TripMate."""

    def get_feature(self, feature_id: str) -> Any | None:
        ...


def normalize_krtour_provider_name(provider: str) -> str:
    """Normalize provider names through python-krtour-map's in-process function API."""

    from krtour_map.providers import normalize_provider_name

    return normalize_provider_name(provider)


def feature_to_tripmate_snapshot(feature: Any) -> dict[str, Any]:
    """Convert a python-krtour-map Feature DTO into a TripMate POI snapshot."""

    data = feature.model_dump(mode="json") if hasattr(feature, "model_dump") else dict(feature)
    coord = data.get("coord") or {}
    address = data.get("address") or {}
    return {
        "source": "python-krtour-map",
        "feature_id": data.get("feature_id"),
        "name": data.get("name"),
        "category": data.get("category"),
        "address": address,
        "longitude": coord.get("longitude"),
        "latitude": coord.get("latitude"),
        "marker_icon": data.get("marker_icon"),
        "marker_color": data.get("marker_color"),
        "urls": data.get("urls") or {},
        "detail": data.get("detail"),
        "raw_refs": data.get("raw_refs", []),
    }


def notice_poi_snapshot_from_feature_id(
    feature_store: KrtourMapFeatureStore,
    feature_id: str,
) -> dict[str, Any] | None:
    """Build a notice POI snapshot from python-krtour-map without any HTTP boundary."""

    feature = feature_store.get_feature(feature_id)
    if feature is None:
        return None
    return feature_to_tripmate_snapshot(feature)

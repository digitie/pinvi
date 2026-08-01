"""Map shared golden fixture에 대한 PinVi 독립 byte-contract gate."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, cast

import pytest

from app.core.cache_target_contract import (
    CacheTargetMerkleRow,
    CacheTargetSource,
    DeletedCacheTargetSource,
    cache_target_snapshot_leaf_digest,
    cache_target_snapshot_merkle_root,
    cache_target_source_fingerprint,
    canonical_cache_target_source_bytes,
    normalize_active_cache_target_source,
)

_GOLDEN = Path(__file__).resolve().parent.parent / "contract" / "cache-target-source-v1-golden.json"
_UPSTREAM_MAP_COMMIT = "2aa4e4bb121995612f7df9396b1639a52496a145"
_GOLDEN_SHA256 = "4408ea19ab4853e91ff2c3e2d62920369f01f35e5b262955ab354909702b94a5"


def _fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_GOLDEN.read_bytes()))


def test_vendored_golden_bytes_are_pinned_to_map_commit() -> None:
    assert len(_UPSTREAM_MAP_COMMIT) == 40
    assert hashlib.sha256(_GOLDEN.read_bytes()).hexdigest() == _GOLDEN_SHA256


def test_source_vectors_match_independent_normalization_and_fingerprint() -> None:
    for vector in _fixture()["source_vectors"]:
        source: CacheTargetSource
        if vector["name"] == "deleted":
            source = DeletedCacheTargetSource()
        else:
            source = normalize_active_cache_target_source(**vector["input"])
            assert source.lon_e6 == vector["normalized"]["lon_e6"]
            assert source.lat_e6 == vector["normalized"]["lat_e6"]
            assert source.radius_m == vector["normalized"]["radius_m"]
        assert canonical_cache_target_source_bytes(source).decode() == vector["canonical_utf8"]
        assert cache_target_source_fingerprint(source).hex() == vector["sha256"]


def test_source_normalization_rejects_float_and_invalid_numeric_contract() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        normalize_active_cache_target_source(
            lon=126.9,  # type: ignore[arg-type]
            lat="37.5",
            radius_km="5",
            update_enabled=True,
        )
    with pytest.raises(ValueError, match="lon"):
        normalize_active_cache_target_source(
            lon="180.000001",
            lat="37.5",
            radius_km="5",
            update_enabled=True,
        )
    with pytest.raises(ValueError, match="metre"):
        normalize_active_cache_target_source(
            lon="126.9",
            lat="37.5",
            radius_km="0.0004",
            update_enabled=True,
        )


def test_merkle_vectors_match_leaf_order_empty_and_odd_promotion() -> None:
    fixture = _fixture()["merkle_v1"]
    rows = [
        CacheTargetMerkleRow(
            external_system=row["external_system"],
            target_key=row["target_key"],
            state=row["state"],
            source_generation=row["source_generation"],
            source_payload_fingerprint=bytes.fromhex(row["source_payload_fingerprint"]),
        )
        for row in fixture["rows"]
    ]
    actual_order = [
        unicodedata.normalize("NFC", row.target_key)
        for row in sorted(
            rows,
            key=lambda row: unicodedata.normalize("NFC", row.target_key).encode(),
        )
    ]

    assert actual_order == fixture["expected_nfc_utf8_order"]
    assert cache_target_snapshot_merkle_root([]).hex() == fixture["empty_root"]
    assert [cache_target_snapshot_leaf_digest(row).hex() for row in rows] == [
        row["leaf_sha256"] for row in fixture["rows"]
    ]
    assert cache_target_snapshot_merkle_root(rows).hex() == fixture["root"]
    assert cache_target_snapshot_merkle_root(list(reversed(rows))).hex() == fixture["root"]


def test_merkle_rejects_nfc_duplicate_and_invalid_raw_fingerprint() -> None:
    fingerprint = bytes.fromhex(_fixture()["source_vectors"][2]["sha256"])
    with pytest.raises(ValueError, match="중복"):
        cache_target_snapshot_merkle_root(
            [
                CacheTargetMerkleRow("pinvi", "é", "deleted", 1, fingerprint),
                CacheTargetMerkleRow("pinvi", "e\u0301", "deleted", 2, fingerprint),
            ]
        )
    with pytest.raises(ValueError, match="32바이트"):
        cache_target_snapshot_merkle_root(
            [CacheTargetMerkleRow("pinvi", "key", "active", 1, b"short")]
        )

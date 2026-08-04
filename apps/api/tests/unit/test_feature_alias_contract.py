"""Map shared alias-map golden에 대한 PinVi 독립 byte-contract gate (T-VN-32C)."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, cast

import pytest

from app.core.feature_alias_contract import (
    FEATURE_ALIAS_MAP_VERSION,
    KNOWN_ALIAS_KINDS,
    FeatureAliasRow,
    alias_leaf_digest,
    alias_map_merkle_root,
    derive_feature_uuid,
    feature_uuid_namespace,
    parse_canonical_feature_uuid,
    validate_alias,
    verify_alias_row,
)

_GOLDEN = Path(__file__).resolve().parent.parent / "contract" / "feature-alias-map-v1-golden.json"
# T-VN-32C 쌍 PR: Map 측 PR 머지 후 merge SHA로 고정하고 contract-pin-consistency
# workflow에 byte-diff 단계를 추가한다. 그 전에는 vendored bytes sha만 고정한다.
_UPSTREAM_MAP_COMMIT: str | None = None
_GOLDEN_SHA256 = "3138587c6118849143d04e99fcb3263c54dd3b1f694408b5dc4a43dad12938ca"


def _fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_GOLDEN.read_bytes()))


def _rows() -> list[FeatureAliasRow]:
    return [
        FeatureAliasRow(
            alias=row["alias"],
            feature_uuid=parse_canonical_feature_uuid(row["feature_uuid"]),
            alias_kind=row["alias_kind"],
        )
        for row in _fixture()["merkle_v1"]["rows"]
    ]


def test_vendored_golden_bytes_are_pinned() -> None:
    assert hashlib.sha256(_GOLDEN.read_bytes()).hexdigest() == _GOLDEN_SHA256
    if _UPSTREAM_MAP_COMMIT is None:
        pytest.skip("Map T-VN-32C PR 머지 후 merge SHA 핀 고정 (쌍 PR 마무리 절차)")
    assert len(_UPSTREAM_MAP_COMMIT) == 40


def test_schema_version_kinds_and_namespace_match_independent_derivation() -> None:
    fixture = _fixture()
    assert fixture["schema"] == FEATURE_ALIAS_MAP_VERSION
    assert fixture["alias_kinds"] == sorted(KNOWN_ALIAS_KINDS)
    # namespace는 상수 복사가 아니라 basis 문자열에서 독립 재파생한 값과 대조한다.
    assert str(feature_uuid_namespace()) == fixture["derivation"]["feature_uuid_namespace"]


def test_rows_match_independent_derivation_leaf_order_and_roots() -> None:
    fixture = _fixture()["merkle_v1"]
    rows = _rows()
    for row in rows:
        verify_alias_row(row)
        assert row.feature_uuid == derive_feature_uuid(row.alias)
    assert [alias_leaf_digest(row).hex() for row in rows] == [
        row["leaf_sha256"] for row in fixture["rows"]
    ]
    assert [
        row.alias for row in sorted(rows, key=lambda row: row.alias.encode("utf-8"))
    ] == fixture["expected_nfc_utf8_order"]
    assert alias_map_merkle_root(rows).hex() == fixture["root"]
    assert alias_map_merkle_root(list(reversed(rows))).hex() == fixture["root"]
    assert alias_map_merkle_root([]).hex() == fixture["empty_root"]
    assert alias_map_merkle_root(rows[:3]).hex() == fixture["odd_promotion_root_first3"]


def test_derivation_mismatch_and_unknown_kind_are_rejected() -> None:
    good = _rows()[0]
    with pytest.raises(ValueError, match="파생 불일치"):
        verify_alias_row(
            FeatureAliasRow(
                alias=good.alias,
                feature_uuid=uuid.UUID("00000000-0000-4000-8000-000000000000"),
                alias_kind=good.alias_kind,
            )
        )
    with pytest.raises(ValueError, match="alias_kind"):
        verify_alias_row(
            FeatureAliasRow(
                alias=good.alias,
                feature_uuid=good.feature_uuid,
                alias_kind="merge_loser",
            )
        )


def test_alias_validation_rejects_non_nfc_padding_empty_and_overlong() -> None:
    with pytest.raises(ValueError, match="trim"):
        validate_alias("")
    with pytest.raises(ValueError, match="trim"):
        validate_alias(" f_x ")
    with pytest.raises(ValueError, match="NFC"):
        validate_alias("e\u0301")
    with pytest.raises(ValueError, match="256"):
        validate_alias("f" * 257)


def test_uuid_parsing_rejects_non_canonical_forms() -> None:
    canonical = "4232803d-a8a7-57c2-b80b-e13ca8fa1a2a"
    assert str(parse_canonical_feature_uuid(canonical)) == canonical
    for bad in (
        canonical.upper(),
        canonical.replace("-", ""),
        "urn:uuid:" + canonical,
        "{" + canonical + "}",
        canonical[:-1],
    ):
        with pytest.raises(ValueError, match="canonical"):
            parse_canonical_feature_uuid(bad)


def test_merkle_rejects_duplicate_alias() -> None:
    rows = _rows()
    with pytest.raises(ValueError, match="중복"):
        alias_map_merkle_root([rows[0], rows[0]])

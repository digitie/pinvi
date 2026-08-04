"""PinVi가 독립 구현하는 feature alias-map v1 byte 계약 (T-VN-32C, Map ADR-068).

Map의 `contracts/feature-alias-map-v1-golden.json`을 vendored 사본으로 두고 양
저장소가 **독립 구현**으로 같은 leaf/merkle 값을 재계산한다
(`cache_target_contract`의 golden 패턴과 동일). Map 응답의 `feature_id` 값이
UUID로 전환되기 전에, PinVi가 저장 중인 legacy `f_*` 참조를 검증된 alias map으로
DB-to-DB 이관하는 데 쓰인다.

canonical 규칙 (feature-alias-map-v1):

- row = ``(alias, feature_uuid, alias_kind)``. alias는 trim된 비어 있지 않은
  NFC 정규형(비-NFC는 정규화하지 않고 거부) 256자 이하. alias_kind는 닫힌 집합
  (현재 ``legacy_feature_id`` 1종).
- leaf = ``sha256(b"KTMFAMLEAF\\x00" || u32be(len(alias)) || alias_utf8
  || u32be(len(kind)) || kind_utf8 || uuid_raw_16)``.
- 정렬은 alias UTF-8 byte 오름차순, node는
  ``sha256(b"KTMFAMNODE\\x00" || left || right)``, 홀수 leaf는 승격, 빈 map은
  ``sha256(b"KTMFAMEMPTY\\x00")``.
- ``legacy_feature_id`` 행은 ``feature_uuid == uuid5(namespace, alias)``
  파생 검증을 함께 통과해야 "검증된 alias map"이다. namespace는 상수 복사가
  아니라 ``uuid5(NAMESPACE_URL, 'kor-travel-map:feature-uuid:v1')``로 매번
  재파생한다 — 두 저장소가 같은 basis에서 독립 계산함을 코드로 증명한다.
"""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from functools import cache
from typing import Final

FEATURE_ALIAS_MAP_VERSION: Final = "feature-alias-map-v1"
LEGACY_ALIAS_KIND: Final = "legacy_feature_id"
KNOWN_ALIAS_KINDS: Final = frozenset({LEGACY_ALIAS_KIND})
MAX_ALIAS_LENGTH: Final = 256

_LEAF_DOMAIN: Final = b"KTMFAMLEAF\x00"
_NODE_DOMAIN: Final = b"KTMFAMNODE\x00"
_EMPTY_DOMAIN: Final = b"KTMFAMEMPTY\x00"
_MAX_U32: Final = 2**32 - 1


@cache
def feature_uuid_namespace() -> uuid.UUID:
    """Map ADR-068 파생 namespace를 basis 문자열에서 재파생한다."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "kor-travel-map:feature-uuid:v1")


def derive_feature_uuid(alias: str) -> uuid.UUID:
    """legacy alias → 결정적 feature UUID (Map과 독립 동일 계산)."""
    if not alias:
        raise ValueError("alias는 비어 있지 않은 문자열이어야 합니다.")
    return uuid.uuid5(feature_uuid_namespace(), alias)


def validate_alias(value: str) -> str:
    """alias canonical 계약 — trim·비어있지 않음·NFC·256자 이하 (위반 거부)."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("alias는 trim된 비어 있지 않은 문자열이어야 합니다.")
    if len(value) > MAX_ALIAS_LENGTH:
        raise ValueError(f"alias는 {MAX_ALIAS_LENGTH}자 이하여야 합니다.")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("alias는 NFC 정규형이어야 합니다 — 정규화하지 않고 거부한다.")
    return value


def parse_canonical_feature_uuid(value: str) -> uuid.UUID:
    """canonical lowercase hyphenated 36자 표기만 UUID로 수용한다."""
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("feature_uuid는 canonical lowercase hyphenated 표기여야 합니다.")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("feature_uuid는 canonical lowercase hyphenated 표기여야 합니다.") from exc
    if str(parsed) != value:
        raise ValueError("feature_uuid는 canonical lowercase hyphenated 표기여야 합니다.")
    return parsed


@dataclass(frozen=True, slots=True)
class FeatureAliasRow:
    """alias-map leaf의 exact 3-field row (typed UUID)."""

    alias: str
    feature_uuid: uuid.UUID
    alias_kind: str


def verify_alias_row(row: FeatureAliasRow) -> None:
    """canonical + 닫힌 kind + legacy 파생 검증 — 하나라도 어긋나면 거부."""
    validate_alias(row.alias)
    if not isinstance(row.feature_uuid, uuid.UUID):
        raise ValueError("feature_uuid는 uuid.UUID 타입이어야 합니다.")
    if row.alias_kind not in KNOWN_ALIAS_KINDS:
        raise ValueError(f"알 수 없는 alias_kind: {row.alias_kind!r}")
    if row.alias_kind == LEGACY_ALIAS_KIND and row.feature_uuid != derive_feature_uuid(row.alias):
        raise ValueError(
            f"legacy alias 파생 불일치: alias={row.alias!r} "
            f"feature_uuid={row.feature_uuid} expected={derive_feature_uuid(row.alias)}"
        )


def _leaf_parts(row: FeatureAliasRow) -> tuple[bytes, bytes]:
    alias_utf8 = validate_alias(row.alias).encode("utf-8")
    if row.alias_kind not in KNOWN_ALIAS_KINDS:
        raise ValueError(f"알 수 없는 alias_kind: {row.alias_kind!r}")
    kind_utf8 = row.alias_kind.encode("utf-8")
    if len(alias_utf8) > _MAX_U32 or len(kind_utf8) > _MAX_U32:
        raise ValueError("alias/alias_kind UTF-8 길이가 u32 범위를 벗어났습니다.")
    if not isinstance(row.feature_uuid, uuid.UUID):
        raise ValueError("feature_uuid는 uuid.UUID 타입이어야 합니다.")
    material = (
        _LEAF_DOMAIN
        + len(alias_utf8).to_bytes(4, "big")
        + alias_utf8
        + len(kind_utf8).to_bytes(4, "big")
        + kind_utf8
        + row.feature_uuid.bytes
    )
    return alias_utf8, material


def alias_leaf_digest(row: FeatureAliasRow) -> bytes:
    """domain-separated leaf의 raw SHA-256 digest."""
    return hashlib.sha256(_leaf_parts(row)[1]).digest()


def alias_map_merkle_root(rows: list[FeatureAliasRow]) -> bytes:
    """alias UTF-8 byte 순서 + 홀수 승격 merkle root (raw 32바이트)."""
    ordered: list[tuple[bytes, bytes]] = []
    seen_aliases: set[bytes] = set()
    for row in rows:
        alias_utf8, material = _leaf_parts(row)
        if alias_utf8 in seen_aliases:
            raise ValueError("alias-map에 중복 alias가 있습니다.")
        seen_aliases.add(alias_utf8)
        ordered.append((alias_utf8, hashlib.sha256(material).digest()))
    if not ordered:
        return hashlib.sha256(_EMPTY_DOMAIN).digest()
    ordered.sort(key=lambda pair: pair[0])
    level = [digest for _, digest in ordered]
    while len(level) > 1:
        merged: list[bytes] = []
        for index in range(0, len(level) - 1, 2):
            merged.append(hashlib.sha256(_NODE_DOMAIN + level[index] + level[index + 1]).digest())
        if len(level) % 2 == 1:
            merged.append(level[-1])
        level = merged
    return level[0]

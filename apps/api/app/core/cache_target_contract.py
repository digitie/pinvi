"""PinVi가 독립 구현하는 cache target source/Merkle byte 계약."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException, InvalidOperation
from typing import Final, Literal

CACHE_TARGET_SOURCE_VERSION: Final = "cache-target-source-v1"

_COORD_QUANTUM = Decimal("0.000001")
_RADIUS_QUANTUM_KM = Decimal("0.001")
_COORD_SCALE = 1_000_000
_METRES_PER_KM = 1_000
_MAX_RADIUS_KM = Decimal("100")
_MAX_U32 = 2**32 - 1
_MAX_U64 = 2**64 - 1
_LEAF_DOMAIN = b"KTMCTLEAF\x00"
_NODE_DOMAIN = b"KTMCTNODE\x00"
_EMPTY_DOMAIN = b"KTMCTEMPTY\x00"


@dataclass(frozen=True, slots=True)
class ActiveCacheTargetSource:
    """JSON float 없이 직렬화할 active source 정수 projection."""

    lon_e6: int
    lat_e6: int
    radius_m: int
    update_enabled: bool

    def __post_init__(self) -> None:
        if not -180_000_000 <= self.lon_e6 <= 180_000_000:
            raise ValueError("lon_e6가 경도 범위를 벗어났습니다.")
        if not -90_000_000 <= self.lat_e6 <= 90_000_000:
            raise ValueError("lat_e6가 위도 범위를 벗어났습니다.")
        if not 1 <= self.radius_m <= 100_000:
            raise ValueError("radius_m은 1 이상 100000 이하여야 합니다.")
        if not isinstance(self.update_enabled, bool):
            raise TypeError("update_enabled는 bool이어야 합니다.")


@dataclass(frozen=True, slots=True)
class DeletedCacheTargetSource:
    """field가 추가되지 않는 durable tombstone marker."""


CacheTargetSource = ActiveCacheTargetSource | DeletedCacheTargetSource


@dataclass(frozen=True, slots=True)
class CacheTargetMerkleRow:
    """snapshot leaf를 구성하는 exact 5-field row."""

    external_system: str
    target_key: str
    state: Literal["active", "deleted"]
    source_generation: int
    source_payload_fingerprint: bytes


def _decimal(value: Decimal | int | str, *, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError(f"{field}는 Decimal, int 또는 10진 문자열이어야 합니다.")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field}는 유효한 10진수여야 합니다.") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field}는 유한한 10진수여야 합니다.")
    return parsed


def _scaled_half_even(value: Decimal, *, quantum: Decimal, scale: int) -> int:
    try:
        return int(value.quantize(quantum, rounding=ROUND_HALF_EVEN) * scale)
    except DecimalException as exc:
        raise ValueError("numeric 값이 canonical 범위를 벗어났습니다.") from exc


def normalize_active_cache_target_source(
    *,
    lon: Decimal | int | str,
    lat: Decimal | int | str,
    radius_km: Decimal | int | str,
    update_enabled: bool,
) -> ActiveCacheTargetSource:
    """DB numeric source를 v1 정수 단위로 정규화한다."""
    longitude = _decimal(lon, field="lon")
    latitude = _decimal(lat, field="lat")
    radius = _decimal(radius_km, field="radius_km")
    if not Decimal("-180") <= longitude <= Decimal("180"):
        raise ValueError("lon이 경도 범위를 벗어났습니다.")
    if not Decimal("-90") <= latitude <= Decimal("90"):
        raise ValueError("lat이 위도 범위를 벗어났습니다.")
    if not Decimal("0") < radius <= _MAX_RADIUS_KM:
        raise ValueError("radius_km는 0 초과 100 이하여야 합니다.")
    if not isinstance(update_enabled, bool):
        raise TypeError("update_enabled는 bool이어야 합니다.")

    radius_m = _scaled_half_even(radius, quantum=_RADIUS_QUANTUM_KM, scale=_METRES_PER_KM)
    if radius_m < 1:
        raise ValueError("radius_km는 metre 정규화 뒤에도 양수여야 합니다.")
    return ActiveCacheTargetSource(
        lon_e6=_scaled_half_even(longitude, quantum=_COORD_QUANTUM, scale=_COORD_SCALE),
        lat_e6=_scaled_half_even(latitude, quantum=_COORD_QUANTUM, scale=_COORD_SCALE),
        radius_m=radius_m,
        update_enabled=update_enabled,
    )


def canonical_cache_target_source_bytes(source: CacheTargetSource) -> bytes:
    """sorted-key compact UTF-8 JSON을 만든다."""
    if isinstance(source, ActiveCacheTargetSource):
        payload: dict[str, object] = {
            "version": CACHE_TARGET_SOURCE_VERSION,
            "state": "active",
            "coord": {"lon_e6": source.lon_e6, "lat_e6": source.lat_e6},
            "radius_m": source.radius_m,
            "update_enabled": source.update_enabled,
        }
    elif isinstance(source, DeletedCacheTargetSource):
        payload = {"version": CACHE_TARGET_SOURCE_VERSION, "state": "deleted"}
    else:
        raise TypeError("지원하지 않는 cache target source 타입입니다.")
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def cache_target_source_fingerprint(source: CacheTargetSource) -> bytes:
    """canonical source의 raw SHA-256 digest를 반환한다."""
    return hashlib.sha256(canonical_cache_target_source_bytes(source)).digest()


def _nfc_utf8(value: str, *, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field}는 비어 있지 않은 문자열이어야 합니다.")
    try:
        encoded = unicodedata.normalize("NFC", value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field}는 유효한 Unicode 문자열이어야 합니다.") from exc
    if len(encoded) > _MAX_U32:
        raise ValueError(f"{field} UTF-8 길이가 u32 범위를 벗어났습니다.")
    return encoded


def _leaf_parts(row: CacheTargetMerkleRow) -> tuple[bytes, bytes, bytes]:
    system = _nfc_utf8(row.external_system, field="external_system")
    key = _nfc_utf8(row.target_key, field="target_key")
    if row.state == "active":
        state_byte = b"\x01"
    elif row.state == "deleted":
        state_byte = b"\x02"
    else:
        raise ValueError("state는 active 또는 deleted여야 합니다.")
    if isinstance(row.source_generation, bool) or not 0 < row.source_generation <= _MAX_U64:
        raise ValueError("source_generation은 양의 u64여야 합니다.")
    if (
        not isinstance(row.source_payload_fingerprint, bytes)
        or len(row.source_payload_fingerprint) != 32
    ):
        raise ValueError("source_payload_fingerprint는 raw SHA-256 32바이트여야 합니다.")

    material = b"".join(
        (
            _LEAF_DOMAIN,
            len(system).to_bytes(4, "big"),
            system,
            len(key).to_bytes(4, "big"),
            key,
            state_byte,
            row.source_generation.to_bytes(8, "big"),
            row.source_payload_fingerprint,
        )
    )
    return system, key, material


def cache_target_snapshot_leaf_digest(row: CacheTargetMerkleRow) -> bytes:
    """domain-separated Merkle leaf digest를 반환한다."""
    return hashlib.sha256(_leaf_parts(row)[2]).digest()


def cache_target_snapshot_merkle_root(rows: list[CacheTargetMerkleRow]) -> bytes:
    """NFC UTF-8 정렬과 odd promotion을 적용한 Merkle v1 root."""
    leaves: list[tuple[bytes, bytes, bytes]] = []
    identities: set[tuple[bytes, bytes]] = set()
    for row in rows:
        system, key, material = _leaf_parts(row)
        identity = (system, key)
        if identity in identities:
            raise ValueError("NFC 정규화 뒤 cache target identity가 중복됩니다.")
        identities.add(identity)
        leaves.append((system, key, hashlib.sha256(material).digest()))

    if not leaves:
        return hashlib.sha256(_EMPTY_DOMAIN).digest()
    level = [digest for _, _, digest in sorted(leaves, key=lambda item: item[:2])]
    while len(level) > 1:
        parent_level: list[bytes] = []
        for offset in range(0, len(level), 2):
            left = level[offset]
            if offset + 1 == len(level):
                parent_level.append(left)
            else:
                parent_level.append(
                    hashlib.sha256(_NODE_DOMAIN + left + level[offset + 1]).digest()
                )
        level = parent_level
    return level[0]

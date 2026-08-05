"""kor-travel-map alias-map 이관 표면(service) 전용 HTTP client (T-VN-32C).

Map ``GET /v1/service/feature-alias-maps``(canonical keyset 페이지)와
``GET /v1/service/feature-alias-maps/checksum``(전체 merkle root)을 소비한다.
계약 정본은 vendored ``tests/contract/feature-alias-map-v1-golden.json``
(feature-alias-map-v1)이고, row 검증·checksum 재계산은
``app.core.feature_alias_contract`` 독립 구현이 담당한다 — 본 client는 응답을
canonical 타입으로만 변환하고, 계약과 다른 응답은 즉시 거부한다 (fail-close).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import httpx

from app.core.feature_alias_contract import (
    FEATURE_ALIAS_MAP_VERSION,
    FeatureAliasRow,
    parse_canonical_feature_uuid,
    validate_alias,
)

_SERVICE_TOKEN_HEADER: Final = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - header name
_ALIAS_MAP_PATH: Final = "/v1/service/feature-alias-maps"
_CHECKSUM_PATH: Final = "/v1/service/feature-alias-maps/checksum"
_PAGE_LIMIT_MAX: Final = 1000
_LOWER_HEX: Final = frozenset("0123456789abcdef")

DEFAULT_MAX_ROWS: Final = 2_000_000
"""이관 pull의 상한 — 초과는 계약 위반(폭주 응답)으로 간주하고 중단한다."""


class AliasMapNetworkError(RuntimeError):
    """응답을 받지 못한 transient transport failure."""


class AliasMapContractError(ValueError):
    """Map alias-map 응답이 feature-alias-map-v1 계약과 다름."""


@dataclass(frozen=True, slots=True)
class AliasMapChecksum:
    """Map 저장소 전체 alias-map checksum."""

    alias_count: int
    merkle_root: bytes
    #: Map generator가 아직 uuid5 파생을 강제하는 세대인지 (Map 0083 이후 노출).
    #: additive 필드 — 구 Map 응답에 없으면 None이며 계약 오류가 아니다.
    derivation_enforced: bool | None = None


@dataclass(frozen=True, slots=True)
class AliasMapPage:
    """canonical 순서 keyset 페이지."""

    rows: tuple[FeatureAliasRow, ...]
    has_more: bool
    next_after_alias: str | None


def _data_or_reject(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise AliasMapContractError("alias-map 응답 envelope에 data object가 없습니다.")
    data: dict[str, Any] = payload["data"]
    if data.get("schema_version") != FEATURE_ALIAS_MAP_VERSION:
        raise AliasMapContractError(
            f"schema_version이 {FEATURE_ALIAS_MAP_VERSION}이 아닙니다: "
            f"{data.get('schema_version')!r}"
        )
    return data


def _parse_row(raw: Any) -> FeatureAliasRow:
    if not isinstance(raw, dict):
        raise AliasMapContractError("alias-map row는 object여야 합니다.")
    try:
        return FeatureAliasRow(
            alias=validate_alias(raw.get("alias", "")),
            feature_uuid=parse_canonical_feature_uuid(raw.get("feature_uuid", "")),
            alias_kind=str(raw.get("alias_kind", "")),
        )
    except ValueError as exc:
        raise AliasMapContractError(f"alias-map row가 canonical 계약 위반: {exc}") from exc


class KorTravelMapAliasMapClient:
    """service token으로 alias-map 이관 표면을 읽는 얇은 transport."""

    def __init__(self, http: httpx.AsyncClient, *, service_token: str) -> None:
        self._http = http
        self._headers = {_SERVICE_TOKEN_HEADER: service_token} if service_token else {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._http.get(path, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise AliasMapNetworkError(f"alias-map 요청 실패: {exc}") from exc
        if response.status_code != 200:
            raise AliasMapContractError(
                f"alias-map 응답 status {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AliasMapContractError("alias-map 응답이 JSON이 아닙니다.") from exc

    async def fetch_checksum(self) -> AliasMapChecksum:
        data = _data_or_reject(await self._get_json(_CHECKSUM_PATH))
        alias_count = data.get("alias_count")
        merkle_root = data.get("merkle_root")
        if not isinstance(alias_count, int) or isinstance(alias_count, bool) or alias_count < 0:
            raise AliasMapContractError("alias_count는 0 이상의 정수여야 합니다.")
        if (
            not isinstance(merkle_root, str)
            or len(merkle_root) != 64
            or any(character not in _LOWER_HEX for character in merkle_root)
        ):
            raise AliasMapContractError("merkle_root는 lowercase SHA-256 hex여야 합니다.")
        derivation_enforced = data.get("derivation_enforced")
        if derivation_enforced is not None and not isinstance(derivation_enforced, bool):
            raise AliasMapContractError("derivation_enforced는 boolean 또는 부재여야 합니다.")
        return AliasMapChecksum(
            alias_count=alias_count,
            merkle_root=bytes.fromhex(merkle_root),
            derivation_enforced=derivation_enforced,
        )

    async def fetch_page(
        self, *, after_alias: str | None, limit: int = _PAGE_LIMIT_MAX
    ) -> AliasMapPage:
        if not 1 <= limit <= _PAGE_LIMIT_MAX:
            raise ValueError(f"limit은 1~{_PAGE_LIMIT_MAX} 범위여야 합니다.")
        params: dict[str, Any] = {"limit": limit}
        if after_alias is not None:
            params["after_alias"] = after_alias
        data = _data_or_reject(await self._get_json(_ALIAS_MAP_PATH, params=params))
        raw_rows = data.get("rows")
        if not isinstance(raw_rows, list):
            raise AliasMapContractError("rows는 배열이어야 합니다.")
        has_more = data.get("has_more")
        if not isinstance(has_more, bool):
            raise AliasMapContractError("has_more는 boolean이어야 합니다.")
        next_after = data.get("next_after_alias")
        if next_after is not None and not isinstance(next_after, str):
            raise AliasMapContractError("next_after_alias는 문자열 또는 null이어야 합니다.")
        if has_more and not next_after:
            raise AliasMapContractError("has_more 페이지에는 next_after_alias가 필요합니다.")
        return AliasMapPage(
            rows=tuple(_parse_row(raw) for raw in raw_rows),
            has_more=has_more,
            next_after_alias=next_after,
        )

    async def fetch_all_rows(
        self, *, page_limit: int = _PAGE_LIMIT_MAX, max_rows: int = DEFAULT_MAX_ROWS
    ) -> list[FeatureAliasRow]:
        """canonical 순서로 전체를 순회한다 — keyset 역행/정체는 계약 위반."""
        rows: list[FeatureAliasRow] = []
        after: str | None = None
        while True:
            page = await self.fetch_page(after_alias=after, limit=page_limit)
            rows.extend(page.rows)
            if len(rows) > max_rows:
                raise AliasMapContractError(f"alias-map row가 상한({max_rows})을 초과했습니다.")
            if not page.has_more:
                return rows
            next_after = page.next_after_alias
            if next_after is None or (
                after is not None and next_after.encode("utf-8") <= after.encode("utf-8")
            ):
                raise AliasMapContractError("keyset이 전진하지 않습니다 — 순회를 중단합니다.")
            after = next_after

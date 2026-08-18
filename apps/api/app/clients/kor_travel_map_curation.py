"""kor-travel-map canonical curation snapshot 전용 service transport."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105
_ETAG_RE = re.compile(r'^"(sha256:[0-9a-f]{64})"$')
_POSTGRES_BIGINT_MAX = 9_223_372_036_854_775_807
_COLLECTION_PAGE_SIZE = 200
_COLLECTION_MAX_ITEMS = 2_000
_COLLECTION_MAX_PAGES = _COLLECTION_MAX_ITEMS // _COLLECTION_PAGE_SIZE
_CUTOVER_MAPPING_PAGE_SIZE = 200
_CUTOVER_MAPPING_ROOT_VERSION = "ktm-curation-cutover-mapping-v1"


class CurationSnapshotError(Exception):
    """curation snapshot 호출 또는 계약 오류의 공통 기반."""


class CurationSnapshotUnavailable(CurationSnapshotError):
    """network 또는 upstream 5xx."""


class CurationSnapshotContractError(CurationSnapshotError):
    """성공 응답이나 pagination receipt가 vendored contract와 다름."""


class CurationSnapshotNotFound(CurationSnapshotError):
    """canonical collection/item이 공개 snapshot에 없음."""


class CurationSnapshotTooLarge(CurationSnapshotError):
    """collection이 Map service snapshot 상한을 초과함."""


class CurationSnapshotServiceProblem(CurationSnapshotError):
    """재시작 가능한 cursor conflict 외의 typed upstream 4xx."""

    def __init__(self, *, status_code: int, code: str) -> None:
        super().__init__(f"kor-travel-map curation snapshot problem: {status_code} {code}")
        self.status_code = status_code
        self.code = code


class CurationCutoverMappingError(Exception):
    """T-VN-40C maintenance mapping export 호출/계약 오류의 공통 기반."""


class CurationCutoverMappingUnavailable(CurationCutoverMappingError):
    """network 또는 upstream 5xx."""


class CurationCutoverMappingContractError(CurationCutoverMappingError):
    """mapping keyset/root/count가 vendored contract와 다름."""


class CurationCutoverMappingServiceProblem(CurationCutoverMappingError):
    """cursor restart 외의 typed upstream 4xx."""

    def __init__(self, *, status_code: int, code: str) -> None:
        super().__init__(f"kor-travel-map curation cutover mapping problem: {status_code} {code}")
        self.status_code = status_code
        self.code = code


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurationSnapshotCollection(_ClosedModel):
    theme_slug: Annotated[str, Field(min_length=1, max_length=128)]
    theme_name: Annotated[str, Field(min_length=1, max_length=200)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    edition_key: Annotated[str, Field(max_length=100)]


class CurationSnapshotItem(_ClosedModel):
    feature_id: uuid.UUID
    relation: str
    sort_order: int
    title: str | None
    summary: str | None


class CurationSnapshotFeature(_ClosedModel):
    feature_id: uuid.UUID
    name: str
    category: str
    kind: str
    lon: float | None
    lat: float | None
    address: dict[str, Any]
    detail: dict[str, Any]
    source_record_key: str | None

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> CurationSnapshotFeature:
        if (self.lon is None) != (self.lat is None):
            raise ValueError("feature lon/lat는 둘 다 있거나 둘 다 없어야 합니다.")
        if self.lon is not None and not -180 <= self.lon <= 180:
            raise ValueError("feature lon 범위가 유효하지 않습니다.")
        if self.lat is not None and not -90 <= self.lat <= 90:
            raise ValueError("feature lat 범위가 유효하지 않습니다.")
        return self


RevisionString = Annotated[str, Field(pattern=r"^[1-9][0-9]*$")]
SnapshotEtag = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
ItemSetHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CurationItemDetailSnapshot(_ClosedModel):
    curation_item_id: uuid.UUID
    collection_id: uuid.UUID
    row_revision: RevisionString
    etag: SnapshotEtag
    updated_at: datetime
    collection: CurationSnapshotCollection
    item: CurationSnapshotItem
    feature: CurationSnapshotFeature

    @model_validator(mode="after")
    def validate_identity_and_revision(self) -> CurationItemDetailSnapshot:
        if self.item.feature_id != self.feature.feature_id:
            raise ValueError("item/feature identity가 다릅니다.")
        if int(self.row_revision) > _POSTGRES_BIGINT_MAX:
            raise ValueError("item row_revision이 PostgreSQL BIGINT 범위를 초과합니다.")
        return self


class CurationCollectionDetailSnapshotPage(_ClosedModel):
    collection_id: uuid.UUID
    row_revision: RevisionString
    etag: SnapshotEtag
    updated_at: datetime
    collection: CurationSnapshotCollection
    item_count: int = Field(ge=0, le=_COLLECTION_MAX_ITEMS)
    item_set_hash_version: Literal["ktm-db-item-set-v1"]
    item_set_hash: ItemSetHash
    items: list[CurationItemDetailSnapshot] = Field(max_length=200)
    next_cursor: str | None
    complete: bool

    @model_validator(mode="after")
    def validate_page(self) -> CurationCollectionDetailSnapshotPage:
        if int(self.row_revision) > _POSTGRES_BIGINT_MAX:
            raise ValueError("collection row_revision이 PostgreSQL BIGINT 범위를 초과합니다.")
        if any(item.collection_id != self.collection_id for item in self.items):
            raise ValueError("page item의 collection identity가 다릅니다.")
        if any(item.collection != self.collection for item in self.items):
            raise ValueError("page item의 collection projection이 다릅니다.")
        if self.complete != (self.next_cursor is None):
            raise ValueError("complete/next_cursor shape가 다릅니다.")
        return self


class CurationCutoverIdentityMapping(_ClosedModel):
    """Map immutable legacy identity에서 canonical UUID로의 one-to-one evidence."""

    legacy_curated_feature_id: uuid.UUID
    collection_id: uuid.UUID
    curation_item_id: uuid.UUID
    mapping_kind: Literal["legacy_projection", "official_membership", "manual_membership"]
    source_row_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CurationCutoverIdentityMappingExportPage(_ClosedModel):
    """Map maintenance endpoint가 반환하는 root-bound keyset page."""

    mapping_root_version: Literal["ktm-curation-cutover-mapping-v1"]
    mapping_count: Annotated[int, Field(ge=0)]
    mapping_root: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    mappings: list[CurationCutoverIdentityMapping] = Field(max_length=_CUTOVER_MAPPING_PAGE_SIZE)
    next_cursor: str | None
    complete: bool

    @model_validator(mode="after")
    def validate_page(self) -> CurationCutoverIdentityMappingExportPage:
        if self.complete != (self.next_cursor is None):
            raise ValueError("mapping complete/next_cursor shape가 다릅니다.")
        return self


@dataclass(frozen=True)
class CurationCollectionSnapshotSet:
    collection_id: uuid.UUID
    row_revision: int
    source_etag: str
    updated_at: datetime
    collection: CurationSnapshotCollection
    item_count: int
    item_set_hash_version: Literal["ktm-db-item-set-v1"]
    item_set_hash: str
    items: tuple[CurationItemDetailSnapshot, ...]


@dataclass(frozen=True)
class CurationCollectionFetchResult:
    not_modified: bool
    source_etag: str
    snapshot: CurationCollectionSnapshotSet | None


@dataclass(frozen=True)
class CurationCutoverMappingSet:
    """PinVi backfill receipt가 그대로 저장할 immutable Map mapping snapshot."""

    mapping_root_version: Literal["ktm-curation-cutover-mapping-v1"]
    mapping_count: int
    mapping_root: str
    mappings: tuple[CurationCutoverIdentityMapping, ...]


def _problem_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "INVALID_PROBLEM"
    if not isinstance(payload, dict):
        return "INVALID_PROBLEM"
    code = payload.get("code")
    return code if isinstance(code, str) and code else "HTTP_ERROR"


def _response_etag(response: httpx.Response) -> tuple[str, str]:
    raw = response.headers.get("ETag", "")
    match = _ETAG_RE.fullmatch(raw)
    if match is None:
        raise CurationSnapshotContractError("snapshot response ETag가 strong SHA-256이 아닙니다.")
    return raw, match.group(1)


class CurationSnapshotServiceClient:
    """`pinvi:curation-snapshot:read` principal에 고정된 read-only client."""

    def __init__(self, http: httpx.AsyncClient, *, token: str, max_attempts: int = 3) -> None:
        if len(token) < 32 or any(character.isspace() for character in token):
            raise ValueError("curation snapshot token은 whitespace 없는 32자 이상이어야 합니다.")
        if max_attempts < 1:
            raise ValueError("max_attempts는 1 이상이어야 합니다.")
        self._http = http
        self._token = token
        self._max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(
        self,
        *,
        collection_id: uuid.UUID,
        cursor: str | None,
        if_none_match: str | None,
    ) -> httpx.Response:
        headers = {_SERVICE_TOKEN_HEADER: self._token}
        if if_none_match is not None:
            if _ETAG_RE.fullmatch(if_none_match) is None:
                raise ValueError("If-None-Match는 raw strong snapshot ETag여야 합니다.")
            headers["If-None-Match"] = if_none_match
        params: dict[str, str | int] = {"page_size": _COLLECTION_PAGE_SIZE}
        if cursor is not None:
            params["cursor"] = cursor

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http.get(
                    f"/v1/service/curation-collections/{collection_id}/detail-snapshot",
                    params=params,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise CurationSnapshotUnavailable(
                        "kor-travel-map curation snapshot network failure"
                    ) from exc
                await asyncio.sleep(0)
                continue
            if response.status_code >= 500 and attempt < self._max_attempts:
                await asyncio.sleep(0)
                continue
            return response
        raise AssertionError("unreachable")

    async def get_collection_snapshot(
        self,
        collection_id: uuid.UUID,
        *,
        if_none_match: str | None = None,
    ) -> CurationCollectionFetchResult:
        """authoritative collection item set을 검증해 bounded restart로 완성한다."""

        for restart in range(self._max_attempts):
            result = await self._get_collection_once(
                collection_id=collection_id,
                if_none_match=if_none_match,
            )
            if result is not None:
                return result
            if restart + 1 < self._max_attempts:
                await asyncio.sleep(0)
        raise CurationSnapshotServiceProblem(
            status_code=status.HTTP_409_CONFLICT,
            code="CURATION_SNAPSHOT_CHANGED",
        )

    async def _get_collection_once(
        self,
        *,
        collection_id: uuid.UUID,
        if_none_match: str | None,
    ) -> CurationCollectionFetchResult | None:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        seen_items: set[uuid.UUID] = set()
        items: list[CurationItemDetailSnapshot] = []
        first_page: CurationCollectionDetailSnapshotPage | None = None
        source_etag = ""
        page_count = 0

        while True:
            page_count += 1
            if page_count > _COLLECTION_MAX_PAGES:
                raise CurationSnapshotContractError(
                    "collection snapshot page 수가 2,000-item 계약을 초과합니다."
                )
            response = await self._get(
                collection_id=collection_id,
                cursor=cursor,
                if_none_match=if_none_match if cursor is None else None,
            )
            if response.status_code == status.HTTP_304_NOT_MODIFIED:
                if cursor is not None or if_none_match is None:
                    raise CurationSnapshotContractError(
                        "304가 first conditional page 밖에서 왔습니다."
                    )
                response_etag, _ = _response_etag(response)
                if response_etag != if_none_match:
                    raise CurationSnapshotContractError("304 ETag가 요청 validator와 다릅니다.")
                return CurationCollectionFetchResult(
                    not_modified=True,
                    source_etag=response_etag,
                    snapshot=None,
                )
            if response.status_code == status.HTTP_409_CONFLICT:
                return None
            if response.status_code == status.HTTP_404_NOT_FOUND:
                raise CurationSnapshotNotFound(str(collection_id))
            if response.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
                raise CurationSnapshotTooLarge(str(collection_id))
            if response.status_code >= 500:
                raise CurationSnapshotUnavailable(
                    f"kor-travel-map curation snapshot HTTP {response.status_code}"
                )
            if response.status_code != status.HTTP_200_OK:
                raise CurationSnapshotServiceProblem(
                    status_code=response.status_code,
                    code=_problem_code(response),
                )

            raw_etag, body_etag = _response_etag(response)
            try:
                page = CurationCollectionDetailSnapshotPage.model_validate(response.json())
            except (ValueError, TypeError) as exc:
                raise CurationSnapshotContractError(
                    "collection snapshot response shape가 contract와 다릅니다."
                ) from exc
            if page.etag != body_etag:
                raise CurationSnapshotContractError(
                    "collection snapshot ETag header/body가 다릅니다."
                )
            if page.collection_id != collection_id:
                raise CurationSnapshotContractError(
                    "collection snapshot identity가 요청과 다릅니다."
                )

            if first_page is None:
                first_page = page
                source_etag = raw_etag
            elif (
                page.collection_id != first_page.collection_id
                or page.row_revision != first_page.row_revision
                or page.collection != first_page.collection
                or page.item_count != first_page.item_count
                or page.item_set_hash_version != first_page.item_set_hash_version
                or page.item_set_hash != first_page.item_set_hash
            ):
                raise CurationSnapshotContractError(
                    "collection snapshot page receipt가 바뀌었습니다."
                )

            for item in page.items:
                if item.curation_item_id in seen_items:
                    raise CurationSnapshotContractError(
                        "collection snapshot item identity가 중복됐습니다."
                    )
                seen_items.add(item.curation_item_id)
                items.append(item)
            if len(items) > page.item_count or len(items) > _COLLECTION_MAX_ITEMS:
                raise CurationSnapshotContractError(
                    "collection snapshot 누적 item 수가 receipt 상한을 초과합니다."
                )

            if page.complete:
                if len(items) != page.item_count:
                    raise CurationSnapshotContractError(
                        "collection snapshot item_count가 실제 set과 다릅니다."
                    )
                assert first_page is not None
                return CurationCollectionFetchResult(
                    not_modified=False,
                    source_etag=source_etag,
                    snapshot=CurationCollectionSnapshotSet(
                        collection_id=first_page.collection_id,
                        row_revision=int(first_page.row_revision),
                        source_etag=source_etag,
                        updated_at=first_page.updated_at,
                        collection=first_page.collection,
                        item_count=first_page.item_count,
                        item_set_hash_version=first_page.item_set_hash_version,
                        item_set_hash=first_page.item_set_hash,
                        items=tuple(items),
                    ),
                )

            next_cursor = page.next_cursor
            if not page.items:
                raise CurationSnapshotContractError(
                    "collection snapshot continuation page가 진행하지 않습니다."
                )
            if next_cursor is None or next_cursor in seen_cursors:
                raise CurationSnapshotContractError(
                    "collection snapshot cursor가 없거나 반복됐습니다."
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor


class CurationCutoverMappingServiceClient:
    """`pinvi:curation-cutover:read` principal에 고정된 maintenance-only client."""

    def __init__(self, http: httpx.AsyncClient, *, token: str, max_attempts: int = 3) -> None:
        if len(token) < 32 or any(character.isspace() for character in token):
            raise ValueError(
                "curation cutover mapping token은 whitespace 없는 32자 이상이어야 합니다."
            )
        if max_attempts < 1:
            raise ValueError("max_attempts는 1 이상이어야 합니다.")
        self._http = http
        self._token = token
        self._max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, *, cursor: str | None) -> httpx.Response:
        params: dict[str, str | int] = {"page_size": _CUTOVER_MAPPING_PAGE_SIZE}
        if cursor is not None:
            params["cursor"] = cursor
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http.get(
                    "/v1/service/curation-cutover/identity-mappings",
                    params=params,
                    headers={_SERVICE_TOKEN_HEADER: self._token},
                )
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise CurationCutoverMappingUnavailable(
                        "kor-travel-map curation cutover mapping network failure"
                    ) from exc
                await asyncio.sleep(0)
                continue
            if response.status_code >= 500 and attempt < self._max_attempts:
                await asyncio.sleep(0)
                continue
            return response
        raise AssertionError("unreachable")

    async def get_identity_mappings(self) -> CurationCutoverMappingSet:
        """Read one closed mapping root; a changing cursor root restarts as a whole."""

        for restart in range(self._max_attempts):
            result = await self._get_once()
            if result is not None:
                return result
            if restart + 1 < self._max_attempts:
                await asyncio.sleep(0)
        raise CurationCutoverMappingServiceProblem(
            status_code=status.HTTP_409_CONFLICT,
            code="CURATION_CUTOVER_MAPPING_CHANGED",
        )

    async def _get_once(self) -> CurationCutoverMappingSet | None:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        seen_legacy_ids: set[uuid.UUID] = set()
        seen_item_ids: set[uuid.UUID] = set()
        mappings: list[CurationCutoverIdentityMapping] = []
        first_page: CurationCutoverIdentityMappingExportPage | None = None
        last_legacy_id: uuid.UUID | None = None

        while True:
            response = await self._get(cursor=cursor)
            if response.status_code == status.HTTP_409_CONFLICT:
                return None
            if response.status_code >= 500:
                raise CurationCutoverMappingUnavailable(
                    f"kor-travel-map curation cutover mapping HTTP {response.status_code}"
                )
            if response.status_code != status.HTTP_200_OK:
                raise CurationCutoverMappingServiceProblem(
                    status_code=response.status_code,
                    code=_problem_code(response),
                )
            try:
                page = CurationCutoverIdentityMappingExportPage.model_validate(response.json())
            except (ValueError, TypeError) as exc:
                raise CurationCutoverMappingContractError(
                    "curation cutover mapping response shape가 contract와 다릅니다."
                ) from exc

            if first_page is None:
                first_page = page
            elif (
                page.mapping_root_version != first_page.mapping_root_version
                or page.mapping_count != first_page.mapping_count
                or page.mapping_root != first_page.mapping_root
            ):
                raise CurationCutoverMappingContractError(
                    "curation cutover mapping page receipt가 바뀌었습니다."
                )

            for mapping in page.mappings:
                if mapping.legacy_curated_feature_id in seen_legacy_ids:
                    raise CurationCutoverMappingContractError(
                        "curation cutover mapping legacy identity가 중복됐습니다."
                    )
                if mapping.curation_item_id in seen_item_ids:
                    raise CurationCutoverMappingContractError(
                        "curation cutover mapping item identity가 중복됐습니다."
                    )
                if (
                    last_legacy_id is not None
                    and mapping.legacy_curated_feature_id.bytes <= last_legacy_id.bytes
                ):
                    raise CurationCutoverMappingContractError(
                        "curation cutover mapping keyset order가 전진하지 않습니다."
                    )
                seen_legacy_ids.add(mapping.legacy_curated_feature_id)
                seen_item_ids.add(mapping.curation_item_id)
                last_legacy_id = mapping.legacy_curated_feature_id
                mappings.append(mapping)

            assert first_page is not None
            if len(mappings) > first_page.mapping_count:
                raise CurationCutoverMappingContractError(
                    "curation cutover mapping 누적 수가 receipt count를 초과합니다."
                )
            if page.complete:
                if len(mappings) != first_page.mapping_count:
                    raise CurationCutoverMappingContractError(
                        "curation cutover mapping count가 실제 set과 다릅니다."
                    )
                return CurationCutoverMappingSet(
                    mapping_root_version=first_page.mapping_root_version,
                    mapping_count=first_page.mapping_count,
                    mapping_root=first_page.mapping_root,
                    mappings=tuple(mappings),
                )

            if not page.mappings:
                raise CurationCutoverMappingContractError(
                    "curation cutover mapping continuation page가 진행하지 않습니다."
                )
            next_cursor = page.next_cursor
            if next_cursor is None or next_cursor in seen_cursors:
                raise CurationCutoverMappingContractError(
                    "curation cutover mapping cursor가 없거나 반복됐습니다."
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor


def create_curation_snapshot_service_client(
    app_settings: Settings,
) -> CurationSnapshotServiceClient | None:
    secret = app_settings.pinvi_kor_travel_map_curation_snapshot_token
    if secret is None:
        return None
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory,
            provider="kor_travel_map_curation_snapshot",
        ),
    )
    return CurationSnapshotServiceClient(
        http,
        token=secret.get_secret_value(),
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
    )


def create_curation_cutover_mapping_service_client(
    app_settings: Settings,
) -> CurationCutoverMappingServiceClient | None:
    """Create the distinct maintenance-fence mapping client only when configured."""

    secret = app_settings.pinvi_kor_travel_map_curation_cutover_mapping_token
    if secret is None:
        return None
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory,
            provider="kor_travel_map_curation_cutover_mapping",
        ),
    )
    return CurationCutoverMappingServiceClient(
        http,
        token=secret.get_secret_value(),
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
    )


@asynccontextmanager
async def curation_snapshot_service_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_curation_snapshot_service_client(settings)
    app.state.curation_snapshot_service_client = client
    if client is None:
        logger.info("kor_travel_map_curation_snapshot.client_disabled")
    else:
        logger.info(
            "kor_travel_map_curation_snapshot.client_ready",
            extra={"base_url": settings.pinvi_kor_travel_map_api_base_url},
        )
    try:
        yield
    finally:
        if client is not None:
            await client.aclose()
        app.state.curation_snapshot_service_client = None


@asynccontextmanager
async def curation_cutover_mapping_service_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_curation_cutover_mapping_service_client(settings)
    app.state.curation_cutover_mapping_service_client = client
    if client is None:
        logger.info("kor_travel_map_curation_cutover_mapping.client_disabled")
    else:
        logger.info(
            "kor_travel_map_curation_cutover_mapping.client_ready",
            extra={"base_url": settings.pinvi_kor_travel_map_api_base_url},
        )
    try:
        yield
    finally:
        if client is not None:
            await client.aclose()
        app.state.curation_cutover_mapping_service_client = None


def get_curation_snapshot_service_client(request: Request) -> CurationSnapshotServiceClient:
    client = getattr(request.app.state, "curation_snapshot_service_client", None)
    if not isinstance(client, CurationSnapshotServiceClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CURATION_SNAPSHOT_SERVICE_UNAVAILABLE",
                "message": "지도 curation snapshot 서비스가 구성되지 않았습니다.",
            },
        )
    return client


def get_curation_cutover_mapping_service_client(
    request: Request,
) -> CurationCutoverMappingServiceClient:
    client = getattr(request.app.state, "curation_cutover_mapping_service_client", None)
    if not isinstance(client, CurationCutoverMappingServiceClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CURATION_CUTOVER_MAPPING_SERVICE_UNAVAILABLE",
                "message": "지도 curation cutover mapping 서비스가 구성되지 않았습니다.",
            },
        )
    return client


CurationSnapshotServiceClientDep = Annotated[
    CurationSnapshotServiceClient,
    Depends(get_curation_snapshot_service_client),
]
CurationCutoverMappingServiceClientDep = Annotated[
    CurationCutoverMappingServiceClient,
    Depends(get_curation_cutover_mapping_service_client),
]

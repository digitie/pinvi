"""canonical curation snapshot 전용 service client 계약."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.clients.kor_travel_map_curation import (
    CurationCollectionFetchResult,
    CurationSnapshotCollection,
    CurationSnapshotContractError,
    CurationSnapshotServiceClient,
)
from app.core.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]
TOKEN = "c" * 32
COLLECTION_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")


def _client(handler: Handler, *, max_attempts: int = 3) -> CurationSnapshotServiceClient:
    return CurationSnapshotServiceClient(
        httpx.AsyncClient(
            base_url="http://kor-travel-map.test",
            transport=httpx.MockTransport(handler),
        ),
        token=TOKEN,
        max_attempts=max_attempts,
    )


def _item(number: int) -> dict[str, Any]:
    item_id = f"20000000-0000-0000-0000-{number:012d}"
    feature_id = f"30000000-0000-0000-0000-{number:012d}"
    collection = {
        "theme_slug": "cafes",
        "theme_name": "카페",
        "title": "서울 카페",
        "edition_key": "2026",
    }
    return {
        "curation_item_id": item_id,
        "collection_id": str(COLLECTION_ID),
        "row_revision": str(number),
        "etag": f"sha256:{number:064x}",
        "updated_at": "2026-08-14T00:00:00Z",
        "collection": collection,
        "item": {
            "feature_id": feature_id,
            "relation": "food_stop",
            "sort_order": number,
            "title": None,
            "summary": "메모",
        },
        "feature": {
            "feature_id": feature_id,
            "name": f"카페 {number}",
            "category": "food",
            "kind": "place",
            "lon": 126.9,
            "lat": 37.5,
            "address": {"road_address": "서울"},
            "detail": {},
            "source_record_key": f"source:{number}",
        },
    }


def _page(
    *,
    items: list[dict[str, Any]],
    cursor: str | None,
    etag_digit: str,
    item_count: int = 2,
) -> dict[str, Any]:
    return {
        "collection_id": str(COLLECTION_ID),
        "row_revision": "7",
        "etag": f"sha256:{etag_digit * 64}",
        "updated_at": "2026-08-14T00:00:00Z",
        "collection": {
            "theme_slug": "cafes",
            "theme_name": "카페",
            "title": "서울 카페",
            "edition_key": "2026",
        },
        "item_count": item_count,
        "item_set_hash_version": "ktm-db-item-set-v1",
        "item_set_hash": "f" * 64,
        "items": items,
        "next_cursor": cursor,
        "complete": cursor is None,
    }


def test_collection_metadata_accepts_map_contract_boundaries() -> None:
    collection = CurationSnapshotCollection(
        theme_slug="s" * 128,
        theme_name="n" * 200,
        title="t" * 300,
        edition_key="e" * 100,
    )
    assert len(collection.theme_slug) == 128
    assert len(collection.theme_name) == 200
    assert len(collection.title) == 300
    assert len(collection.edition_key) == 100


@pytest.mark.parametrize(
    "override",
    [
        {"theme_slug": "s" * 129},
        {"theme_name": "n" * 201},
        {"title": "t" * 301},
        {"edition_key": "e" * 101},
    ],
)
def test_collection_metadata_rejects_values_beyond_map_contract(
    override: dict[str, str],
) -> None:
    payload = {
        "theme_slug": "s" * 128,
        "theme_name": "n" * 200,
        "title": "t" * 300,
        "edition_key": "e" * 100,
        **override,
    }
    with pytest.raises(ValidationError):
        CurationSnapshotCollection.model_validate(payload)


@pytest.mark.asyncio
async def test_collection_snapshot_reads_exact_paged_set_and_uses_first_etag_only() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == TOKEN
        cursor = request.url.params.get("cursor")
        payload = (
            _page(items=[_item(1)], cursor="cursor-1", etag_digit="a")
            if cursor is None
            else _page(items=[_item(2)], cursor=None, etag_digit="b")
        )
        return httpx.Response(
            200,
            json=payload,
            headers={"ETag": f'"{payload["etag"]}"'},
        )

    client = _client(handler)
    result = await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()

    assert result.not_modified is False
    assert result.source_etag == f'"sha256:{"a" * 64}"'
    assert result.snapshot is not None
    assert result.snapshot.item_count == 2
    assert tuple(item.item.sort_order for item in result.snapshot.items) == (1, 2)
    assert len(requests) == 2
    assert requests[0].url.params["page_size"] == "200"
    assert "if-none-match" not in requests[0].headers
    assert "if-none-match" not in requests[1].headers


@pytest.mark.asyncio
async def test_collection_snapshot_304_is_exact_terminal_noop() -> None:
    etag = f'"sha256:{"a" * 64}"'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == etag
        return httpx.Response(304, headers={"ETag": etag})

    client = _client(handler)
    result = await client.get_collection_snapshot(COLLECTION_ID, if_none_match=etag)
    await client.aclose()

    assert result == CurationCollectionFetchResult(
        not_modified=True,
        source_etag=etag,
        snapshot=None,
    )


@pytest.mark.asyncio
async def test_collection_snapshot_restarts_after_cursor_conflict() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(409, json={"code": "CURATION_SNAPSHOT_CHANGED"})
        payload = _page(items=[_item(1), _item(2)], cursor=None, etag_digit="a")
        return httpx.Response(200, json=payload, headers={"ETag": f'"{payload["etag"]}"'})

    client = _client(handler)
    result = await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()

    assert result.snapshot is not None
    assert calls == 2


@pytest.mark.asyncio
async def test_collection_snapshot_rejects_page_receipt_drift() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        payload = (
            _page(items=[_item(1)], cursor="cursor-1", etag_digit="a")
            if cursor is None
            else _page(items=[_item(2)], cursor=None, etag_digit="b")
        )
        if cursor is not None:
            payload["item_set_hash"] = "e" * 64
        return httpx.Response(200, json=payload, headers={"ETag": f'"{payload["etag"]}"'})

    client = _client(handler)
    with pytest.raises(CurationSnapshotContractError, match="page receipt"):
        await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()


@pytest.mark.asyncio
async def test_collection_snapshot_rejects_over_contract_item_count() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _page(
            items=[],
            cursor=None,
            etag_digit="a",
            item_count=2_001,
        )
        return httpx.Response(200, json=payload, headers={"ETag": f'"{payload["etag"]}"'})

    client = _client(handler)
    with pytest.raises(CurationSnapshotContractError, match="response shape"):
        await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()


@pytest.mark.asyncio
async def test_collection_snapshot_rejects_excessive_page_chain() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = _page(
            items=[_item(calls)],
            cursor=f"cursor-{calls}",
            etag_digit="a",
            item_count=11,
        )
        return httpx.Response(200, json=payload, headers={"ETag": f'"{payload["etag"]}"'})

    client = _client(handler)
    with pytest.raises(CurationSnapshotContractError, match="page 수"):
        await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()
    assert calls == 10


@pytest.mark.asyncio
async def test_collection_snapshot_rejects_nonprogressing_page() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _page(
            items=[],
            cursor="cursor-empty",
            etag_digit="a",
            item_count=1,
        )
        return httpx.Response(200, json=payload, headers={"ETag": f'"{payload["etag"]}"'})

    client = _client(handler)
    with pytest.raises(CurationSnapshotContractError, match="진행하지"):
        await client.get_collection_snapshot(COLLECTION_ID)
    await client.aclose()


def test_curation_snapshot_token_is_optional_but_strict_and_role_distinct() -> None:
    loaded = Settings(
        _env_file=None,
        pinvi_environment="test",
        pinvi_kor_travel_map_curation_snapshot_token=TOKEN,
    )
    assert loaded.pinvi_kor_travel_map_curation_snapshot_token is not None

    with pytest.raises(ValidationError, match="at least 32"):
        Settings(
            _env_file=None,
            pinvi_environment="test",
            pinvi_kor_travel_map_curation_snapshot_token="weak",
        )
    with pytest.raises(ValidationError, match="must not reuse"):
        Settings(
            _env_file=None,
            pinvi_environment="test",
            pinvi_kor_travel_map_curation_snapshot_token=TOKEN,
            pinvi_kor_travel_map_admin_proxy_secret=TOKEN,
        )

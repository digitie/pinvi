"""kor-travel-map HTTP client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import (
    FoundFeatureBatchItem,
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapContractError,
    KorTravelMapError,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
    MissingFeatureBatchItem,
    RetiredFeatureBatchItem,
    SuppressedFeatureBatchItem,
    UnchangedFeatureBatchItem,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KorTravelMapClient:
    http = httpx.AsyncClient(
        base_url="http://kor_travel_map.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {"max_attempts": 2, "backoff_base_seconds": 0.0}
    params.update(kwargs)
    return KorTravelMapClient(http, **params)  # type: ignore[arg-type]


def _trip_card(feature_id: str, *, lon: float | None = 126.977) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "kind": "place",
        "name": f"{feature_id} 이름",
        "category": "attraction",
        "lon": lon,
        "lat": 37.579,
        "address": {"road_address": "서울특별시 종로구"},
        "marker_icon": "monument",
        "marker_color": "P-01",
    }


async def test_features_in_bounds_unwraps_data_and_repeats_kind() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"data": {"count": 1, "items": []}, "meta": {}})

    client = _client(handler)
    data = await client.features_in_bounds(
        min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2, kinds=["place", "event"]
    )
    assert data == {"count": 1, "items": []}
    assert seen["path"] == "/v1/features/in-bounds"
    assert "kind=place" in seen["query"] and "kind=event" in seen["query"]
    await client.aclose()


async def test_search_features_uses_v1_path_and_split_bbox() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"data": {"items": [], "next_cursor": None}})

    client = _client(handler)
    await client.search_features(
        q="광안리",
        min_lon=129.0,
        min_lat=35.0,
        max_lon=129.2,
        max_lat=35.2,
        page_size=20,
    )
    assert seen["path"] == "/v1/features/search"
    # ADR-048 clean cut: bbox는 분리 float 4개, pagination은 page_size.
    for token in ("min_lon=129", "min_lat=35", "max_lon=129.2", "max_lat=35.2", "page_size=20"):
        assert token in seen["query"], seen["query"]
    assert "bbox=" not in seen["query"]
    await client.aclose()


async def test_get_feature_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "FEATURE_NOT_FOUND"}})

    client = _client(handler)
    assert await client.get_feature("f_x") is None
    await client.aclose()


async def test_get_feature_returns_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"feature_id": "f_x", "name": "광안리"}})

    client = _client(handler)
    feature = await client.get_feature("f_x")
    assert feature is not None
    assert feature["name"] == "광안리"
    await client.aclose()


async def test_get_features_chunks_and_merges() -> None:
    calls: list[dict[str, Any]] = []

    seen_path: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen_path["path"] = request.url.path
        body = _json.loads(request.content)
        calls.append(body)
        items = []
        for request_item in body["items"]:
            feature_id = request_item["feature_id"]
            if feature_id == "f_found":
                items.append(
                    {
                        "state": "found",
                        "feature_id": feature_id,
                        "row_revision": 10,
                        "trip_card": _trip_card(feature_id),
                    }
                )
            elif feature_id == "f_retired":
                items.append({"state": "retired", "feature_id": feature_id, "row_revision": 11})
            elif feature_id == "f_suppressed":
                items.append({"state": "suppressed", "feature_id": feature_id, "row_revision": 12})
            elif feature_id == "f_missing":
                items.append({"state": "missing", "feature_id": feature_id})
            else:
                items.append(
                    {
                        "state": "unchanged",
                        "feature_id": feature_id,
                        "row_revision": request_item["known_row_revision"],
                    }
                )
        return httpx.Response(200, json={"data": {"items": items}, "meta": {}})

    client = _client(handler, batch_chunk_size=2)
    data = await client.get_features(
        ["f_found", "f_retired", "f_suppressed", "f_missing", "f_unchanged"],
        known_row_revisions={"f_unchanged": 13},
    )
    assert seen_path["path"] == "/v1/features/batch"  # #318: /pinvi 제거
    assert len(calls) == 3
    assert all(call["projection"] == "trip_card" for call in calls)
    assert calls[-1]["items"] == [{"feature_id": "f_unchanged", "known_row_revision": 13}]
    assert isinstance(data["f_found"], FoundFeatureBatchItem)
    assert data["f_found"].trip_card.name == "f_found 이름"
    assert isinstance(data["f_retired"], RetiredFeatureBatchItem)
    assert isinstance(data["f_suppressed"], SuppressedFeatureBatchItem)
    assert isinstance(data["f_missing"], MissingFeatureBatchItem)
    assert isinstance(data["f_unchanged"], UnchangedFeatureBatchItem)
    await client.aclose()


@pytest.mark.parametrize(
    ("batch_data", "known_row_revisions"),
    [
        ({}, None),
        ({"items": "not-an-array"}, None),
        ({"items": []}, None),
        ({"items": [{"state": "missing", "feature_id": "f_other"}]}, None),
        (
            {"items": [{"state": "missing", "feature_id": "f_1", "row_revision": 1}]},
            None,
        ),
        ({"items": [{"state": "future", "feature_id": "f_1"}]}, None),
        (
            {
                "items": [
                    {
                        "state": "found",
                        "feature_id": "f_1",
                        "row_revision": 1,
                        "trip_card": {"feature_id": "f_1"},
                    }
                ]
            },
            None,
        ),
        (
            {
                "items": [
                    {
                        "state": "found",
                        "feature_id": "f_1",
                        "row_revision": 1,
                        "trip_card": _trip_card("f_other"),
                    }
                ]
            },
            None,
        ),
        (
            {
                "items": [
                    {
                        "state": "found",
                        "feature_id": "f_1",
                        "row_revision": 1,
                        "trip_card": {**_trip_card("f_1"), "private_payload": "leak"},
                    }
                ]
            },
            None,
        ),
        (
            {"items": [{"state": "unchanged", "feature_id": "f_1", "row_revision": 2}]},
            {"f_1": 1},
        ),
        (
            {
                "items": [
                    {
                        "state": "found",
                        "feature_id": "f_1",
                        "row_revision": 1,
                        "trip_card": _trip_card("f_1"),
                    }
                ]
            },
            {"f_1": 1},
        ),
    ],
    ids=[
        "missing-items",
        "items-not-array",
        "incomplete-partition",
        "unknown-id",
        "missing-extra-key",
        "future-state",
        "incomplete-trip-card",
        "mismatched-trip-card-id",
        "extra-trip-card-field",
        "wrong-unchanged-validator",
        "ignored-matching-validator",
    ],
)
async def test_get_features_rejects_invalid_response_partition(
    batch_data: dict[str, Any],
    known_row_revisions: dict[str, int] | None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": batch_data, "meta": {}},
        )

    client = _client(handler)
    with pytest.raises(KorTravelMapContractError):
        await client.get_features(["f_1"], known_row_revisions=known_row_revisions)
    await client.aclose()


async def test_get_features_deduplicates_input_and_skips_empty_request() -> None:
    calls: list[list[dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        request_items = _json.loads(request.content)["items"]
        calls.append(request_items)
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "state": "found",
                            "feature_id": item["feature_id"],
                            "row_revision": 1,
                            "trip_card": _trip_card(item["feature_id"]),
                        }
                        for item in request_items
                    ],
                },
                "meta": {},
            },
        )

    client = _client(handler)
    assert await client.get_features([]) == {}
    assert calls == []
    result = await client.get_features(["f_1", "f_1"])
    assert list(result) == ["f_1"]
    assert isinstance(result["f_1"], FoundFeatureBatchItem)
    assert calls == [[{"feature_id": "f_1"}]]
    await client.aclose()


async def test_get_features_rejects_duplicate_found_json_member() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'{"data":{"items":[{"state":"missing","state":"found",'
                b'"feature_id":"f_1"}]},"meta":{}}'
            ),
            headers={"content-type": "application/json"},
        )

    client = _client(handler)
    with pytest.raises(KorTravelMapError, match="중복 key"):
        await client.get_features(["f_1"])
    await client.aclose()


@pytest.mark.parametrize("raw_number", ["NaN", "Infinity", "-Infinity", "1e400"])
async def test_get_features_rejects_non_finite_json_numbers(raw_number: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                '{"data":{"items":[{"state":"found","feature_id":"f_1","row_revision":1,'
                '"trip_card":{"feature_id":"f_1","kind":"place","name":"장소",'
                '"category":"attraction","lon":'
                f"{raw_number}"
                ',"lat":37.5,"address":{},"marker_icon":null,"marker_color":null}}]},'
                '"meta":{}}'
            ).encode(),
            headers={"content-type": "application/json"},
        )

    client = _client(handler)
    with pytest.raises(KorTravelMapContractError, match=r"비유한 수|범위를 벗어난 실수"):
        await client.get_features(["f_1"])
    await client.aclose()


@pytest.mark.parametrize(
    "known_row_revisions",
    [
        {"f_other": 1},
        {"f_1": 0},
        {"f_1": True},
    ],
)
async def test_get_features_rejects_invalid_known_revisions(
    known_row_revisions: dict[str, int],
) -> None:
    client = _client(lambda request: httpx.Response(500))
    with pytest.raises(ValueError, match="known_row_revisions"):
        await client.get_features(["f_1"], known_row_revisions=known_row_revisions)
    await client.aclose()


async def test_get_features_is_all_or_nothing_across_chunks() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            data = {
                "items": [
                    {
                        "state": "found",
                        "feature_id": "f_1",
                        "row_revision": 1,
                        "trip_card": _trip_card("f_1"),
                    }
                ]
            }
        else:
            data = {"items": [{"state": "future", "feature_id": "f_2"}]}
        return httpx.Response(200, json={"data": data, "meta": {}})

    client = _client(handler, batch_chunk_size=1)
    with pytest.raises(KorTravelMapContractError, match="state"):
        await client.get_features(["f_1", "f_2"])
    assert calls == 2
    await client.aclose()


# --- ADR-048 / kor_travel_map 0e45bd7 계약 (T-181) -------------------------------


async def test_in_bounds_sends_max_items_and_threads_cluster_unit() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = str(request.url.query, "utf-8")
        # granularity는 meta.cluster.cluster_unit로 옴 (data.cluster_unit 폐기).
        return httpx.Response(
            200,
            json={
                "data": {"clusters": [], "items": []},
                "meta": {"request_id": "r1", "cluster": {"cluster_unit": "sigungu"}},
            },
        )

    client = _client(handler)
    data = await client.features_in_bounds(
        min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2, max_items=1000
    )
    assert "max_items=1000" in seen["query"]
    assert "limit=" not in seen["query"]  # 구 limit 폐기
    assert data["cluster_unit"] == "sigungu"  # meta.cluster → data re-projection
    await client.aclose()


async def test_nearby_threads_meta_page_cursor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {"origin": {}, "items": [{"feature_id": "f1", "distance_m": 12}]},
                "meta": {
                    "request_id": "r2",
                    "page": {"page_size": 20, "next_cursor": "c2", "total": None},
                },
            },
        )

    client = _client(handler)
    data = await client.features_nearby(lon=129.0, lat=35.0, radius_m=500)
    # 구 data.next_cursor 폐기 → meta.page.next_cursor를 data로 threading.
    assert data["next_cursor"] == "c2"
    assert data["total"] is None
    assert data["items"][0]["distance_m"] == 12
    await client.aclose()


async def test_search_threads_meta_page_and_include_total() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(
            200,
            json={
                "data": {"items": []},
                "meta": {
                    "request_id": "r3",
                    "page": {"page_size": 50, "next_cursor": None, "total": 7},
                },
            },
        )

    client = _client(handler)
    data = await client.search_features(q="광안리", include_total=True)
    assert "include_total=true" in seen["query"].lower()
    assert data["next_cursor"] is None
    assert data["total"] == 7
    await client.aclose()


async def test_public_beaches_uses_public_path_and_threads_page_meta() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(
            200,
            json={
                "data": {"items": [{"feature_id": "f_beach"}]},
                "meta": {"page": {"page_size": 20, "next_cursor": "n2", "total": 3}},
            },
        )

    client = _client(handler)
    data = await client.public_beaches(
        sido_code="26",
        sigungu_code="26110",
        q="광안리",
        page_size=20,
        cursor="c1",
    )
    assert seen["path"] == "/v1/public/beaches"
    for token in (
        "sido_code=26",
        "sigungu_code=26110",
        "q=",
        "page_size=20",
        "cursor=c1",
    ):
        assert token in seen["query"], seen["query"]
    assert "include_quality" not in seen["query"]
    assert "include_forecast" not in seen["query"]
    assert data["next_cursor"] == "n2"
    assert data["total"] == 3
    await client.aclose()


async def test_public_marker_and_detail_paths() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.path.endswith("/map-markers"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "layer_key": "beach",
                        "display_name": "해수욕장",
                        "marker_icon": "swimming",
                        "marker_color": "P-07",
                        "items": [],
                    },
                    "meta": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "feature_id": "f_beach",
                    "display_name": "광안리 해수욕장",
                    "address": {},
                    "source_providers": ["khoa"],
                    "updated_at": "2026-06-12T00:00:00+09:00",
                },
                "meta": {},
            },
        )

    client = _client(handler)
    await client.public_beach_markers(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    beach = await client.get_public_beach("f_beach")
    assert beach is not None
    assert [url.path for url in seen] == [
        "/v1/public/beaches/map-markers",
        "/v1/public/beaches/f_beach",
    ]
    detail_query = str(seen[1].query, "utf-8")
    assert detail_query == ""
    assert "include_quality" not in detail_query
    assert "include_forecast" not in detail_query
    await client.aclose()


async def test_public_festivals_uses_public_paths() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/monthly"):
            return httpx.Response(
                200,
                json={
                    "data": {"months": [{"year": 2026, "month": 6, "count": 1}], "items": []},
                    "meta": {"page": {"page_size": 12, "next_cursor": None, "total": 1}},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "layer_key": "festival",
                    "display_name": "축제",
                    "marker_icon": "star",
                    "marker_color": "P-11",
                    "items": [],
                },
                "meta": {},
            },
        )

    client = _client(handler)
    monthly = await client.public_festivals_monthly(year=2026, month=6, page_size=12)
    await client.public_festival_markers(year=2026, month=6, max_items=100)
    assert monthly["total"] == 1
    assert seen == ["/v1/public/festivals/monthly", "/v1/public/festivals/map-markers"]
    await client.aclose()


async def test_public_detail_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "FEATURE_NOT_FOUND"})

    client = _client(handler)
    assert await client.get_public_beach("missing") is None
    assert await client.get_public_festival("missing") is None
    await client.aclose()


async def test_problem_json_top_level_code_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # RFC7807 problem+json — 머신 코드는 top-level 확장 `code`.
        return httpx.Response(
            422,
            headers={"Content-Type": "application/problem+json"},
            json={
                "type": "about:blank",
                "title": "Unprocessable Entity",
                "status": 422,
                "detail": "bbox invalid",
                "code": "INVALID_BBOX",
                "request_id": "r4",
            },
        )

    client = _client(handler)
    with pytest.raises(KorTravelMapBadRequest) as exc:
        await client.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert exc.value.code == "INVALID_BBOX"
    await client.aclose()


async def test_5xx_retries_then_unavailable() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"error": {"code": "UPSTREAM_UNAVAILABLE"}})

    client = _client(handler, max_attempts=3)
    with pytest.raises(KorTravelMapUnavailable):
        await client.get_feature("f_x")
    assert attempts["n"] == 3
    await client.aclose()


async def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable):
        await client.healthz()
    await client.aclose()


async def test_rate_limited_429_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "15"}, json={"error": {"code": "RATE_LIMITED"}}
        )

    client = _client(handler)
    with pytest.raises(KorTravelMapRateLimited) as exc:
        await client.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert exc.value.retry_after_seconds == 15
    await client.aclose()


async def test_422_raises_bad_request_with_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": {"code": "INVALID_BBOX"}})

    client = _client(handler)
    with pytest.raises(KorTravelMapBadRequest) as exc:
        await client.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert exc.value.code == "INVALID_BBOX"
    await client.aclose()


async def test_batch_404_path_raises_contract_error() -> None:
    # batch endpoint 자체 404는 item-level missing이 아니라 배포/계약 skew다.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "FEATURE_NOT_FOUND"}})

    client = _client(handler)
    with pytest.raises(KorTravelMapContractError, match="batch endpoint"):
        await client.get_features(["f_1"])
    await client.aclose()


async def test_service_token_header() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token")
        return httpx.Response(200, json={"data": {"count": 0, "items": []}})

    with_token = _client(handler, service_token="secret-abc")
    await with_token.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert seen["token"] == "secret-abc"
    await with_token.aclose()

    without = _client(handler)
    await without.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert seen["token"] is None
    await without.aclose()


async def test_public_api_key_header_added_when_service_token_absent() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query_key"] = request.url.params.get("key")
        seen["api_key"] = request.headers.get("X-Kor-Travel-Map-Api-Key")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token")
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _client(handler, public_api_key="public-key-123")
    await client.search_features(q="광안리")
    assert seen == {"query_key": None, "api_key": "public-key-123", "token": None}
    await client.aclose()


async def test_service_token_suppresses_public_api_key_header() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query_key"] = request.url.params.get("key")
        seen["api_key"] = request.headers.get("X-Kor-Travel-Map-Api-Key")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token")
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _client(handler, service_token="svc-tok", public_api_key="public-key-123")
    await client.search_features(q="광안리")
    assert seen == {"query_key": None, "api_key": None, "token": "svc-tok"}
    await client.aclose()


@pytest.mark.parametrize(
    ("service_token", "public_api_key", "expected_token"),
    [
        ("svc-only", "", "svc-only"),
        ("", "public-only", None),
        ("svc-both", "public-both", "svc-both"),
    ],
    ids=["service-only", "public-only", "both"],
)
async def test_batch_is_service_token_only(
    service_token: str,
    public_api_key: str,
    expected_token: str | None,
) -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query_key"] = request.url.params.get("key")
        seen["api_key"] = request.headers.get("X-Kor-Travel-Map-Api-Key")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token")
        return httpx.Response(
            200,
            json={
                "data": {"items": [{"state": "missing", "feature_id": "f_1"}]},
                "meta": {},
            },
        )

    client = _client(
        handler,
        service_token=service_token,
        public_api_key=public_api_key,
    )
    result = await client.get_features(["f_1"])
    assert isinstance(result["f_1"], MissingFeatureBatchItem)
    assert seen == {"query_key": None, "api_key": None, "token": expected_token}
    await client.aclose()


def test_deploy_contract_wires_map_user_credentials_to_api_only() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    api_block, non_api_block = compose.split("  app-web:", maxsplit=1)
    expected_compose_lines = {
        "PINVI_KOR_TRAVEL_MAP_API_BASE_URL": (
            "PINVI_KOR_TRAVEL_MAP_API_BASE_URL: "
            "${PINVI_KOR_TRAVEL_MAP_API_BASE_URL:-http://host.docker.internal:12701}"
        ),
        "PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN": (
            "PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN: ${PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN:-}"
        ),
        "PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY": (
            "PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY: ${PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY:-}"
        ),
    }
    for env_name, compose_line in expected_compose_lines.items():
        assert compose_line in api_block
        assert env_name not in non_api_block

    for relative in (".env.example", "apps/api/.env.example", "infra/.env.prod.example"):
        example = (root / relative).read_text(encoding="utf-8")
        for env_name in expected_compose_lines:
            assert f"{env_name}=" in example
        public_key_context = example.split("PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY=", maxsplit=1)[
            0
        ].rsplit("\n", maxsplit=2)
        assert "X-Kor-Travel-Map-Api-Key" in "\n".join(public_key_context)
        assert "query" not in "\n".join(public_key_context).lower()

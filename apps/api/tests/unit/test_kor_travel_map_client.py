"""kor-travel-map HTTP client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapFeatureNotFound,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
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
    calls: list[list[str]] = []

    seen_path: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen_path["path"] = request.url.path
        body = _json.loads(request.content)
        ids = body["feature_ids"]
        calls.append(ids)
        found = {fid: {"feature_id": fid} for fid in ids if fid != "f_missing"}
        missing = [fid for fid in ids if fid == "f_missing"]
        # ADR-048: id-keyed map 키는 `found`(구 `items`).
        return httpx.Response(200, json={"data": {"found": found, "missing": missing}, "meta": {}})

    client = _client(handler, batch_chunk_size=2)
    data = await client.get_features(["f_1", "f_2", "f_missing"])
    assert seen_path["path"] == "/v1/features/batch"  # #318: /pinvi 제거
    assert len(calls) == 2  # 2 + 1 청크
    assert set(data["found"]) == {"f_1", "f_2"}
    assert data["missing"] == ["f_missing"]
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
        include_quality=True,
        include_forecast=True,
    )
    assert seen["path"] == "/v1/public/beaches"
    for token in (
        "sido_code=26",
        "sigungu_code=26110",
        "q=",
        "page_size=20",
        "cursor=c1",
        "include_quality=true",
        "include_forecast=true",
    ):
        assert token in seen["query"], seen["query"]
    assert data["next_cursor"] == "n2"
    assert data["total"] == 3
    await client.aclose()


async def test_public_marker_and_detail_paths() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
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
    assert seen == ["/v1/public/beaches/map-markers", "/v1/public/beaches/f_beach"]
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


async def test_curated_pinvi_copy_uses_public_snapshot_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "data": {
                    "curated_feature_id": "cf_1",
                    "version": 3,
                    "etag": "sha256:abc",
                    "updated_at": "2026-06-12T00:00:00+09:00",
                    "theme": {},
                    "plan": {"title": "부산 코스"},
                    "source": {},
                    "items": [],
                },
                "meta": {},
            },
        )

    client = _client(handler)
    snapshot = await client.get_curated_pinvi_copy("cf_1")
    assert seen["path"] == "/v1/curated-features/cf_1/pinvi-copy"
    assert snapshot["curated_feature_id"] == "cf_1"
    assert snapshot["etag"] == "sha256:abc"
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


async def test_batch_404_path_raises_not_found() -> None:
    # batch는 get_feature와 달리 404를 도메인 예외로 올린다(셰입 보장).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "FEATURE_NOT_FOUND"}})

    client = _client(handler)
    with pytest.raises(KorTravelMapFeatureNotFound):
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

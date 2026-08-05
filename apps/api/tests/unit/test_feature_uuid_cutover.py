"""alias-map client·검증된 이관 service 계약 테스트 (T-VN-32C)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map_alias_map import (
    AliasMapChecksum,
    AliasMapContractError,
    KorTravelMapAliasMapClient,
)
from app.core.feature_alias_contract import (
    FeatureAliasRow,
    alias_map_merkle_root,
    derive_feature_uuid,
)
from app.services.feature_uuid_cutover import (
    CUTOVER_TARGETS,
    FeatureUuidCutoverVerificationError,
    pull_verified_alias_map,
    run_feature_uuid_cutover,
)

_ALIASES = [
    "f_1168010100_p_3c0c2820e96d28d3",
    "f_global_e_0123456789abcdef",
    "f_global_w_00ff00ff00ff00ff",
]


def _rows() -> list[FeatureAliasRow]:
    return [
        FeatureAliasRow(
            alias=alias,
            feature_uuid=derive_feature_uuid(alias),
            alias_kind="legacy_feature_id",
        )
        for alias in _ALIASES
    ]


def _row_json(row: FeatureAliasRow) -> dict[str, str]:
    return {
        "alias": row.alias,
        "feature_uuid": str(row.feature_uuid),
        "alias_kind": row.alias_kind,
    }


def _serve_alias_map(
    rows: list[FeatureAliasRow],
    *,
    checksum_root: bytes | None = None,
    alias_count: int | None = None,
    page_size: int = 2,
) -> KorTravelMapAliasMapClient:
    """canonical keyset 페이지·checksum을 내는 in-memory Map surface."""
    ordered = sorted(rows, key=lambda row: row.alias.encode("utf-8"))
    root = checksum_root if checksum_root is not None else alias_map_merkle_root(rows)
    count = alias_count if alias_count is not None else len(rows)

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == "token-1"
        meta = {"duration_ms": 1, "request_id": "t"}
        if request.url.path.endswith("/checksum"):
            data = {
                "schema_version": "feature-alias-map-v1",
                "alias_count": count,
                "merkle_root": root.hex(),
            }
            return httpx.Response(200, json={"data": data, "meta": meta})
        after = request.url.params.get("after_alias")
        limit = min(int(request.url.params.get("limit", "1000")), page_size)
        remaining = [row for row in ordered if after is None or row.alias.encode() > after.encode()]
        page = remaining[:limit]
        has_more = len(remaining) > len(page)
        data = {
            "schema_version": "feature-alias-map-v1",
            "rows": [_row_json(row) for row in page],
            "has_more": has_more,
            "next_after_alias": page[-1].alias if has_more and page else None,
        }
        return httpx.Response(200, json={"data": data, "meta": meta})

    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(_handler))
    return KorTravelMapAliasMapClient(http, service_token="token-1")


async def test_client_traverses_keyset_pages_and_parses_rows() -> None:
    client = _serve_alias_map(_rows(), page_size=2)
    rows = await client.fetch_all_rows(page_limit=2)
    assert [row.alias for row in rows] == sorted(_ALIASES)
    checksum = await client.fetch_checksum()
    assert checksum == AliasMapChecksum(alias_count=3, merkle_root=alias_map_merkle_root(rows))
    await client.aclose()


async def test_client_rejects_wrong_schema_version_and_bad_rows() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/checksum"):
            data = {"schema_version": "v2", "alias_count": 0, "merkle_root": "00" * 32}
        else:
            data = {
                "schema_version": "feature-alias-map-v1",
                "rows": [
                    {"alias": " pad ", "feature_uuid": "x", "alias_kind": "legacy_feature_id"}
                ],
                "has_more": False,
                "next_after_alias": None,
            }
        return httpx.Response(200, json={"data": data, "meta": {}})

    client = KorTravelMapAliasMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(_handler)),
        service_token="token-1",
    )
    with pytest.raises(AliasMapContractError, match="schema_version"):
        await client.fetch_checksum()
    with pytest.raises(AliasMapContractError, match="canonical"):
        await client.fetch_page(after_alias=None)
    await client.aclose()


async def test_client_rejects_non_advancing_keyset() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        data = {
            "schema_version": "feature-alias-map-v1",
            "rows": [_row_json(_rows()[0])],
            "has_more": True,
            "next_after_alias": _rows()[0].alias,
        }
        return httpx.Response(200, json={"data": data, "meta": {}})

    client = KorTravelMapAliasMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(_handler)),
        service_token="token-1",
    )
    # 첫 페이지 뒤 keyset이 전진하지 않으면(같은 next) 무한 순회 대신 중단한다.
    with pytest.raises(AliasMapContractError, match="전진"):
        await client.fetch_all_rows(page_limit=1)
    await client.aclose()


async def test_pull_verified_alias_map_fails_close_on_checksum_mismatch() -> None:
    rows = _rows()
    client = _serve_alias_map(rows, checksum_root=b"\x00" * 32)
    with pytest.raises(FeatureUuidCutoverVerificationError, match="checksum"):
        await pull_verified_alias_map(client)
    await client.aclose()

    client = _serve_alias_map(rows, alias_count=99)
    with pytest.raises(FeatureUuidCutoverVerificationError, match="checksum"):
        await pull_verified_alias_map(client)
    await client.aclose()


class _FakeResult:
    def __init__(self, *, values: list[str] | None = None, rowcount: int = 0) -> None:
        self._values = values or []
        self.rowcount = rowcount

    def scalars(self) -> list[str]:
        return self._values


class _FakeSession:
    """SELECT DISTINCT/UPDATE 두 SQL 형태만 아는 기록형 session."""

    def __init__(self, refs_by_table: dict[str, list[str]]) -> None:
        self._refs_by_table = refs_by_table
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        if sql.lstrip().startswith("SELECT DISTINCT"):
            table = sql.split("FROM app.")[1].split()[0]
            return _FakeResult(values=self._refs_by_table.get(table, []))
        assert params is not None
        self.updates.append((sql, params))
        return _FakeResult(values=["1"])


async def test_run_cutover_rewrites_matched_refs_and_reports_unmatched() -> None:
    rows = _rows()
    client = _serve_alias_map(rows)
    session = _FakeSession(
        {
            "trip_day_pois": [_ALIASES[0], "f_stale_gone"],
            "curated_plan_pois": [_ALIASES[1]],
            "feature_suggestions": [],
        }
    )
    report = await run_feature_uuid_cutover(session, client)  # type: ignore[arg-type]
    await client.aclose()

    assert report.alias_count == 3
    assert report.merkle_root_hex == alias_map_merkle_root(rows).hex()
    by_table = {table.table: table for table in report.tables}
    assert {table for table, _, _ in CUTOVER_TARGETS} == set(by_table)
    assert by_table["trip_day_pois"].mapped_refs == 1
    assert by_table["trip_day_pois"].updated_rows == 1
    assert by_table["trip_day_pois"].unmatched_refs == ("f_stale_gone",)
    assert by_table["trip_day_pois"].unmatched_total == 1
    assert by_table["curated_plan_pois"].mapped_refs == 1
    assert by_table["feature_suggestions"].distinct_refs == 0
    # UPDATE는 매칭된 참조에만, 검증 통과한 map 값으로만 나간다 (이 fixture의
    # map은 파생 세대 벡터라 파생값과 일치 — 역사 앵커).
    assert len(session.updates) == 2
    for sql, params in session.updates:
        assert "SET" in sql
        assert params["feature_uuid"] == derive_feature_uuid(params["ref"])


async def test_uuid_literal_refs_resolve_to_themselves() -> None:
    """Map 값 전환(0083) 이후 저장된 canonical UUID 참조는 자기 자신이 정본이다.

    alias map에는 legacy alias만 실리므로 UUID 리터럴은 map 미포함 — 종전에는
    영구 unmatched로 방치됐다. canonical 형태만 인정하고 대문자/비정규 표기는
    여전히 unmatched다.
    """
    import uuid as uuid_module

    rows = _rows()
    client = _serve_alias_map(rows)
    literal = "01890a5d-ac96-774b-bcce-b302099a8057"
    session = _FakeSession(
        {
            "trip_day_pois": [
                literal,
                "01890A5D-AC96-774B-BCCE-B302099A8057",  # 대문자 — 비정규
                "f_stale_gone",
            ],
            "curated_plan_pois": [],
            "feature_suggestions": [],
        }
    )
    report = await run_feature_uuid_cutover(session, client)  # type: ignore[arg-type]
    await client.aclose()

    trip = {table.table: table for table in report.tables}["trip_day_pois"]
    assert trip.mapped_refs == 1
    assert trip.updated_rows == 1
    assert set(trip.unmatched_refs) == {
        "01890A5D-AC96-774B-BCCE-B302099A8057",
        "f_stale_gone",
    }
    [(_sql, params)] = session.updates
    assert params["ref"] == literal
    assert params["feature_uuid"] == uuid_module.UUID(literal)


async def test_run_cutover_dry_run_writes_nothing() -> None:
    rows = _rows()
    client = _serve_alias_map(rows)
    session = _FakeSession({"trip_day_pois": [_ALIASES[0]]})
    report = await run_feature_uuid_cutover(session, client, dry_run=True)  # type: ignore[arg-type]
    await client.aclose()
    assert report.dry_run is True
    assert session.updates == []
    assert report.tables[0].mapped_refs == 1
    assert report.tables[0].updated_rows == 0


async def test_run_cutover_applies_nothing_when_verification_fails() -> None:
    client = _serve_alias_map(_rows(), checksum_root=b"\x11" * 32)
    session = _FakeSession({"trip_day_pois": [_ALIASES[0]]})
    with pytest.raises(FeatureUuidCutoverVerificationError):
        await run_feature_uuid_cutover(session, client)  # type: ignore[arg-type]
    await client.aclose()
    assert session.updates == []


def test_serialized_row_shape_matches_vendored_golden_fields() -> None:
    golden = json.loads(
        (
            Path(__file__).resolve().parent.parent / "contract" / "feature-alias-map-v1-golden.json"
        ).read_text(encoding="utf-8")
    )
    row_fields = set(golden["merkle_v1"]["rows"][0])
    assert {"alias", "feature_uuid", "alias_kind"} <= row_fields

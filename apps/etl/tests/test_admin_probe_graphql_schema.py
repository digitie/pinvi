"""API의 Admin Dagster live query가 **이 lock의 dagster_graphql 스키마**에서 유효한지 본다.

`apps/api/app/services/admin_etl.py`의 `_PINVI_DAGSTER_LIVE_QUERY`는 Dagster webserver에
보내는 GraphQL 문자열이다. API 단위 테스트는 응답을 흉내 낼 뿐이라, 필드 이름·인자·
입력 타입(`RepositorySelector`, `RunsFilter`)이 실제 스키마와 어긋나도 초록이다 — 운영에서
`degraded`로만 드러난다. API 환경에는 dagster가 없으므로 검증은 dagster_graphql이
설치된 ETL 환경(= 운영 webserver와 같은 lock)에서 한다.

query는 import하지 않고 소스에서 상수를 읽는다(API 패키지는 이 환경에 없다).
"""

from __future__ import annotations

import ast
from pathlib import Path

from graphql import GraphQLSchema, parse, validate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ADMIN_ETL = _REPO_ROOT / "apps" / "api" / "app" / "services" / "admin_etl.py"
_QUERY_NAME = "_PINVI_DAGSTER_LIVE_QUERY"


def _live_query() -> str:
    module = ast.parse(_ADMIN_ETL.read_text(encoding="utf-8"))
    values = [
        node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == _QUERY_NAME for t in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert len(values) == 1, f"문자열 상수 {_QUERY_NAME}를 정확히 하나 찾지 못했다: {_ADMIN_ETL}"
    return values[0]


def _dagster_schema() -> GraphQLSchema:
    from dagster_graphql.schema import create_schema

    schema = create_schema().graphql_schema
    assert isinstance(schema, GraphQLSchema)
    return schema


def test_the_admin_live_query_is_valid_against_the_locked_dagster_schema() -> None:
    errors = validate(_dagster_schema(), parse(_live_query()))
    assert errors == [], [error.message for error in errors]


def test_the_schema_check_rejects_an_unknown_field() -> None:
    """검증이 공허하지 않다 — 스키마에 없는 필드는 거부된다."""
    broken = _live_query().replace("assetNodes { groupName }", "assetNodes { noSuchField }")
    assert broken != _live_query()
    errors = validate(_dagster_schema(), parse(broken))
    assert any("noSuchField" in error.message for error in errors)

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    ColumnElement,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    and_,
    asc,
    cast,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.sql.type_api import TypeEngine

from app.core.json_types import JsonValue
from app.db.base import Base

EXCLUDED_ADMIN_TABLES = {"users", "sessions", "trips", "trip_days"}
PAGE_SIZE_OPTIONS = {50, 100, 200, 500}
DEFAULT_PAGE_SIZE = 100
SORTABLE_DEFAULT_COLUMNS = ("created_at", "collected_at", "updated_at", "id")


class AdminDatasetColumnData(TypedDict):
    name: str
    type: str
    nullable: bool
    searchable: bool
    filterable: bool
    sortable: bool


class AdminDatasetSummaryData(TypedDict):
    table_name: str
    row_count: int
    columns: list[AdminDatasetColumnData]


class AdminDatasetRowsData(TypedDict):
    table_name: str
    page: int
    limit: int
    total: int
    columns: list[AdminDatasetColumnData]
    rows: list[dict[str, JsonValue]]


def get_admin_dataset_tables() -> dict[str, Table]:
    return {
        table_name: table
        for table_name, table in Base.metadata.tables.items()
        if table_name not in EXCLUDED_ADMIN_TABLES
    }


def list_admin_datasets(db: Session) -> list[AdminDatasetSummaryData]:
    datasets: list[AdminDatasetSummaryData] = []
    for table_name, table in sorted(get_admin_dataset_tables().items()):
        row_count = db.scalar(select(func.count()).select_from(table))
        datasets.append(
            {
                "table_name": table_name,
                "row_count": int(row_count or 0),
                "columns": [_describe_column(column) for column in table.c],
            }
        )
    return datasets


def query_admin_dataset_rows(
    db: Session,
    *,
    table_name: str,
    page: int,
    limit: int,
    search: str | None,
    sort_by: str | None,
    sort_dir: str,
    filters: Mapping[str, str],
) -> AdminDatasetRowsData:
    table = _get_table_or_raise(table_name)
    resolved_limit = limit if limit in PAGE_SIZE_OPTIONS else DEFAULT_PAGE_SIZE
    resolved_page = max(page, 1)
    offset = (resolved_page - 1) * resolved_limit

    where_clauses = _build_where_clauses(table, search=search, filters=filters)
    where_clause = and_(*where_clauses) if where_clauses else None

    selected_columns = [
        func.ST_AsText(column).label(column.name) if _is_geometry_type(column.type) else column
        for column in table.c
    ]
    stmt = select(*selected_columns).select_from(table)
    count_stmt = select(func.count()).select_from(table)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
        count_stmt = count_stmt.where(where_clause)

    sort_column: ColumnElement[Any] | None = table.c.get(sort_by) if sort_by else None
    if sort_column is None or not _is_sortable_type(sort_column.type):
        sort_column = _default_sort_column(table)
    if sort_column is not None:
        stmt = stmt.order_by(desc(sort_column) if sort_dir == "desc" else asc(sort_column))

    stmt = stmt.limit(resolved_limit).offset(offset)

    total = int(db.scalar(count_stmt) or 0)
    rows: list[dict[str, JsonValue]] = [
        {key: _serialize_value(value) for key, value in row._mapping.items()}
        for row in db.execute(stmt)
    ]
    return {
        "table_name": table_name,
        "page": resolved_page,
        "limit": resolved_limit,
        "total": total,
        "columns": [_describe_column(column) for column in table.c],
        "rows": rows,
    }


def _get_table_or_raise(table_name: str) -> Table:
    tables = get_admin_dataset_tables()
    table = tables.get(table_name)
    if table is None:
        raise KeyError(table_name)
    return table


def _build_where_clauses(
    table: Table,
    *,
    search: str | None,
    filters: Mapping[str, str],
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        search_clauses = [
            cast(column, String).ilike(pattern)
            for column in table.c
            if _is_searchable_type(column.type)
        ]
        if search_clauses:
            clauses.append(or_(*search_clauses))

    for column_name, filter_value in filters.items():
        normalized_value = filter_value.strip()
        column = table.c.get(column_name)
        if not normalized_value or column is None or not _is_filterable_type(column.type):
            continue
        clauses.append(cast(column, String).ilike(f"%{normalized_value}%"))

    return clauses


def _default_sort_column(table: Table) -> ColumnElement[Any] | None:
    for column_name in SORTABLE_DEFAULT_COLUMNS:
        column = table.c.get(column_name)
        if column is not None and _is_sortable_type(column.type):
            return column
    primary_key_columns = list(table.primary_key.columns)
    if primary_key_columns:
        return primary_key_columns[0]
    return None


def _describe_column(column: ColumnElement[Any]) -> AdminDatasetColumnData:
    return {
        "name": column.name,
        "type": str(column.type),
        "nullable": bool(getattr(column, "nullable", True)),
        "searchable": _is_searchable_type(column.type),
        "filterable": _is_filterable_type(column.type),
        "sortable": _is_sortable_type(column.type),
    }


def _is_geometry_type(column_type: TypeEngine[Any]) -> bool:
    return isinstance(column_type, Geometry)


def _is_json_type(column_type: TypeEngine[Any]) -> bool:
    return isinstance(column_type, JSONB)


def _is_searchable_type(column_type: TypeEngine[Any]) -> bool:
    return isinstance(column_type, (String, Text))


def _is_filterable_type(column_type: TypeEngine[Any]) -> bool:
    return not _is_geometry_type(column_type) and not _is_json_type(column_type)


def _is_sortable_type(column_type: TypeEngine[Any]) -> bool:
    return isinstance(column_type, (String, Text, Integer, Numeric, DateTime, Date, Boolean))


def _serialize_value(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_serialize_value(item) for item in value]
    return str(value)

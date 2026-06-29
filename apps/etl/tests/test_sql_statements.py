"""ETL raw SQL statement import + dialect-compile guard.

Scope (issue #348): this guard only proves the SQL constants import and compile
for the PostgreSQL dialect (``text(...)`` is opaque to SQLAlchemy — grammar,
tables, columns, ``FILTER`` and casts are NOT validated here). The load-bearing
check that the statements run with correct count logic against the real
Alembic-migrated ``app`` schema lives in
``apps/api/tests/integration/test_etl_sql_smoke.py``.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from pinvi.etl.sql.outbox import (
    EMAIL_OUTBOX_SUMMARY_SQL,
    EMAIL_OUTBOX_TEMPLATE_SQL,
    TELEGRAM_OUTBOX_CATEGORY_SQL,
    TELEGRAM_OUTBOX_SUMMARY_SQL,
)
from pinvi.etl.sql.retention import (
    LOCATION_LOG_ARCHIVE_PURPOSE_SQL,
    LOCATION_LOG_ARCHIVE_SUMMARY_SQL,
    PII_RETENTION_SUMMARY_SQL,
)


def test_etl_raw_sql_statements_import_and_compile_for_postgresql() -> None:
    """All statements import and compile for the PostgreSQL dialect (import guard)."""
    dialect = postgresql.dialect()
    statements = [
        EMAIL_OUTBOX_SUMMARY_SQL,
        EMAIL_OUTBOX_TEMPLATE_SQL,
        TELEGRAM_OUTBOX_SUMMARY_SQL,
        TELEGRAM_OUTBOX_CATEGORY_SQL,
        PII_RETENTION_SUMMARY_SQL,
        LOCATION_LOG_ARCHIVE_SUMMARY_SQL,
        LOCATION_LOG_ARCHIVE_PURPOSE_SQL,
    ]

    compiled = [str(statement.compile(dialect=dialect)) for statement in statements]

    assert all("app." in sql for sql in compiled)
    assert any("app.users" in sql for sql in compiled)
    assert any("app.location_access_log" in sql for sql in compiled)


def test_email_template_sql_is_converged_with_api_copy() -> None:
    """ETL email-template SQL must select the same Resend status columns as the API copy.

    Locks the convergence done in issue #349: the extracted
    ``EMAIL_OUTBOX_TEMPLATE_SQL`` keeps the ``delivery_delayed`` / ``suppressed``
    columns present in ``admin_etl._EMAIL_OUTBOX_TEMPLATE_SQL``.
    """
    sql = str(EMAIL_OUTBOX_TEMPLATE_SQL.compile(dialect=postgresql.dialect()))
    for column in (
        "pending",
        "sent",
        "delivered",
        "delivery_delayed",
        "failed",
        "bounced",
        "complained",
        "suppressed",
    ):
        assert f"AS {column}" in sql


def test_pii_retention_sql_matches_pending_delete_and_deleted() -> None:
    """deleted_users filter stays widened to both lifecycle statuses (issue #349)."""
    sql = str(PII_RETENTION_SUMMARY_SQL.compile(dialect=postgresql.dialect()))
    assert "status IN ('pending_delete', 'deleted')" in sql

"""ETL raw SQL statement smoke tests."""

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


def test_etl_raw_sql_statements_compile_for_postgresql() -> None:
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

from pathlib import Path


def test_initial_migration_keeps_session_tokens_hashed() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "session_token_hash" in migration
    assert "session_token\"" not in migration


def test_initial_migration_creates_postgis_extension() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration


def test_juso_migration_creates_raw_and_code_tables() -> None:
    migration = Path("alembic/versions/20260424_0002_juso_legal_dong_tables.py").read_text(
        encoding="utf-8"
    )

    assert "address_raw_juso_road_address" in migration
    assert "address_code_standard" in migration

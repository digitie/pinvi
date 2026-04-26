from pathlib import Path


def test_initial_migration_keeps_session_tokens_hashed() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "session_token_hash" in migration
    assert 'session_token"' not in migration


def test_initial_migration_creates_postgis_extension() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration


def test_juso_migration_creates_raw_and_code_tables() -> None:
    migration = Path("alembic/versions/20260424_0002_juso_legal_dong_tables.py").read_text(
        encoding="utf-8"
    )

    assert "address_raw_juso_road_address" in migration
    assert "address_code_standard" in migration


def test_juso_address_serving_migration_creates_serving_and_related_jibun_tables() -> None:
    migration = Path(
        "alembic/versions/20260425_0003_juso_address_serving_and_related_jibun.py"
    ).read_text(encoding="utf-8")

    assert "address_serving_juso_road_address" in migration
    assert "address_raw_juso_related_jibun" in migration
    assert "address_serving_juso_related_jibun" in migration


def test_vworld_boundary_migration_creates_raw_and_serving_tables() -> None:
    migration = Path("alembic/versions/20260425_0004_vworld_region_boundaries.py").read_text(
        encoding="utf-8"
    )

    assert "region_boundary_import_batch" in migration
    assert "region_raw_vworld_boundary" in migration
    assert "region_serving_boundary" in migration
    assert "srid=5179" in migration
    assert "srid=4326" in migration


def test_legal_dong_code_csv_migration_preserves_fk_target_rows() -> None:
    migration = Path("alembic/versions/20260425_0005_legal_dong_code_csv_standard.py").read_text(
        encoding="utf-8"
    )

    assert "address_raw_legal_dong_code" in migration
    assert "source_provider" in migration
    assert "is_discontinued" in migration
    assert "fk_asjra_legal_code" in migration
    assert "fk_asjrj_legal_code" in migration
    assert "DELETE FROM address_code_standard" not in migration


def test_data_go_legal_dong_fields_migration_preserves_code_primary_key() -> None:
    migration = Path("alembic/versions/20260425_0006_data_go_legal_dong_fields.py").read_text(
        encoding="utf-8"
    )

    assert "source_created_date" in migration
    assert "source_deleted_date" in migration
    assert "previous_legal_dong_code" in migration
    assert "source_sort_order" in migration
    assert "DROP TABLE address_code_standard" not in migration
    assert "DELETE FROM address_code_standard" not in migration

"""0101 M05 통합 migration의 실제 PostgreSQL 계약을 검증한다."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

API_DIR = Path(__file__).resolve().parents[2]
_ROLE_PASSWORD = "m05-role-owner-test-only"


def _alembic(
    database_url: str,
    *args: str,
    check: bool = True,
    environment: Mapping[str, str | None] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PINVI_DATABASE_URL"] = database_url
    for key, value in (environment or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


async def _execute_autocommit(database_url: str, sql: str) -> None:
    engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(sql))
    finally:
        await engine.dispose()


async def _new_database(_database_url: str, prefix: str) -> tuple[str, str]:
    database_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    parsed = make_url(_database_url)
    target_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    await _execute_autocommit(maintenance_url, f'CREATE DATABASE "{database_name}"')
    return target_url, maintenance_url


async def _drop_database(maintenance_url: str, database_url: str) -> None:
    database_name = make_url(database_url).database
    assert database_name is not None
    await _execute_autocommit(
        maintenance_url,
        f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)',
    )


def _role_database_url(database_url: str, *, role: str, password: str, database: str) -> str:
    return (
        make_url(database_url)
        .set(
            username=role,
            password=password,
            database=database,
        )
        .render_as_string(hide_password=False)
    )


def _rebaseline_module():  # type: ignore[no-untyped-def]
    path = API_DIR.parents[1] / "scripts" / "alembic_rebaseline.py"
    spec = importlib.util.spec_from_file_location("pinvi_alembic_rebaseline_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rebaseline_evidence(module, preflight, tmp_path: Path):  # type: ignore[no-untyped-def]
    backup_manifest = module.BackupManifest(
        path=tmp_path / "snapshot.dump.m05-manifest",
        sha256="1" * 64,
        created_at="2026-08-24T00:00:00Z",
        dump_sha256="0" * 64,
        restore_list_sha256="2" * 64,
        source_database=preflight.database_name,
        source_database_oid=preflight.database_oid,
        source_system_identifier=preflight.system_identifier,
        source_hostaddr=preflight.server_addr,
        source_port=preflight.server_port,
    )
    artifact = module.BackupArtifact(sha256="0" * 64, manifest=backup_manifest)
    target = module.TargetManifest(
        path=tmp_path / "target.json",
        sha256="3" * 64,
        captured_at="2026-08-24T00:00:01Z",
        backup_manifest_sha256=backup_manifest.sha256,
        preflight=preflight.as_dict(),
    )
    return artifact, target


@pytest.mark.asyncio
async def test_0101_installs_m05_final_contract_with_minimal_public_surface(
    _database_url: str,
) -> None:
    """새 DB는 0100→0101만 거쳐 anchor, receipt, audit guard를 함께 얻는다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_0101")
    try:
        upgraded = _alembic(target_url, "upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0101"
                )
                boundary_definition = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(constraint_row.oid) "
                        "FROM pg_constraint constraint_row "
                        "JOIN pg_class relation ON relation.oid = constraint_row.conrelid "
                        "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                        "WHERE namespace.nspname = 'app' "
                        "AND relation.relname = 'ktm_cache_target_boundary_audits' "
                        "AND pg_get_constraintdef(constraint_row.oid) "
                        "LIKE '%pinvi-cache-target-final-boundary/v1%'"
                    )
                )
                assert "schema_revision = '20260824_0101'::text" in boundary_definition

                trigger_rows = await connection.execute(
                    text(
                        "SELECT namespace.nspname, relation.relname, trigger_row.tgname, "
                        "trigger_row.tgenabled::text "
                        "FROM pg_trigger trigger_row "
                        "JOIN pg_class relation ON relation.oid = trigger_row.tgrelid "
                        "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                        "WHERE (namespace.nspname, relation.relname) IN ("
                        "('app', 'admin_audit_log'), "
                        "('ops', 'm05_activation_database_anchor'), "
                        "('ops', 'm05_hotswap_release_receipts')) "
                        "AND trigger_row.tgname LIKE 'trg_%append_only%' "
                        "AND NOT trigger_row.tgisinternal"
                    )
                )
                assert {(row[0], row[1], row[2], row[3]) for row in trigger_rows} >= {
                    ("app", "admin_audit_log", "trg_admin_audit_log_append_only", "A"),
                    ("app", "admin_audit_log", "trg_admin_audit_log_truncate_append_only", "A"),
                    (
                        "ops",
                        "m05_activation_database_anchor",
                        "trg_m05_activation_database_anchor_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_activation_database_anchor",
                        "trg_m05_activation_database_anchor_truncate_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_hotswap_release_receipts",
                        "trg_m05_hotswap_release_receipts_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_hotswap_release_receipts",
                        "trg_m05_hotswap_release_receipts_truncate_append_only",
                        "A",
                    ),
                }

                public_anchor_read = await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_class relation "
                        "CROSS JOIN LATERAL aclexplode(COALESCE(relation.relacl, "
                        "acldefault('r', relation.relowner))) acl "
                        "WHERE relation.oid = 'ops.m05_activation_database_anchor'::regclass "
                        "AND acl.grantee = 0 AND acl.privilege_type = 'SELECT' "
                        "AND NOT acl.is_grantable)"
                    )
                )
                assert public_anchor_read is True
                public_receipt_capability = await connection.scalar(
                    text(
                        "WITH objects AS ("
                        "SELECT relation.relacl AS acl, acldefault('r', relation.relowner) "
                        "AS default_acl FROM pg_class relation "
                        "WHERE relation.oid = 'ops.m05_hotswap_release_receipts'::regclass "
                        "UNION ALL "
                        "SELECT procedure.proacl, acldefault('f', procedure.proowner) "
                        "FROM pg_proc procedure WHERE procedure.oid IN ("
                        "'ops.m05_hotswap_release_topology_sha256("
                        "name,name,name,name,name,name)'::regprocedure, "
                        "'ops.record_m05_hotswap_release_receipt("
                        "uuid,text,text,text,text,text,text,text,name,name,name,name,name,name,"
                        "oid,oid,oid,oid,jsonb,jsonb,boolean,text)'::regprocedure, "
                        "'ops.verify_m05_hotswap_release_receipt(uuid,text)'::regprocedure)"
                        ") SELECT EXISTS (SELECT 1 FROM objects "
                        "CROSS JOIN LATERAL aclexplode(COALESCE(acl, default_acl)) privilege "
                        "WHERE privilege.grantee = 0)"
                    )
                )
                assert public_receipt_capability is False

                await connection.execute(
                    text(
                        "INSERT INTO ops.m05_activation_database_anchor "
                        "(generation, receipt_sha256, record_sha256) "
                        "VALUES (1, repeat('1', 64), repeat('2', 64))"
                    )
                )
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE ops.m05_activation_database_anchor "
                            "SET generation = 2 WHERE generation = 1"
                        )
                    )
                await connection.rollback()
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_0101_absorbs_current_main_post_0061_contracts_and_backfill(
    _database_url: str,
) -> None:
    """0101은 N150 0061의 location audit·동의 데이터를 현재 main 계약으로 전진시킨다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_0101_main")
    user_id = uuid.uuid4()
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO app.users (user_id, email, nickname) "
                        "VALUES (:user_id, :email, 'rebaseline')"
                    ),
                    {"user_id": user_id, "email": f"{user_id.hex}@pinvi.test"},
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO app.user_consents
                            (user_id, consent_type, version, agreed_at, withdrawn_at)
                        VALUES
                            (:user_id, 'tos', 'v1', '2026-01-01T00:00:00Z', NULL),
                            (:user_id, 'location_collection', 'v1', '2026-01-02T00:00:00Z',
                             '2026-01-03T00:00:00Z')
                        """
                    ),
                    {"user_id": user_id},
                )
        finally:
            await engine.dispose()

        activation = _alembic(target_url, "upgrade", "20260824_0101")
        assert activation.returncode == 0, activation.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                location_purpose_check = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(constraint_row.oid) "
                        "FROM pg_constraint constraint_row "
                        "JOIN pg_class relation ON relation.oid = constraint_row.conrelid "
                        "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                        "WHERE namespace.nspname = 'app' "
                        "AND relation.relname = 'location_access_log' "
                        "AND constraint_row.conname = "
                        "'ck_location_access_log_ck_location_access_log_purpose'"
                    )
                )
                assert location_purpose_check is not None
                assert "third_party_place_search" in location_purpose_check

                events = (
                    await connection.execute(
                        text(
                            "SELECT consent_type, event, source "
                            "FROM app.user_consent_events "
                            "WHERE user_id = :user_id "
                            "ORDER BY consent_type, event"
                        ),
                        {"user_id": user_id},
                    )
                ).all()
                assert events == [
                    ("location_collection", "agreed", "backfill"),
                    ("location_collection", "withdrawn", "backfill"),
                    ("tos", "agreed", "backfill"),
                ]
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_rebaseline_0061_to_0100_then_0101_preserves_data_and_runs_backfill(
    _database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """N150과 같은 0061 catalog는 version row만 전환한 뒤 current-main/M05 0101을 적용한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_rebaseline")
    user_id = uuid.uuid4()
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO app.users (user_id, email, nickname) "
                        "VALUES (:user_id, :email, 'rebaseline')"
                    ),
                    {"user_id": user_id, "email": f"{user_id.hex}@pinvi.test"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO app.user_consents "
                        "(user_id, consent_type, version, agreed_at, withdrawn_at) "
                        "VALUES (:user_id, 'privacy', 'v1', '2026-02-01T00:00:00Z', NULL)"
                    ),
                    {"user_id": user_id},
                )
                await connection.execute(
                    text("UPDATE app.alembic_version SET version_num = '20260821_0061'")
                )
        finally:
            await engine.dispose()

        module = _rebaseline_module()
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                rebaseline_preflight = await module._preflight(connection, lock_version=False)
        finally:
            await engine.dispose()
        artifact, target_manifest = _rebaseline_evidence(module, rebaseline_preflight, tmp_path)
        receipt_payloads: list[dict[str, object]] = []
        monkeypatch.setattr(
            module,
            "_prepare_receipt",
            lambda _path, payload: receipt_payloads.append(payload),
        )
        monkeypatch.setattr(
            module,
            "_finalize_receipt",
            lambda _path, payload: receipt_payloads.append(payload),
        )
        preflight, state = await module._apply(
            target_url, artifact, target_manifest, tmp_path / "receipt.json"
        )
        assert preflight.version_rows == ("20260821_0061",)
        assert state == "applied"
        assert [payload["state"] for payload in receipt_payloads] == ["prepared", "applied"]

        activation = _alembic(target_url, "upgrade", "20260824_0101")
        assert activation.returncode == 0, activation.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0101"
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM app.user_consent_events "
                            "WHERE user_id = :user_id AND source = 'backfill'"
                        ),
                        {"user_id": user_id},
                    )
                    == 1
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_rebaseline_preflight_rejects_same_shape_constraint_drift(
    _database_url: str,
) -> None:
    """제약 이름·열이 같아도 정의가 달라지면 0061 fingerprint는 fail-close한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_drift")
    user_id = uuid.uuid4()
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        module = _rebaseline_module()
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO app.users (user_id, email, nickname) "
                        "VALUES (:user_id, :email, 'drift')"
                    ),
                    {"user_id": user_id, "email": f"{user_id.hex}@pinvi.test"},
                )
                await connection.execute(
                    text("UPDATE app.alembic_version SET version_num = '20260821_0061'")
                )
                await connection.execute(
                    text(
                        "ALTER TABLE app.user_consents "
                        "DROP CONSTRAINT ck_user_consents_ck_user_consents_consent_type"
                    )
                )
                await connection.execute(
                    text(
                        "ALTER TABLE app.user_consents "
                        "ADD CONSTRAINT ck_user_consents_ck_user_consents_consent_type "
                        "CHECK (consent_type IN ('tos'))"
                    )
                )
            async with engine.connect() as connection:
                with pytest.raises(module.RebaselineError, match="catalog fingerprint"):
                    await module._preflight(connection, lock_version=False)
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_rebaseline_preflight_rejects_data_less_0061_target(
    _database_url: str,
) -> None:
    """alembic row만 있는 empty clone은 production rebaseline 대상이 아니다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_empty")
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE app.alembic_version SET version_num = '20260821_0061'")
                )
            module = _rebaseline_module()
            async with engine.connect() as connection:
                with pytest.raises(module.RebaselineError, match="must contain app data rows"):
                    await module._preflight(connection, lock_version=False)
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_rebaseline_target_manifest_rejects_changed_data_fingerprint(
    _database_url: str,
    tmp_path: Path,
) -> None:
    """target manifest는 database OID·role뿐 아니라 app data content drift도 봉인한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_target")
    first_user_id = uuid.uuid4()
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO app.users (user_id, email, nickname) "
                        "VALUES (:user_id, :email, 'target')"
                    ),
                    {
                        "user_id": first_user_id,
                        "email": f"{first_user_id.hex}@pinvi.test",
                    },
                )
                await connection.execute(
                    text("UPDATE app.alembic_version SET version_num = '20260821_0061'")
                )
            module = _rebaseline_module()
            async with engine.begin() as connection:
                preflight = await module._preflight(connection, lock_version=False)
                artifact, target = _rebaseline_evidence(module, preflight, tmp_path)
                await connection.execute(
                    text("UPDATE app.users SET nickname = 'changed' WHERE user_id = :user_id"),
                    {"user_id": first_user_id},
                )
            async with engine.connect() as connection:
                changed = await module._preflight(connection, lock_version=False)
            with pytest.raises(
                module.RebaselineError, match="identity or data fingerprint changed"
            ):
                module._assert_target_manifest(
                    target,
                    changed,
                    artifact.manifest.sha256,
                    artifact.manifest.created_at,
                    allow_baseline_revision=False,
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_rebaseline_recovers_prepared_receipt_after_version_commit(
    _database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """commit 뒤 receipt write가 끊겨도 같은 intent로 재실행하면 finalize한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_receipt")
    user_id = uuid.uuid4()
    receipt = tmp_path / "receipt.json"
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO app.users (user_id, email, nickname) "
                        "VALUES (:user_id, :email, 'receipt')"
                    ),
                    {"user_id": user_id, "email": f"{user_id.hex}@pinvi.test"},
                )
                await connection.execute(
                    text("UPDATE app.alembic_version SET version_num = '20260821_0061'")
                )
            module = _rebaseline_module()
            async with engine.connect() as connection:
                preflight = await module._preflight(connection, lock_version=False)
            artifact, target = _rebaseline_evidence(module, preflight, tmp_path)
            stored: dict[str, dict[str, object]] = {}
            finalize_attempts = 0

            def prepare(_path: Path, payload: dict[str, object]) -> None:
                receipt.write_text("prepared\n", encoding="utf-8")
                stored["receipt"] = payload

            def read(_path: Path) -> dict[str, object]:
                return stored["receipt"]

            def finalize(_path: Path, payload: dict[str, object]) -> None:
                nonlocal finalize_attempts
                finalize_attempts += 1
                if finalize_attempts == 1:
                    raise OSError("simulated crash after commit")
                stored["receipt"] = payload

            monkeypatch.setattr(module, "_prepare_receipt", prepare)
            monkeypatch.setattr(module, "_read_receipt", read)
            monkeypatch.setattr(module, "_finalize_receipt", finalize)
            with pytest.raises(module.RebaselineError, match="rerun apply"):
                await module._apply(target_url, artifact, target, receipt)
            assert stored["receipt"]["state"] == "prepared"
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0100"
                )
            recovered, state = await module._apply(target_url, artifact, target, receipt)
            assert recovered.version_rows == ("20260824_0100",)
            assert state == "recovered"
            assert stored["receipt"]["state"] == "applied"
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


def test_rebaseline_backup_manifest_binds_archive_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """checksum sidecar만이 아니라 root producer manifest와 pg_restore inventory를 요구한다."""

    module = _rebaseline_module()
    backup = tmp_path / "snapshot.dump"
    backup.write_bytes(b"custom-archive-fixture")
    backup_sha256 = hashlib.sha256(backup.read_bytes()).hexdigest()
    checksum = tmp_path / "snapshot.dump.sha256"
    checksum.write_text(f"{backup_sha256}  {backup.name}\n", encoding="utf-8")
    manifest = tmp_path / "snapshot.dump.m05-manifest"
    manifest.write_text(
        "\n".join(
            (
                "version=1",
                f"dump_filename={backup.name}",
                "schema=app",
                f"dump_sha256={backup_sha256}",
                f"pg_restore_list_sha256={'2' * 64}",
                "source_database=pinvi",
                "source_database_oid=100",
                "source_system_identifier=200",
                "source_hostaddr=127.0.0.1",
                "source_port=5432",
                "created_at=2026-08-24T00:00:00Z",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_validate_private_root_file", lambda path, **_kwargs: path)
    monkeypatch.setattr(module, "_restore_list_sha256", lambda _path: "2" * 64)

    artifact = module._validate_backup(backup, checksum, manifest)

    assert artifact.sha256 == backup_sha256
    assert artifact.manifest.restore_list_sha256 == "2" * 64


def test_rebaseline_target_manifest_requires_exact_legacy_preflight_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """root-created target manifest도 partial/forged preflight를 fail-close한다."""

    module = _rebaseline_module()
    preflight = module.CatalogPreflight(
        database_name="pinvi",
        database_oid=100,
        system_identifier="200",
        server_addr="127.0.0.1",
        server_port=5432,
        session_user="pinvi_migrator",
        current_user="pinvi_migrator",
        server_version_num=160000,
        version_rows=(module.LEGACY_REVISION,),
        catalog_lines=module._EXPECTED_CATALOG_LINES,
        catalog_sha256=module._EXPECTED_CATALOG_SHA256,
        app_data_rows=1,
        app_data_table_lines=1,
        app_data_content_sha256="4" * 64,
    )
    target_path = tmp_path / "target.json"
    payload = module._target_manifest_payload(preflight, "3" * 64)
    del payload["preflight"]["app_data_content_sha256"]
    target_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "_validate_private_root_file", lambda path, **_kwargs: path)

    with pytest.raises(module.RebaselineError, match="preflight fields"):
        module._read_target_manifest(target_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_sql", "expected_message"),
    (
        (
            "CREATE SCHEMA ops; "
            "ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT EXECUTE ON FUNCTIONS TO PUBLIC",
            "rejects migration-owner default privileges",
        ),
        (
            "CREATE SCHEMA ops; "
            "CREATE TABLE ops.m05_activation_database_anchor (generation bigint)",
            "refuses to replace pre-existing M05 objects",
        ),
    ),
)
async def test_0101_rejects_unsafe_existing_ops_state(
    _database_url: str,
    setup_sql: str,
    expected_message: str,
) -> None:
    """0101은 default ACL·부분 M05 object를 덮어쓰지 않고 0100에 남긴다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_0101_reject")
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                for statement in setup_sql.split("; "):
                    await connection.execute(text(statement))
        finally:
            await engine.dispose()

        failed = _alembic(target_url, "upgrade", "20260824_0101", check=False)
        assert failed.returncode != 0
        assert expected_message in (failed.stdout + failed.stderr)

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0100"
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_0101_can_use_a_separate_nonruntime_migration_owner(
    _database_url: str,
) -> None:
    """Fresh topology는 non-login owner와 one-shot SET ROLE만으로 0101을 실행한다."""

    suffix = uuid.uuid4().hex[:12]
    database_name = f"pinvi_m05_owner_{suffix}"
    app_owner = f"m05_app_owner_{suffix}"
    fence_role = f"m05_fence_{suffix}"
    migration_owner = f"m05_migration_{suffix}"
    migrator_login = f"m05_migrator_{suffix}"
    runtime_role = f"m05_runtime_{suffix}"
    stale_role = f"m05_stale_{suffix}"
    parsed = make_url(_database_url)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    migrator_url = _role_database_url(
        _database_url,
        role=migrator_login,
        password=_ROLE_PASSWORD,
        database=database_name,
    )
    target_url = parsed.set(database=database_name).render_as_string(hide_password=False)

    try:
        for statement in (
            f"CREATE ROLE \"{fence_role}\" LOGIN NOINHERIT PASSWORD '{_ROLE_PASSWORD}';",
            f'CREATE ROLE "{app_owner}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
            "NOREPLICATION NOBYPASSRLS NOINHERIT;",
            f'CREATE ROLE "{migration_owner}" NOLOGIN NOSUPERUSER NOCREATEDB '
            "NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;",
            f'CREATE ROLE "{migrator_login}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
            f"NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{_ROLE_PASSWORD}';",
            f'CREATE ROLE "{runtime_role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
            f"NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{_ROLE_PASSWORD}';",
        ):
            await _execute_autocommit(maintenance_url, statement)
        await _execute_autocommit(
            maintenance_url,
            f'CREATE DATABASE "{database_name}" OWNER "{fence_role}";',
        )
        for statement in (
            f'GRANT "{app_owner}" TO "{migration_owner}" WITH INHERIT FALSE, SET TRUE;',
            f'GRANT "{app_owner}" TO "{migrator_login}" WITH INHERIT FALSE, SET TRUE;',
            f'GRANT "{migration_owner}" TO "{migrator_login}" WITH INHERIT FALSE, SET TRUE;',
            f'ALTER ROLE "{migrator_login}" IN DATABASE "{database_name}" '
            f'SET ROLE TO "{app_owner}";',
            f'REVOKE CONNECT ON DATABASE "{database_name}" FROM PUBLIC;',
            f'GRANT CONNECT ON DATABASE "{database_name}" TO "{runtime_role}", "{migrator_login}";',
            f'GRANT CREATE ON DATABASE "{database_name}" TO "{app_owner}", "{migration_owner}";',
            f'CREATE SCHEMA app AUTHORIZATION "{app_owner}";',
            "CREATE SCHEMA x_extension;",
            "CREATE EXTENSION pgcrypto SCHEMA x_extension;",
            "CREATE EXTENSION pg_trgm SCHEMA x_extension;",
            "CREATE EXTENSION citext SCHEMA x_extension;",
            "REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;",
            "REVOKE ALL ON FUNCTION x_extension.digest(bytea, text) FROM PUBLIC;",
            f'GRANT USAGE ON SCHEMA x_extension TO "{app_owner}", '
            f'"{migration_owner}", "{runtime_role}";',
            f'GRANT EXECUTE ON FUNCTION x_extension.digest(bytea, text) TO "{app_owner}", '
            f'"{migration_owner}", "{runtime_role}";',
        ):
            await _execute_autocommit(target_url, statement)

        role_environment = {
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_MIGRATION_OWNER": migration_owner,
            "PINVI_MIGRATOR_DB_USER": migrator_login,
        }
        baseline = _alembic(
            migrator_url,
            "upgrade",
            "20260824_0100",
            environment=role_environment,
        )
        assert baseline.returncode == 0, baseline.stderr
        await _execute_autocommit(
            maintenance_url,
            f"CREATE ROLE \"{stale_role}\" LOGIN NOINHERIT PASSWORD '{_ROLE_PASSWORD}';",
        )
        await _execute_autocommit(
            target_url,
            f'GRANT "{app_owner}" TO "{stale_role}" WITH INHERIT FALSE, SET TRUE;',
        )
        stale_membership = _alembic(
            migrator_url,
            "upgrade",
            "20260824_0101",
            check=False,
            environment=role_environment,
        )
        assert stale_membership.returncode != 0
        assert "0101 migration owner role contract is not satisfied" in (
            stale_membership.stdout + stale_membership.stderr
        )
        await _execute_autocommit(target_url, f'REVOKE "{app_owner}" FROM "{stale_role}";')
        await _execute_autocommit(maintenance_url, f'DROP ROLE "{stale_role}";')
        activation = _alembic(
            migrator_url,
            "upgrade",
            "20260824_0101",
            check=False,
            environment=role_environment,
        )
        assert activation.returncode == 0, activation.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                membership_contract = await connection.scalar(
                    text(
                        """
                        WITH schema_owner AS (
                            SELECT oid FROM pg_roles WHERE rolname = :app_owner
                        ),
                        migration_owner AS (
                            SELECT oid, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb,
                                   rolreplication, rolbypassrls, rolinherit
                            FROM pg_roles WHERE rolname = :migration_owner
                        ),
                        migrator AS (
                            SELECT oid, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb,
                                   rolreplication, rolbypassrls, rolinherit
                            FROM pg_roles WHERE rolname = :migrator_login
                        )
                        SELECT
                            (SELECT count(*) FROM migration_owner) = 1
                            AND (SELECT count(*) FROM migrator) = 1
                            AND EXISTS (
                                SELECT 1 FROM migration_owner role_row
                                WHERE NOT role_row.rolcanlogin
                                  AND NOT role_row.rolsuper
                                  AND NOT role_row.rolcreaterole
                                  AND NOT role_row.rolcreatedb
                                  AND NOT role_row.rolreplication
                                  AND NOT role_row.rolbypassrls
                                  AND NOT role_row.rolinherit
                                  AND NOT has_database_privilege(
                                      role_row.oid, current_database(), 'CONNECT'
                                  )
                                  AND has_schema_privilege(
                                      role_row.oid, 'x_extension', 'USAGE'
                                  )
                                  AND NOT has_schema_privilege(
                                      role_row.oid, 'x_extension', 'CREATE'
                                  )
                                  AND has_function_privilege(
                                      role_row.oid,
                                      'x_extension.digest(bytea,text)'::regprocedure,
                                      'EXECUTE'
                                  )
                            )
                            AND EXISTS (
                                SELECT 1 FROM migrator role_row
                                WHERE role_row.rolcanlogin
                                  AND NOT role_row.rolsuper
                                  AND NOT role_row.rolcreaterole
                                  AND NOT role_row.rolcreatedb
                                  AND NOT role_row.rolreplication
                                  AND NOT role_row.rolbypassrls
                                  AND NOT role_row.rolinherit
                                  AND (
                                      SELECT count(*) FROM pg_auth_members membership
                                      WHERE membership.member = role_row.oid
                                        AND membership.roleid IN (
                                            (SELECT oid FROM schema_owner),
                                            (SELECT oid FROM migration_owner)
                                        )
                                        AND NOT membership.admin_option
                                        AND NOT membership.inherit_option
                                        AND membership.set_option
                                  ) = 2
                                  AND NOT EXISTS (
                                      SELECT 1 FROM pg_auth_members membership
                                      WHERE membership.member = role_row.oid
                                        AND membership.roleid NOT IN (
                                            (SELECT oid FROM schema_owner),
                                            (SELECT oid FROM migration_owner)
                                        )
                                  )
                                  AND NOT EXISTS (
                                      SELECT 1 FROM pg_auth_members membership
                                      WHERE membership.roleid = role_row.oid
                                  )
                            )
                            AND EXISTS (
                                SELECT 1 FROM pg_auth_members membership
                                WHERE membership.member = (SELECT oid FROM migration_owner)
                                  AND membership.roleid = (SELECT oid FROM schema_owner)
                                  AND NOT membership.admin_option
                                  AND NOT membership.inherit_option
                                  AND membership.set_option
                            )
                            AND EXISTS (
                                SELECT 1 FROM pg_db_role_setting setting_row
                                WHERE setting_row.setrole = (SELECT oid FROM migrator)
                                  AND setting_row.setdatabase = (
                                      SELECT oid FROM pg_database
                                      WHERE datname = current_database()
                                  )
                                  AND ('role=' || :app_owner) = ANY(setting_row.setconfig)
                            )
                        """
                    ),
                    {
                        "app_owner": app_owner,
                        "migration_owner": migration_owner,
                        "migrator_login": migrator_login,
                    },
                )
                assert membership_contract is True
                owners = await connection.execute(
                    text(
                        "SELECT namespace.nspowner::regrole::text, "
                        "relation.relowner::regrole::text "
                        "FROM pg_namespace namespace "
                        "JOIN pg_class relation ON relation.relnamespace = namespace.oid "
                        "WHERE namespace.nspname = 'ops' "
                        "AND relation.relname = 'm05_hotswap_release_receipts'"
                    )
                )
                assert owners.one() == (migration_owner, migration_owner)
                assert (
                    await connection.scalar(
                        text(
                            "SELECT relation.relowner::regrole::text "
                            "FROM pg_class relation "
                            "WHERE relation.oid = 'app.user_consent_events'::regclass"
                        )
                    )
                    == app_owner
                )
                extension_access = await connection.scalar(
                    text(
                        "SELECT has_schema_privilege(:migration_owner, 'x_extension', 'USAGE') "
                        "AND NOT has_schema_privilege(:fence_role, 'x_extension', 'USAGE')"
                    ),
                    {"migration_owner": migration_owner, "fence_role": fence_role},
                )
                assert extension_access is True
        finally:
            await engine.dispose()

        migrator_engine = create_async_engine(migrator_url, poolclass=NullPool)
        try:
            async with migrator_engine.connect() as connection:
                session_roles = await connection.execute(text("SELECT session_user, current_user"))
                assert session_roles.one() == (migrator_login, app_owner)
                await connection.execute(text(f'SET ROLE "{migration_owner}"'))
                assert await connection.scalar(text("SELECT current_user")) == migration_owner
        finally:
            await migrator_engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)
        await _execute_autocommit(
            maintenance_url,
            f'DROP ROLE IF EXISTS "{stale_role}", "{runtime_role}", "{migrator_login}", '
            f'"{migration_owner}", "{app_owner}", "{fence_role}";',
        )


@pytest.mark.asyncio
async def test_0101_requires_owner_roles_in_managed_environment(
    _database_url: str,
) -> None:
    """staging/production은 M05 owner role 입력 누락을 transaction 전체에서 거부한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_owner_required")
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr

        failed = _alembic(
            target_url,
            "upgrade",
            "20260824_0101",
            check=False,
            environment={
                "PINVI_ENVIRONMENT": "staging",
                "PINVI_M05_LEGACY_REBASELINE": "0",
                "PINVI_MIGRATION_OWNER": None,
                "PINVI_MIGRATOR_DB_USER": None,
            },
        )
        assert failed.returncode != 0
        assert "0101 managed migration requires migration and migrator roles" in (
            failed.stdout + failed.stderr
        )

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0100"
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_0101_legacy_rebaseline_profile_requires_root_owned_handoff(
    _database_url: str,
) -> None:
    """legacy profile은 root-owned 0061→0100 인수증 없이는 DDL 전에 거부한다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_legacy_owner")
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        failed = _alembic(
            target_url,
            "upgrade",
            "20260824_0101",
            check=False,
            environment={
                "PINVI_ENVIRONMENT": "staging",
                "PINVI_M05_LEGACY_REBASELINE": "1",
                "PINVI_MIGRATION_OWNER": "pinvi_migration_owner",
                "PINVI_MIGRATOR_DB_USER": "pinvi_migrator",
                "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH": None,
            },
        )
        assert failed.returncode != 0
        assert "0101 legacy rebaseline requires an applied root-owned receipt" in (
            failed.stdout + failed.stderr
        )

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0100"
                )
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass('ops.m05_hotswap_release_receipts')")
                    )
                    is None
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)

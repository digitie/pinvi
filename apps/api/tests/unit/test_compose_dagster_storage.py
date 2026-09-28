"""PinVi 자신의 compose에서도 Dagster instance storage가 실제로 배송되는지 고정한다.

#558(2026-09-19)이 `apps/etl/dagster.yaml`을 이미지에 구워 instance storage를
`PINVI_DAGSTER_PG_URL`의 PostgreSQL로 옮겼다. 운영(Manager compose)은 그 env를 주지만
PinVi의 app compose(`app-dagster`, profile etl)는 주지 않았다 — instance가 뜨지 못해
이미지 HEALTHCHECK(`repositoriesOrError`)가 끝내 unhealthy를 보고했고, Manager M05 격리
실행이 `--profile etl up --wait app-dagster`에서 매번 멈췄다(2026-09-27 p3·p4·p8).

이 파일은 이름이 아니라 **효과**를 본다. compose를 Compose처럼 보간해, app-dagster가 받는
DSN과 storage one-shot이 만드는 role·database·password가 같은 값으로 풀리는지, 그리고 그
env 이름이 이미지에 구운 dagster.yaml이 실제로 읽는 이름인지 확인한다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
APP_COMPOSE = ROOT / "infra/docker-compose.app.yml"
DEV_COMPOSE = ROOT / "infra/docker-compose.yml"
DAGSTER_YAML = ROOT / "apps/etl/dagster.yaml"
ETL_DOCKERFILE = ROOT / "apps/etl/Dockerfile"
STORAGE_BOOTSTRAP = ROOT / "infra/postgres/bootstrap-pinvi-dagster-db.sh"


def _interpolate(value: object, environment: dict[str, str]) -> object:
    """Compose처럼 문자열만 치환한다: `$$`는 문자 그대로, `${A:-${B:-x}}`는 안쪽부터."""

    if isinstance(value, dict):
        return {key: _interpolate(item, environment) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, environment) for item in value]
    if not isinstance(value, str):
        return value

    def substitute(match: re.Match[str]) -> str:
        name, operator, default = match.group(1), match.group(2), match.group(3) or ""
        current = environment.get(name)
        if operator == ":-":
            return current or default
        if operator == "-":
            return default if current is None else current
        return current or ""

    text = value.replace("$$", "\0")
    pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?-)([^${}]*))?\}"
    while (replaced := re.sub(pattern, substitute, text)) != text:
        text = replaced
    return text.replace("\0", "$")


def _services(path: Path) -> dict[str, dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]


def _storage_env_name() -> str:
    """이미지에 구운 instance 설정이 storage DSN을 읽는 env 이름."""

    config = yaml.safe_load(DAGSTER_YAML.read_text(encoding="utf-8"))
    name = config["storage"]["postgres"]["postgres_url"]["env"]
    assert isinstance(name, str) and name
    return name


def _baked_dagster_home() -> str:
    match = re.search(r"DAGSTER_HOME=(\S+)", ETL_DOCKERFILE.read_text(encoding="utf-8"))
    assert match is not None, "apps/etl/Dockerfile의 DAGSTER_HOME을 찾지 못했다"
    return match.group(1)


def _database(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


@pytest.mark.parametrize(
    ("environment", "expected_password"),
    [
        # smoke: 다른 비밀번호와 같은 기본값.
        ({}, "pinvi_app_smoke"),
        # Manager M05 격리 실행: app/owner/migrator만 무작위로 준다 — Dagster 전용 입력 없이도
        # 무작위 비밀번호가 된다.
        (
            {
                "PINVI_POSTGRES_PASSWORD": "owner-random",
                "PINVI_APP_DB_PASSWORD": "app-random",
                "PINVI_MIGRATOR_DB_PASSWORD": "migrator-random",
            },
            "app-random",
        ),
        # 전용 값을 주는 환경.
        (
            {"PINVI_APP_DB_PASSWORD": "app-random", "PINVI_DAGSTER_DB_PASSWORD": "dagster-own"},
            "dagster-own",
        ),
    ],
)
def test_app_dagster_storage_url_resolves_to_what_the_one_shot_creates(
    environment: dict[str, str], expected_password: str
) -> None:
    services = _services(APP_COMPOSE)
    env_name = _storage_env_name()
    dagster_env = _interpolate(services["app-dagster"]["environment"], environment)
    init_env = _interpolate(services["app-dagster-db-init"]["environment"], environment)
    assert isinstance(dagster_env, dict) and isinstance(init_env, dict)

    assert env_name in dagster_env, (
        f"app-dagster가 {env_name}을 받지 않는다 — 이미지에 구운 dagster.yaml이 storage DSN을 "
        "그 env에서 읽으므로 instance가 뜨지 못하고 컨테이너는 끝내 unhealthy가 된다."
    )
    storage = urlsplit(dagster_env[env_name])
    app = urlsplit(dagster_env["PINVI_DATABASE_URL"])

    assert storage.scheme == "postgresql"
    assert (storage.hostname, storage.port) == ("app-postgres", 5432)
    # one-shot이 만드는 바로 그 login·password·database다.
    assert storage.username == init_env["PINVI_DAGSTER_DB_USER"]
    assert unquote(storage.password or "") == init_env["PINVI_DAGSTER_DB_PASSWORD"]
    assert storage.password == expected_password
    assert _database(dagster_env[env_name]) == init_env["PINVI_DAGSTER_DB"]
    # 앱 DB와 다른 database — Dagster가 첫 기동에 만드는 테이블을 M05 runtime login은 `pinvi`에
    # 만들 수 없고, 그 테이블을 M05 소유·백업·복원·hotswap 범위 밖에 둔다(운영도 `pinvi_dagster`).
    assert _database(dagster_env[env_name]) != _database(dagster_env["PINVI_DATABASE_URL"])
    assert init_env["PINVI_DAGSTER_DB"] != init_env["POSTGRES_DB"]
    # 앱 runtime login이 아니다 — 그 role은 새 database를 소유하지 않는다.
    assert storage.username != app.username


def test_app_dagster_waits_for_the_storage_one_shot_after_the_role_bootstrap() -> None:
    services = _services(APP_COMPOSE)
    dagster = services["app-dagster"]
    init = services["app-dagster-db-init"]
    role_bootstrap = services["app-db-runtime-role"]

    assert dagster["depends_on"]["app-dagster-db-init"] == {
        "condition": "service_completed_successfully"
    }
    # 같은 profile이어야 `--profile etl up app-dagster`가 one-shot을 함께 띄운다.
    assert init["profiles"] == dagster["profiles"] == ["etl"]
    assert init["depends_on"]["app-postgres"] == {"condition": "service_healthy"}
    # 앱 DB의 PUBLIC CONNECT를 걷는 쪽이 먼저 끝나야 "앱 DB에 닿지 못한다" 검증이 선다.
    assert init["depends_on"]["app-db-runtime-role"] == {
        "condition": "service_completed_successfully"
    }
    assert init["restart"] == "no"
    assert init["image"] == services["app-postgres"]["image"]
    assert "ports" not in init

    mount = "./postgres/bootstrap-pinvi-dagster-db.sh:/bootstrap/bootstrap-pinvi-dagster-db.sh:ro"
    assert init["volumes"] == [mount]
    assert init["entrypoint"] == ["/bin/sh", "/bootstrap/bootstrap-pinvi-dagster-db.sh"]
    assert STORAGE_BOOTSTRAP.is_file()

    # root bootstrap 입력과 M05 role 이름은 role bootstrap과 **같은 식**이어야 한다 —
    # one-shot의 "Dagster login은 M05 role과 달라야 한다" 검사가 실제로 만들어진 role을 본다.
    for name in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "PINVI_APP_DB_USER",
        "PINVI_APP_SCHEMA_OWNER",
        "PINVI_MIGRATION_OWNER",
        "PINVI_MIGRATOR_DB_USER",
    ):
        assert init["environment"][name] == role_bootstrap["environment"][name], name
    # one-shot은 app/migrator 비밀번호를 받지 않는다 — 그 role의 비밀번호를 바꾸지 않는다.
    assert "PINVI_APP_DB_PASSWORD" not in init["environment"]
    assert "PINVI_MIGRATOR_DB_PASSWORD" not in init["environment"]


def test_owner_and_migrator_secrets_do_not_reach_the_dagster_runtime() -> None:
    """새 DSN이 root owner·migrator 비밀을 runtime에 실어 나르지 않는다(M05 role 분리)."""

    services = _services(APP_COMPOSE)
    secrets = {
        "PINVI_POSTGRES_PASSWORD": "owner-secret-7f3a",
        "PINVI_MIGRATOR_DB_PASSWORD": "migrator-secret-2c9e",
        "PINVI_APP_DB_PASSWORD": "app-secret-5b1d",
    }
    for service, forbidden in (
        ("app-dagster", ("owner-secret-7f3a", "migrator-secret-2c9e")),
        # root one-shot은 owner로 붙지만 migrator login은 모른다.
        ("app-dagster-db-init", ("migrator-secret-2c9e",)),
    ):
        rendered = _interpolate(services[service]["environment"], secrets)
        assert isinstance(rendered, dict)
        blob = "\n".join(f"{key}={value}" for key, value in rendered.items())
        for value in forbidden:
            assert value not in blob, f"{service}에 {value}가 풀린다"


@pytest.mark.parametrize(
    ("compose", "service"), [(APP_COMPOSE, "app-dagster"), (DEV_COMPOSE, "dagster")]
)
def test_no_volume_shadows_the_baked_instance_config(compose: Path, service: str) -> None:
    """DAGSTER_HOME에 볼륨을 붙이면 이미지에 구운 dagster.yaml을 볼륨 사본이 가린다.

    named volume은 처음 만들어질 때만 이미지 내용을 복사한다. 그 뒤 이미지의 dagster.yaml이
    바뀌어도 반영되지 않고, dagster.yaml이 생기기 전에 만든 볼륨에서는 instance가 SQLite로 뜬다.
    """

    definition = _services(compose)[service]
    home = definition["environment"]["DAGSTER_HOME"]
    assert home == _baked_dagster_home(), (
        f"{compose.name}의 {service}가 이미지에 구운 DAGSTER_HOME이 아닌 곳을 쓴다 — 그 자리에는 "
        "dagster.yaml이 없어 instance가 PINVI_DAGSTER_PG_URL 없이 SQLite로 뜬다."
    )
    baked_config = f"{home}/dagster.yaml"
    for volume in definition.get("volumes", []):
        target = volume.split(":")[1] if isinstance(volume, str) else volume["target"]
        target = target.rstrip("/")
        assert not (baked_config == target or baked_config.startswith(f"{target}/")), (
            f"{compose.name}의 {service} 볼륨 {target}이 구운 {baked_config}을 가린다"
        )


def test_dev_compose_dagster_uses_its_own_storage_database() -> None:
    services = _services(DEV_COMPOSE)
    dagster = services["dagster"]
    init = services["dagster-db-init"]
    env_name = _storage_env_name()

    assert env_name in dagster["environment"]
    storage_db = _database(dagster["environment"][env_name])
    app_db = _database(dagster["environment"]["PINVI_DATABASE_URL"])
    assert storage_db and storage_db != app_db
    assert dagster["depends_on"]["dagster-db-init"] == {
        "condition": "service_completed_successfully"
    }
    assert init["profiles"] == dagster["profiles"] == ["etl"]
    script = "\n".join(init["command"])
    assert "set -eu" in script
    assert f"createdb --template=template0 {storage_db}" in script
    assert f"datname = '{storage_db}'" in script
    assert "|| true" not in script


# ---------------------------------------------------------------------------
# bootstrap-pinvi-dagster-db.sh 동작 — fake psql로 분기를 돈다.
# ---------------------------------------------------------------------------

_BOOTSTRAP_ENV = {
    "POSTGRES_USER": "pinvi_owner",
    "POSTGRES_PASSWORD": "root-password",
    "POSTGRES_DB": "pinvi",
    "PINVI_APP_DB_USER": "pinvi_app",
    "PINVI_APP_SCHEMA_OWNER": "pinvi_app_owner",
    "PINVI_MIGRATION_OWNER": "pinvi_migration_owner",
    "PINVI_MIGRATOR_DB_USER": "pinvi_migrator",
    "PINVI_DAGSTER_DB": "pinvi_dagster",
    "PINVI_DAGSTER_DB_USER": "pinvi_dagster_app",
    "PINVI_DAGSTER_DB_PASSWORD": "dagster-password",
}

# 질의 종류는 stdin으로 가른다. 호출마다 한 줄을 로그에 남긴다.
_FAKE_PSQL = r"""#!/bin/sh
[ -z "${PGHOSTADDR:-}${PGHOST:-}${PGPORT:-}${PGDATABASE:-}" ] || exit 96
case " $* " in
  *" --host=app-postgres --port=5432 "*) ;;
  *) exit 97 ;;
esac
case " $* " in
  *" --command=SELECT 1 "*) echo ready >> "$PINVI_TEST_LOG"; exit 0 ;;
esac
input="$(cat)"
case "$input" in
  *"THEN 'absent'"*) echo owner-probe >> "$PINVI_TEST_LOG"; printf '%s\n' "$PINVI_TEST_EXISTING" ;;
  *"CREATE ROLE"*) echo mutation >> "$PINVI_TEST_LOG" ;;
  *"has_database_privilege"*) echo verify >> "$PINVI_TEST_LOG"; printf '%s\n' "$PINVI_TEST_ISOLATED" ;;
  *) exit 98 ;;
esac
exit 0
"""


def _run_bootstrap(
    tmp_path: Path, overrides: dict[str, str] | None = None, **fake: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    shell = shutil.which("sh")
    assert shell is not None
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(_FAKE_PSQL, encoding="utf-8")
    fake_psql.chmod(0o700)
    log = tmp_path / "psql.log"
    log.write_text("", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 -- fixed repository script under test
        [shell, str(STORAGE_BOOTSTRAP)],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            # caller가 고른 libpq target은 상속되지 않아야 한다(fake가 96으로 끝낸다).
            "PGHOSTADDR": "127.0.0.2",
            "PGHOST": "db.example.test",
            "PGPORT": "6543",
            "PGDATABASE": "postgres",
            # endpoint는 고정이다 — env로 바꿀 수 없다(fake가 97로 끝낸다).
            "PINVI_DB_HOST": "db.example.test",
            "PINVI_DB_PORT": "6543",
            "PINVI_TEST_LOG": str(log),
            "PINVI_TEST_EXISTING": fake.get("existing", "absent"),
            "PINVI_TEST_ISOLATED": fake.get("isolated", "true"),
            **_BOOTSTRAP_ENV,
            **(overrides or {}),
        },
    )
    return result, log.read_text(encoding="utf-8").split()


@pytest.mark.parametrize("existing", ["absent", "owned"])
def test_storage_bootstrap_creates_then_verifies(tmp_path: Path, existing: str) -> None:
    result, calls = _run_bootstrap(tmp_path, existing=existing)
    assert result.returncode == 0, result.stderr
    assert calls == ["ready", "owner-probe", "mutation", "verify"]


def test_storage_bootstrap_refuses_a_foreign_database_before_any_change(tmp_path: Path) -> None:
    result, calls = _run_bootstrap(tmp_path, existing="foreign")
    assert result.returncode == 3
    assert "belongs to another role" in result.stderr
    assert "mutation" not in calls


def test_storage_bootstrap_refuses_a_foreign_role_before_any_change(tmp_path: Path) -> None:
    """같은 이름의 기존 role이 평범한 Dagster login이 아니면 ALTER ROLE 전에 멈춘다.

    예약 이름 목록(bootstrap owner·M05 네 role)에 없는 restore·hotswap role을 Dagster login으로
    잘못 주면, 끝의 격리 검사가 실패하기 **전에** ALTER ROLE이 그 role의 비밀번호와 속성을 이미
    바꿔 놓았다(2026-09-28 리뷰).
    """

    result, calls = _run_bootstrap(
        tmp_path, {"PINVI_DAGSTER_DB_USER": "pinvi_restore_fence"}, existing="foreign-role"
    )
    assert result.returncode == 3
    assert "is not a plain Dagster login" in result.stderr
    assert calls == ["ready", "owner-probe"]


def test_storage_bootstrap_pre_mutation_probe_covers_the_role_shape() -> None:
    """변경 전 probe가 기존 role을 끝의 격리 검사와 같은 role 모양으로 묻는지 본다.

    효과(실제 PostgreSQL에서 foreign role이 거부되고 그 role의 비밀번호·속성이 그대로인 것)는
    n150 live run이 봤다 — 여기는 그 질의가 조용히 줄어드는 회귀를 막는다.
    """

    script = STORAGE_BOOTSTRAP.read_text(encoding="utf-8")
    probe = script[
        script.index('existing_database="$(') : script.index('case "${existing_database}" in')
    ]
    for clause in (
        "role_row.rolcanlogin",
        "NOT role_row.rolsuper",
        "NOT role_row.rolcreaterole",
        "NOT role_row.rolcreatedb",
        "NOT role_row.rolreplication",
        "NOT role_row.rolbypassrls",
        "NOT role_row.rolinherit",
        "existing_membership.member = (SELECT oid FROM existing_role)",
        "existing_membership.roleid = (SELECT oid FROM existing_role)",
        "owned_database.datdba = (SELECT oid FROM existing_role)",
        "owned_database.datname <> :'dagster_db'",
        "has_database_privilege((SELECT oid FROM existing_role), :'app_db', 'CONNECT')",
        "THEN 'foreign-role'",
    ):
        assert clause in probe, clause
    # probe는 읽기만 한다.
    for mutation in ("CREATE", "ALTER", "GRANT", "REVOKE", "\\gexec", "dagster_password"):
        assert mutation not in probe, mutation


def test_storage_bootstrap_fails_closed_when_the_owner_is_unknown(tmp_path: Path) -> None:
    result, calls = _run_bootstrap(tmp_path, existing="")
    assert result.returncode == 1
    assert "mutation" not in calls


def test_storage_bootstrap_fails_when_the_login_is_not_isolated(tmp_path: Path) -> None:
    result, calls = _run_bootstrap(tmp_path, isolated="false")
    assert result.returncode == 3
    assert "is not isolated" in result.stderr
    assert calls[-1] == "verify"


@pytest.mark.parametrize(
    "role",
    ["pinvi_owner", "pinvi_app", "pinvi_app_owner", "pinvi_migration_owner", "pinvi_migrator"],
)
def test_storage_bootstrap_refuses_an_existing_principal_as_the_dagster_login(
    tmp_path: Path, role: str
) -> None:
    result, calls = _run_bootstrap(tmp_path, {"PINVI_DAGSTER_DB_USER": role})
    assert result.returncode == 2
    assert "must differ from the bootstrap and M05 roles" in result.stderr
    assert calls == []


@pytest.mark.parametrize("database", ["pinvi", "postgres", "template0", "template1"])
def test_storage_bootstrap_refuses_a_shared_database(tmp_path: Path, database: str) -> None:
    result, calls = _run_bootstrap(tmp_path, {"PINVI_DAGSTER_DB": database})
    assert result.returncode == 2
    assert "must name a database of its own" in result.stderr
    assert calls == []


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"PINVI_DAGSTER_DB_USER": "Pinvi-Dagster"}, "invalid PostgreSQL identifier"),
        (
            {"PINVI_DAGSTER_DB": "pinvi_dagster; DROP DATABASE pinvi"},
            "invalid PostgreSQL identifier",
        ),
        ({"PINVI_DAGSTER_DB_PASSWORD": ""}, "PINVI_DAGSTER_DB_PASSWORD is required"),
    ],
)
def test_storage_bootstrap_rejects_invalid_input(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    result, calls = _run_bootstrap(tmp_path, override)
    # 메시지까지 본다 — `sh`는 스크립트를 열지 못해도 2로 끝나므로 종료 코드만으로는 공허하다.
    assert result.returncode == 2
    assert message in result.stderr
    assert calls == []


def test_storage_bootstrap_verification_covers_the_isolation_claims() -> None:
    """검증 질의가 주석이 약속한 격리를 실제로 묻는지 본다(효과는 n150 live run이 봤다)."""

    script = STORAGE_BOOTSTRAP.read_text(encoding="utf-8")
    verification = script[script.index('storage_isolated="$(') :]
    for clause in (
        "role_row.rolcanlogin",
        "NOT role_row.rolsuper",
        "NOT role_row.rolcreaterole",
        "NOT role_row.rolcreatedb",
        "NOT role_row.rolreplication",
        "NOT role_row.rolbypassrls",
        "NOT role_row.rolinherit",
        "membership.member = (SELECT oid FROM dagster_role)",
        "membership.roleid = (SELECT oid FROM dagster_role)",
        "(SELECT datdba FROM dagster_database) = (SELECT oid FROM dagster_role)",
        "database_row.datname <> :'dagster_db'",
        "acl.grantee <> database_row.datdba",
        "NOT has_database_privilege((SELECT oid FROM dagster_role), :'app_db', 'CONNECT')",
    ):
        assert clause in verification, clause
    mutation = script[script.index("CREATE ROLE %I") : script.index('storage_isolated="$(')]
    assert "TEMPLATE template0" in mutation
    assert "REVOKE ALL ON DATABASE %I FROM PUBLIC" in mutation
    assert "GRANT" not in mutation

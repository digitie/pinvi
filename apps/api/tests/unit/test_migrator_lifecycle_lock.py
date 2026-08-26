"""두 배포 wrapper가 공유하는 one-shot migrator lifecycle lock 회귀."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOCK_HELPER = ROOT / "scripts" / "migrator-lifecycle-lock.sh"
BASH = "/usr/bin/bash"


def _environment(lock_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PINVI_ENVIRONMENT": "smoke",
            "PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH": str(lock_path),
        }
    )
    return environment


def test_smoke_default_lock_uses_a_private_per_user_directory() -> None:
    environment = os.environ.copy()
    environment.pop("PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH", None)
    environment["PINVI_ENVIRONMENT"] = "smoke"
    result = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
        [BASH, "-c", 'source "$1"; migrator_lifecycle_lock_path', "--", str(LOCK_HELPER)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"{os.sep}tmp{os.sep}pinvi-migrator-lifecycle-{os.getuid()}{os.sep}migrator-lifecycle.lock"
    )


def test_migrator_lifecycle_lock_rejects_a_smoke_path_in_a_shared_writable_parent(
    tmp_path: Path,
) -> None:
    shared_parent = tmp_path / "shared"
    shared_parent.mkdir(mode=0o777)
    shared_parent.chmod(0o777)
    result = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
        [
            BASH,
            "-c",
            'source "$1"; acquire_migrator_lifecycle_lock',
            "--",
            str(LOCK_HELPER),
        ],
        env=_environment(shared_parent / "migrator-lifecycle.lock"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "migrator lifecycle lock parent must be owned by the current user and non-writable" in (
        result.stderr
    )


def test_migrator_lifecycle_lock_serializes_two_wrapper_processes(tmp_path: Path) -> None:
    """두 wrapper가 공유 helper의 real flock 앞에서 writer drain 전에 멈춘다."""

    lock_path = tmp_path / "migrator-lifecycle.lock"
    ready_path = tmp_path / "holder-ready"
    environment = _environment(lock_path)
    holder = subprocess.Popen(  # noqa: S603 - fixed local Bash helper invocation
        [
            BASH,
            "-c",
            'source "$1"; acquire_migrator_lifecycle_lock; : >"$2"; sleep 10',
            "--",
            str(LOCK_HELPER),
            str(ready_path),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            if ready_path.exists():
                break
            assert holder.poll() is None, holder.stderr.read()
            time.sleep(0.02)
        assert ready_path.exists()

        contender = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
            [
                BASH,
                "-c",
                'source "$1"; acquire_migrator_lifecycle_lock',
                "--",
                str(LOCK_HELPER),
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert contender.returncode == 2
        assert "another Pinvi migrator lifecycle is already running" in contender.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_both_migration_wrappers_take_the_shared_lock_before_writer_drain() -> None:
    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        lifecycle = source[
            source.index("migrate_under_lifecycle_lock() {") : source.index(
                "bootstrap_credential_file()"
            )
        ]
        wrapper = source[source.index("migrate() {") :]
        assert 'source "$ROOT_DIR/scripts/migrator-lifecycle-lock.sh"' in source
        assert wrapper.index("acquire_migrator_lifecycle_lock") < wrapper.index(
            "migrate_under_lifecycle_lock"
        )
        assert lifecycle.index("drain_runtime_writers") < lifecycle.index("prepare_migrator_login")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"{name}() {{")
    end = source.index("\n}\n", start) + 2
    return source[start:end]


def test_migration_resolves_compose_environment_before_selecting_the_lock() -> None:
    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        migrate = _function_body(source, "migrate")
        assert migrate.index("pinvi_prepare_api_image_provenance") < migrate.index(
            "acquire_migrator_lifecycle_lock"
        )


def test_writer_startup_stays_under_the_shared_lifecycle_lock_until_ready() -> None:
    docker_app = (ROOT / "scripts" / "docker-app.sh").read_text(encoding="utf-8")
    docker_up = _function_body(docker_app, "up")
    assert docker_up.index("acquire_migrator_lifecycle_lock") < docker_up.index("up_deps")
    assert docker_up.index("drain_runtime_writers") < docker_up.index("free_app_ports")
    assert docker_up.index("acquire_migrator_lifecycle_lock") < docker_up.index("free_app_ports")
    assert docker_up.index("free_app_ports") < docker_up.index("up_deps")
    assert docker_up.index("migrate_under_lifecycle_lock") < docker_up.index(
        "compose up -d app-api app-web"
    )
    assert docker_up.index("compose up -d app-api app-web") < docker_up.index(
        'wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"'
    )
    assert docker_up.index('wait_for_url "http://127.0.0.1:${WEB_PORT}/" "Web"') < docker_up.index(
        "release_migrator_lifecycle_lock"
    )

    deploy = (ROOT / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    deploy_up = _function_body(deploy, "up")
    assert deploy_up.index("acquire_migrator_lifecycle_lock") < deploy_up.index(
        "up_under_lifecycle_lock"
    )
    assert deploy_up.index("up_under_lifecycle_lock") < deploy_up.index(
        "release_migrator_lifecycle_lock"
    )
    deploy_command = _function_body(deploy, "deploy")
    assert deploy_command.index("acquire_migrator_lifecycle_lock") < deploy_command.index(
        "drain_runtime_writers"
    )
    assert deploy_command.index("drain_runtime_writers") < deploy_command.index(
        "migrate_under_lifecycle_lock"
    )
    assert deploy_command.index("migrate_under_lifecycle_lock") < deploy_command.index(
        "up_under_lifecycle_lock"
    )
    assert deploy_command.index("up_under_lifecycle_lock") < deploy_command.index("smoke")
    assert deploy_command.index("smoke") < deploy_command.index(
        "finalize_preserved_runtime_writers"
    )
    assert deploy_command.index("finalize_preserved_runtime_writers") < deploy_command.index(
        "release_migrator_lifecycle_lock"
    )
    deploy_dagster = _function_body(deploy, "dagster_up")
    assert deploy_dagster.index("acquire_migrator_lifecycle_lock") < deploy_dagster.index(
        "dagster_up_under_lifecycle_lock"
    )
    assert deploy_dagster.index("dagster_up_under_lifecycle_lock") < deploy_dagster.index(
        "release_migrator_lifecycle_lock"
    )
    assert (
        'wait_for_url "http://127.0.0.1:${DAGSTER_PORT}/server_info" "Dagster"'
        in _function_body(deploy, "dagster_up_under_lifecycle_lock")
    )


def test_deploy_node_seals_fresh_migration_before_reusing_the_stack() -> None:
    source = (ROOT / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    migrate = _function_body(source, "migrate")
    deploy = _function_body(source, "deploy")
    up = _function_body(source, "up")
    dagster = _function_body(source, "dagster_up")

    assert migrate.index("migrate_under_lifecycle_lock") < migrate.index("write_fresh_stack_state")
    assert (
        deploy.index("migrate_under_lifecycle_lock")
        < deploy.index("write_fresh_stack_state")
        < deploy.index("up_under_lifecycle_lock")
    )
    assert "require_reusable_fresh_stack_contract" in up
    assert "require_reusable_fresh_stack_contract" in dagster


def test_fresh_continuation_is_bound_to_the_canonical_compose_and_database_proof() -> None:
    source = (ROOT / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    assert "require_canonical_compose_file" in source
    assert "version=3" in source
    assert "compose_sha256" in source
    assert "environment_source_sha256" in source
    assert "db_system_identifier" in source
    assert 'state_alembic_version" == "20260824_0101"' in source
    assert "migration_receipt_sha256" in source
    assert "capture_fresh_stack_migration_proof" in source


def test_observability_container_names_are_project_scoped() -> None:
    compose = (ROOT / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    for service in ("dagster", "cadvisor", "blackbox", "prometheus", "grafana"):
        assert f"container_name: ${{PINVI_DOCKER_PROJECT:-pinvi-app}}-{service}" in compose


def test_dev_compose_does_not_use_global_container_names() -> None:
    compose = (ROOT / "infra/docker-compose.yml").read_text(encoding="utf-8")
    assert "container_name:" not in compose

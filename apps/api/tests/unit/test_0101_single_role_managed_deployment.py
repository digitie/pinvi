"""ADR-46/070: 0101의 fail-closed 게이트가 단일 scoped app role 배포도 허용한다.

`_activate_m05_migration_owner`는 원래 두 가지 경로만 알았다: 4-role M05 전체
설정(migration_owner+migrator_login), 또는 아무것도 설정하지 않은 "관리 대상이 아닌"
설치(로컬/테스트). production에서 `PINVI_APP_DB_USER`만 설정하고 M05의 나머지 셋을
비우면 `_managed_deployment_requires_migration_owner()`가 무조건 거부했다 —
공용 control-plane instance로 옮긴 뒤 실제로 이 상태가 됐다(Manager
kor-travel-docker-manager PR #382가 M05를 폐기하고 geo 패턴 단일 role로 접었다).

여기서 검증하는 것은 **그 세 번째 경로**뿐이다. 기존 두 경로(전체 M05, 완전 비움)의
동작은 이 파일이 아니라 `test_m05_migration_role_wiring.py`(구조)와 통합 테스트가
계속 지킨다 — 이 파일은 새로 생긴 분기만 좁게 본다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260824_0101_m05_activation_contract.py"
)

_ROLE_ENV_NAMES = (
    "PINVI_MIGRATION_OWNER",
    "PINVI_MIGRATOR_DB_USER",
    "PINVI_APP_DB_USER",
    "PINVI_APP_SCHEMA_OWNER",
    "PINVI_M05_LEGACY_REBASELINE",
    "PINVI_ENVIRONMENT",
)


def _migration_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m05_single_role_gate", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_role_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ROLE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_single_role_production_deployment_succeeds_without_m05(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이것이 이번 변경의 요지다 — 종전에는 여기서 RuntimeError였다."""

    monkeypatch.setenv("PINVI_ENVIRONMENT", "production")
    monkeypatch.setenv("PINVI_APP_DB_USER", "pinvi_app")

    module = _migration_module()
    result = module._activate_m05_migration_owner(cast(Any, None))

    assert result == "pinvi_app"


def test_single_role_staging_deployment_also_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PINVI_ENVIRONMENT", "staging")
    monkeypatch.setenv("PINVI_APP_DB_USER", "pinvi_app")

    module = _migration_module()
    result = module._activate_m05_migration_owner(cast(Any, None))

    assert result == "pinvi_app"


def test_production_with_nothing_configured_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기존 안전망은 그대로다 — app role조차 없는 production은 여전히 거부한다."""

    monkeypatch.setenv("PINVI_ENVIRONMENT", "production")

    module = _migration_module()
    with pytest.raises(
        RuntimeError, match="0101 managed migration requires migration and migrator roles"
    ):
        module._activate_m05_migration_owner(cast(Any, None))


def test_legacy_rebaseline_still_requires_full_m05_even_with_app_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """legacy rebaseline은 새 경로로 새지 않는다 — 여전히 migration_owner/migrator를 요구한다."""

    monkeypatch.setenv("PINVI_ENVIRONMENT", "production")
    monkeypatch.setenv("PINVI_APP_DB_USER", "pinvi_app")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE", "1")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE", "n150-production")

    module = _migration_module()
    with pytest.raises(
        RuntimeError, match="0101 managed migration requires migration and migrator roles"
    ):
        module._activate_m05_migration_owner(cast(Any, None))


def test_partially_configured_m05_still_fails_closed_with_app_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """새 경로는 M05 role 둘 다 비었을 때만 연다 — 하나만 있으면 여전히 거부."""

    monkeypatch.setenv("PINVI_ENVIRONMENT", "production")
    monkeypatch.setenv("PINVI_APP_DB_USER", "pinvi_app")
    monkeypatch.setenv("PINVI_MIGRATION_OWNER", "pinvi_migration_owner")

    module = _migration_module()
    with pytest.raises(
        RuntimeError, match="0101 managed migration requires migration and migrator roles"
    ):
        module._activate_m05_migration_owner(cast(Any, None))


def test_local_dev_without_app_role_still_returns_none() -> None:
    """관리 대상이 아닌 설치(PINVI_ENVIRONMENT 미설정, app role도 없음)는 그대로 no-op."""

    module = _migration_module()
    result = module._activate_m05_migration_owner(cast(Any, None))

    assert result is None

"""env-file에 선언한 설정이 컨테이너에 **도달하는지** 확인한다.

2026-09-02: Manager 격리 하네스가 `PINVI_RATE_LIMIT_ENABLED=false`를 env-file에
넣었는데 `infra/docker-compose.app.yml`의 `app-api` environment 블록이
`PINVI_RATE_LIMIT_BACKEND`만 매핑하고 있었다. compose의 `--env-file`은 **파일의
값을 `${...}` 보간에만** 쓰고 컨테이너 환경으로 자동 전달하지 않으므로, 그 설정은
조용히 무시되고 기본값 `True`가 살았다.

결과: `/auth/login`(auth_low, 5회/분, 키=(ip, email))에 M04·M05 로그인이 같은
버킷으로 몰려 429가 났고, 그 실패는 **1~2시간짜리 격리 e2e를 태운 뒤에야** 드러났다.
게다가 attestation의 `_http_json`이 `HTTPError`를 `URLError`·`OSError`와 같은
문자열로 접어 429라는 사실조차 보이지 않았다.

같은 사실이 두 곳에 독립 선언되고 둘을 묶는 기계가 없던 것이다 — 이 파일이 그
기계다.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[4]
_COMPOSE = _ROOT / "infra/docker-compose.app.yml"

# 격리 하네스와 배포 스크립트가 **실제로 넘기는** 설정. 여기 있으면 compose의
# environment 블록에도 있어야 한다 — 없으면 조용히 무시된다.
#
# 목록을 손으로 두는 대신 아래에서 소스에서 유도한다. 이 상수는 유도가 아무것도
# 찾지 못했을 때를 잡는 하한이다(자기검증).
_MINIMUM_DELIVERED = frozenset({"PINVI_RATE_LIMIT_ENABLED"})

_ASSIGNMENT = re.compile(r'"(PINVI_[A-Z0-9_]+)=')


def _compose_environment(service: str) -> set[str]:
    document = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    environment = document["services"][service]["environment"]
    if isinstance(environment, dict):
        return set(environment)
    return {entry.split("=", 1)[0] for entry in environment}


def _settings_declared_by_the_manager_harness() -> set[str]:
    """Manager 격리 하네스가 env-file에 쓰는 `PINVI_*` 설정.

    형제 저장소를 읽는다. 없으면(체크아웃되지 않은 CI 등) 검사를 건너뛰지 않고
    **최소 집합**으로 떨어진다 — 건너뛰면 이 검사가 조용히 무효가 된다.
    """

    harness = _ROOT.parent / "kor-travel-docker-manager/scripts/m05_isolated_e2e.py"
    if not harness.is_file():
        return set(_MINIMUM_DELIVERED)
    text = harness.read_text(encoding="utf-8", errors="ignore")
    return {name for name in _ASSIGNMENT.findall(text)}


def test_app_api_delivers_every_pinvi_setting_the_harness_declares() -> None:
    """하네스가 선언한 `PINVI_*`가 compose environment에 있어야 한다.

    compose는 `--env-file`의 값을 `${...}` 보간에만 쓴다. environment 블록에 없는
    이름은 컨테이너에 **도달하지 않고**, 그 사실은 아무 데서도 드러나지 않는다.
    """

    declared = _settings_declared_by_the_manager_harness()
    assert declared >= _MINIMUM_DELIVERED, (
        "하네스에서 PINVI_* 선언을 찾지 못했다 — 유도가 깨졌다: " + repr(sorted(declared))
    )

    delivered = _compose_environment("app-api")
    # compose가 다른 서비스에서 소비하거나 보간 전용으로 쓰는 것도 있다.
    # 여기서 보는 것은 **app-api의 런타임 동작을 바꾸는** 설정이다.
    runtime_scoped = {
        name
        for name in declared
        if name.startswith(("PINVI_RATE_LIMIT_", "PINVI_GEOFENCE_", "PINVI_CORS_"))
    }
    assert runtime_scoped, "런타임 설정을 하나도 찾지 못했다 — 이 검사가 공허해졌다"

    missing = sorted(runtime_scoped - delivered)
    assert not missing, (
        "하네스가 넘기지만 app-api environment에 없어 **조용히 무시되는** 설정: " + repr(missing)
    )


def test_rate_limit_settings_are_deliverable_and_documented() -> None:
    """rate limit 세 값이 모두 매핑돼 있어야 한다.

    `ENABLED`만 있고 `AUTH_PER_MINUTE`가 없으면, 한도를 조정하려는 시도가 같은
    방식으로 조용히 무시된다.
    """

    delivered = _compose_environment("app-api")
    required = {
        "PINVI_RATE_LIMIT_ENABLED",
        "PINVI_RATE_LIMIT_BACKEND",
        "PINVI_RATE_LIMIT_AUTH_PER_MINUTE",
    }

    assert required <= delivered, "app-api environment에 없는 rate limit 설정: " + repr(
        sorted(required - delivered)
    )


def test_login_is_rate_limited_and_the_harness_can_turn_it_off() -> None:
    """이 검사가 지키려는 사실 자체를 코드로 고정한다.

    `/auth/login`이 auth_low 정책 아래 있고 그 정책의 키가 (ip, email)이라는 것이
    2026-09-02 실패의 기전이다. 정책이 바뀌면 이 파일의 존재 이유도 바뀌므로
    함께 깨져야 한다.
    """

    from app.core.config import Settings
    from app.middleware.rate_limit import AUTH_LOW_PATHS, rate_limit_policy_for_name

    assert "/auth/login" in AUTH_LOW_PATHS
    policy = rate_limit_policy_for_name("auth_low")
    assert policy.identity_kind == "ip_email"
    # 기본값이 True라는 것이 "전달되지 않으면 켜진 채로 남는다"의 근거다.
    assert Settings.model_fields["pinvi_rate_limit_enabled"].default is True

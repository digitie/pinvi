"""API Admin ETL 요약의 정적 asset·job·schedule·sensor 목록을 이 code location의 정의에 묶는다(T-377).

`apps/api/app/services/admin_etl.py`의 `PINVI_ETL_SCHEDULES`·`PINVI_ETL_SENSORS`는 Dagster가 죽어 있어도
"무엇이 구성돼 있나"를 보여 주는 정적 사본이다. 정의에 schedule·sensor가 늘었는데 사본을 고치지 않아 같은
payload 안에서 `pinvi.schedules`(5)와 live `schedule_count`(7), 빈 `sensors`와 `sensor_count`(6)가 어긋났다.

API 패키지는 이 환경에 없으므로 `test_admin_probe_graphql_schema.py`처럼 소스를 AST로 읽는다 — 목록 원소는
`AdminEtlDefinition*(...)` 호출이고 인자는 전부 키워드 리터럴이어야 한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from dagster import DagsterError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ADMIN_ETL = _REPO_ROOT / "apps" / "api" / "app" / "services" / "admin_etl.py"


def _static_entries(name: str, call: str) -> list[dict[str, object]]:
    module = ast.parse(_ADMIN_ETL.read_text(encoding="utf-8"))
    lists = [
        node.value
        for node in module.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and any(
            isinstance(t, ast.Name) and t.id == name
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert len(lists) == 1, f"{name}를 정확히 하나 찾지 못했다: {_ADMIN_ETL}"
    value = lists[0]
    assert isinstance(value, ast.List), f"{name}는 리스트 리터럴이어야 한다"
    entries: list[dict[str, object]] = []
    for element in value.elts:
        assert isinstance(element, ast.Call), ast.unparse(element)
        assert isinstance(element.func, ast.Name) and element.func.id == call, ast.unparse(element)
        assert not element.args, f"키워드 인자만 쓴다: {ast.unparse(element)}"
        entry: dict[str, object] = {}
        for keyword in element.keywords:
            assert keyword.arg is not None, ast.unparse(element)
            # 리터럴만 허용한다(문자열·None·문자열 리스트) — 계산식이면 literal_eval이 거부한다.
            entry[keyword.arg] = ast.literal_eval(keyword.value)
        entries.append(entry)
    return entries


def test_static_schedules_match_definitions() -> None:
    from pinvi.etl.definitions import defs

    defined = {
        (s.name, s.job_name, s.cron_schedule, s.execution_timezone)
        for s in defs.get_repository_def().schedule_defs
    }
    static = [
        (e["name"], e["job_name"], e["cron_schedule"], e.get("execution_timezone"))
        for e in _static_entries("PINVI_ETL_SCHEDULES", "AdminEtlDefinitionSchedule")
    ]
    # 하한은 본 것에 건다 — 빈 정의·빈 사본이 항진명제로 통과하지 않게.
    assert len(defined) >= 7
    assert len(static) == len(set(static)), "중복 항목"
    assert set(static) == defined


def _sensor_job_name(sensor: object) -> str | None:
    try:
        job_name = sensor.job_name  # type: ignore[attr-defined]
    except DagsterError:  # 대상 job이 없거나(run status sensor) 여럿이다
        return None
    assert job_name is None or isinstance(job_name, str)
    return job_name


def test_static_sensors_match_definitions() -> None:
    from pinvi.etl.definitions import defs

    defined = {
        (sensor.name, _sensor_job_name(sensor)) for sensor in defs.get_repository_def().sensor_defs
    }
    static = [
        (e["name"], e.get("job_name"))
        for e in _static_entries("PINVI_ETL_SENSORS", "AdminEtlDefinitionSensor")
    ]
    assert len(defined) >= 6
    assert len(static) == len(set(static)), "중복 항목"
    assert set(static) == defined


def test_static_assets_match_definitions() -> None:
    """asset key·group만 대조한다 — description은 사람이 쓴 요약이라 대조하지 않는다."""
    from pinvi.etl.definitions import defs

    defined = {
        (node.key.to_user_string(), node.group_name)
        for node in defs.resolve_asset_graph().asset_nodes
    }
    static = [
        (e["key"], e["group_name"])
        for e in _static_entries("PINVI_ETL_ASSETS", "AdminEtlDefinitionAsset")
    ]
    assert len(defined) >= 7
    assert len(static) == len(set(static)), "중복 항목"
    assert set(static) == defined


def test_static_jobs_match_definitions() -> None:
    """job 이름과 그 job이 고르는 asset key를 대조한다 — trigger·description은 대조하지 않는다."""
    from pinvi.etl.definitions import defs

    defined = {
        (job.name, frozenset(k.to_user_string() for k in job.asset_layer.selected_asset_keys))
        for job in defs.get_repository_def().get_all_jobs()
        if not job.name.startswith("__")  # Dagster가 만드는 암묵 `__ASSET_JOB`
    }
    static = [
        (e["name"], frozenset(e.get("asset_keys") or []))
        for e in _static_entries("PINVI_ETL_JOBS", "AdminEtlDefinitionJob")
    ]
    assert len(defined) >= 8
    assert len(static) == len(set(static)), "중복 항목"
    assert set(static) == defined

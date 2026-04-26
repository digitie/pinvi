from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


def test_legal_dong_code_airflow_dag_contract(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "legal_dong_code_standard.py")

    dag_kwargs = captured["dag_kwargs"]
    assert captured["module"].DAG_ID == "legal_dong_code_standard_quarterly"
    assert dag_kwargs["dag_id"] == "legal_dong_code_standard_quarterly"
    assert dag_kwargs["schedule"] == "30 4 15 2,5,8,11 *"
    assert str(dag_kwargs["start_date"].tzinfo) == "Asia/Seoul"
    assert dag_kwargs["catchup"] is False
    assert dag_kwargs["max_active_runs"] == 1
    assert dag_kwargs["default_args"]["retries"] == 3
    assert dag_kwargs["default_args"]["retry_delay"].total_seconds() == 300
    assert captured["task_kwargs"] == [{"task_id": "download_and_load_legal_dong_code_standard"}]
    assert captured["task_function_name"] == "download_and_load"
    assert captured["task_invoked_during_dag_build"] is True


def test_juso_monthly_address_airflow_dag_contract(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "juso_monthly_address.py")

    dag_kwargs = captured["dag_kwargs"]
    assert captured["module"].DAG_ID == "juso_monthly_address_dataset"
    assert dag_kwargs["dag_id"] == "juso_monthly_address_dataset"
    assert dag_kwargs["schedule"] == "0 4 10-31 * *"
    assert str(dag_kwargs["start_date"].tzinfo) == "Asia/Seoul"
    assert dag_kwargs["catchup"] is False
    assert dag_kwargs["max_active_runs"] == 1
    assert dag_kwargs["default_args"]["retries"] == 3
    assert dag_kwargs["default_args"]["retry_delay"].total_seconds() == 300
    assert captured["task_kwargs"] == [{"task_id": "download_and_load_juso_monthly_address"}]
    assert captured["task_function_name"] == "download_and_load"
    assert captured["task_invoked_during_dag_build"] is True


def test_opinet_fuel_airflow_dag_contracts(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "opinet_fuel.py")

    dag_kwargs_list = captured["dag_kwargs_list"]
    task_kwargs_list = captured["task_kwargs"]

    assert [kwargs["dag_id"] for kwargs in dag_kwargs_list] == [
        "opinet_region_code_quarterly",
        "opinet_avg_price_daily",
        "opinet_lowest_station_daily",
    ]
    assert [kwargs["schedule"] for kwargs in dag_kwargs_list] == [
        "0 4 1 1,4,7,10 *",
        "20 5,13,21 * * *",
        "40 5,13,21 * * *",
    ]
    assert all(str(kwargs["start_date"].tzinfo) == "Asia/Seoul" for kwargs in dag_kwargs_list)
    assert all(kwargs["catchup"] is False for kwargs in dag_kwargs_list)
    assert all(kwargs["max_active_runs"] == 1 for kwargs in dag_kwargs_list)
    assert [kwargs["default_args"]["retries"] for kwargs in dag_kwargs_list] == [3, 3, 3]
    assert [
        kwargs["default_args"]["retry_delay"].total_seconds() for kwargs in dag_kwargs_list
    ] == [1800, 300, 300]
    assert task_kwargs_list == [
        {"task_id": "load_opinet_region_codes"},
        {"task_id": "load_opinet_avg_prices"},
        {"task_id": "load_opinet_lowest_stations_for_all_sigungu"},
    ]
    assert captured["task_invocation_count"] == 3
    parsed = captured["module"]._parse_airflow_datetime("2026-05-01T04:00:00+09:00")
    assert parsed.strftime("%Y%m%dT%H%M%S") == "20260501T040000"


def test_rest_area_airflow_dag_contracts(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "rest_area.py")

    dag_kwargs_list = captured["dag_kwargs_list"]

    assert [kwargs["dag_id"] for kwargs in dag_kwargs_list] == [
        "rest_area_master_monthly",
        "rest_area_oil_price_daily",
        "rest_area_service_monthly",
    ]
    assert [kwargs["schedule"] for kwargs in dag_kwargs_list] == [
        "10 4 1 * *",
        "10 6,18 * * *",
        "30 4 1 * *",
    ]
    assert all(str(kwargs["start_date"].tzinfo) == "Asia/Seoul" for kwargs in dag_kwargs_list)
    assert all(kwargs["catchup"] is False for kwargs in dag_kwargs_list)
    assert all(kwargs["max_active_runs"] == 1 for kwargs in dag_kwargs_list)
    assert [kwargs["default_args"]["retries"] for kwargs in dag_kwargs_list] == [3, 3, 3]
    assert [
        kwargs["default_args"]["retry_delay"].total_seconds() for kwargs in dag_kwargs_list
    ] == [1800, 600, 1800]
    assert captured["task_kwargs"] == [
        {"task_id": "load_rest_area_master"},
        {"task_id": "load_rest_area_oil_prices"},
        {"task_id": "load_rest_area_services"},
    ]
    assert captured["task_invocation_count"] == 3


def test_weather_air_quality_airflow_dag_contracts(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "weather_air_quality.py")

    dag_kwargs_list = captured["dag_kwargs_list"]

    assert [kwargs["dag_id"] for kwargs in dag_kwargs_list] == [
        "weather_short_term_sigungu_grid",
        "weather_kma_alert",
        "weather_mid_term_nationwide",
        "air_quality_station_daily",
        "air_quality_forecast_daily",
        "air_quality_sido_measurement_hourly",
        "kma_recommended_tour_course_annual",
    ]
    assert [kwargs["schedule"] for kwargs in dag_kwargs_list] == [
        "*/30 * * * *",
        "*/30 * * * *",
        "20 6,18 * * *",
        "20 4 * * *",
        "15 5,11,17,23 * * *",
        "25 * * * *",
        "0 5 1 3 *",
    ]
    assert all(str(kwargs["start_date"].tzinfo) == "Asia/Seoul" for kwargs in dag_kwargs_list)
    assert all(kwargs["catchup"] is False for kwargs in dag_kwargs_list)
    assert all(kwargs["max_active_runs"] == 1 for kwargs in dag_kwargs_list)
    assert [kwargs["default_args"]["retries"] for kwargs in dag_kwargs_list] == [
        3,
        3,
        3,
        3,
        3,
        3,
        3,
    ]
    assert [
        kwargs["default_args"]["retry_delay"].total_seconds() for kwargs in dag_kwargs_list
    ] == [300, 300, 600, 1800, 600, 600, 1800]
    assert captured["task_kwargs"] == [
        {"task_id": "load_weather_short_term"},
        {"task_id": "load_weather_kma_alerts"},
        {"task_id": "load_weather_mid_term"},
        {"task_id": "load_air_quality_stations"},
        {"task_id": "load_air_quality_forecasts"},
        {"task_id": "load_air_quality_sido_measurements"},
        {"task_id": "load_kma_recommended_tour_course"},
    ]
    assert captured["task_invocation_count"] == 7
    parsed = captured["module"]._parse_airflow_datetime("2026-05-01T04:00:00+09:00")
    assert parsed.strftime("%Y%m%dT%H%M%S") == "20260501T040000"


def test_airflow_retry_exhaustion_uses_task_instance(monkeypatch: Any) -> None:
    captured = _load_dag_with_fake_airflow(monkeypatch, "juso_monthly_address.py")

    sdk_module = types.ModuleType("airflow.sdk")

    class RetryableTaskInstance:
        def is_eligible_to_retry(self) -> bool:
            return True

    class ExhaustedTaskInstance:
        def is_eligible_to_retry(self) -> bool:
            return False

    sdk_any: Any = sdk_module
    sdk_any.get_current_context = lambda: {"ti": RetryableTaskInstance()}
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk_module)

    assert captured["module"]._is_airflow_retry_exhausted() is False

    sdk_any.get_current_context = lambda: {"ti": ExhaustedTaskInstance()}
    assert captured["module"]._is_airflow_retry_exhausted() is True


def _load_dag_with_fake_airflow(monkeypatch: Any, file_name: str) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    airflow_module = types.ModuleType("airflow")
    decorators_module = types.ModuleType("airflow.decorators")

    def fake_dag(**kwargs: Any) -> Any:
        captured["dag_kwargs"] = kwargs
        captured.setdefault("dag_kwargs_list", []).append(kwargs)

        def decorator(function: Any) -> Any:
            captured["dag_function_name"] = function.__name__
            captured.setdefault("dag_function_names", []).append(function.__name__)
            return function

        return decorator

    def fake_task(**kwargs: Any) -> Any:
        captured.setdefault("task_kwargs", []).append(kwargs)

        def decorator(function: Any) -> Any:
            captured["task_function_name"] = function.__name__

            def wrapped(*args: Any, **inner_kwargs: Any) -> None:
                captured["task_invoked_during_dag_build"] = True
                captured["task_invocation_count"] = captured.get("task_invocation_count", 0) + 1
                return None

            return wrapped

        return decorator

    decorators_any: Any = decorators_module
    decorators_any.dag = fake_dag
    decorators_any.task = fake_task
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.decorators", decorators_module)

    dag_path = Path(__file__).resolve().parents[3] / "dags" / file_name
    module_name = file_name.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(module_name, dag_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured["module"] = module
    return captured

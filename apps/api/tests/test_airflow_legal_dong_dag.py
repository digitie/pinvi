from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


def test_legal_dong_code_airflow_dag_contract(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    airflow_module = types.ModuleType("airflow")
    decorators_module = types.ModuleType("airflow.decorators")

    def fake_dag(**kwargs: Any) -> Any:
        captured["dag_kwargs"] = kwargs

        def decorator(function: Any) -> Any:
            captured["dag_function_name"] = function.__name__
            return function

        return decorator

    def fake_task(**kwargs: Any) -> Any:
        captured.setdefault("task_kwargs", []).append(kwargs)

        def decorator(function: Any) -> Any:
            captured["task_function_name"] = function.__name__

            def wrapped(*args: Any, **inner_kwargs: Any) -> None:
                captured["task_invoked_during_dag_build"] = True
                return None

            return wrapped

        return decorator

    decorators_any: Any = decorators_module
    decorators_any.dag = fake_dag
    decorators_any.task = fake_task
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.decorators", decorators_module)

    dag_path = Path(__file__).resolve().parents[3] / "dags" / "legal_dong_code_standard.py"
    spec = importlib.util.spec_from_file_location("legal_dong_code_standard", dag_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dag_kwargs = captured["dag_kwargs"]
    assert module.DAG_ID == "legal_dong_code_standard_quarterly"
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

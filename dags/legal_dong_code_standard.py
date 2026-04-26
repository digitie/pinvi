from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

DAG_ID = "legal_dong_code_standard_quarterly"
DEFAULT_DOWNLOAD_DIR = "/tmp/tripmate-airflow/legal-dong-code-standard"


def _ensure_api_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    api_dir = repo_root / "apps" / "api"
    api_path = str(api_dir)
    if api_path not in sys.path:
        sys.path.insert(0, api_path)


@dag(
    dag_id=DAG_ID,
    description="Download data.go.kr legal-dong code CSV and refresh TripMate code standard.",
    schedule="30 4 15 2,5,8,11 *",
    start_date=datetime(2026, 5, 15, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["tripmate", "address", "legal-dong-code", "data-go"],
)
def legal_dong_code_standard_quarterly() -> None:
    @task(task_id="download_and_load_legal_dong_code_standard")
    def download_and_load() -> dict[str, Any]:
        database_url = os.environ["TRIPMATE_DATABASE_URL"]
        download_dir = Path(
            os.environ.get("TRIPMATE_AIRFLOW_DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR)
        )

        _ensure_api_on_path()

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.etl.vworld.legal_dong_code_loader import (
            DATA_GO_LEGAL_DONG_PAGE_URL,
            load_latest_legal_dong_code_from_data_go,
        )

        engine = create_engine(database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        try:
            with session_factory() as session:
                result = load_latest_legal_dong_code_from_data_go(session, download_dir)
                session.commit()
                payload = asdict(result)
                payload["page_url"] = DATA_GO_LEGAL_DONG_PAGE_URL
                payload["download_dir"] = str(download_dir)
                return payload
        finally:
            engine.dispose()

    download_and_load()


legal_dong_code_standard_quarterly()

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.etl_config import get_etl_dataset_config
from app.db.session import build_engine, build_session_factory
from app.etl.vworld.boundary_loader import VWorldBoundaryLoadResult, load_vworld_boundary_zip
from app.models.etl import EtlRunLog
from app.services.etl_runtime import (
    create_etl_run_log,
    mark_etl_run_failed,
    mark_etl_run_success,
)

DATASET_KEY = "vworld_boundary_upload"
SessionFactory = Callable[[], Session]


def import_vworld_boundary_archives(
    session_factory: SessionFactory,
    zip_paths: Sequence[Path | str],
) -> list[VWorldBoundaryLoadResult]:
    return [
        import_vworld_boundary_archive(session_factory, Path(zip_path)) for zip_path in zip_paths
    ]


def import_vworld_boundary_archive(
    session_factory: SessionFactory,
    zip_path: Path,
) -> VWorldBoundaryLoadResult:
    runtime_config = get_etl_dataset_config(DATASET_KEY)
    source_path = Path(zip_path)

    with session_factory() as log_session:
        run_log = create_etl_run_log(
            log_session,
            dataset_key=DATASET_KEY,
            run_key=source_path.stem,
            run_type="manual",
            trigger_date=None,
            config=runtime_config,
        )
        run_log_id = run_log.id
        log_session.commit()

    try:
        with session_factory() as load_session:
            result = load_vworld_boundary_zip(load_session, source_path)
            load_session.commit()

        with session_factory() as log_session:
            resolved_run_log = log_session.get(EtlRunLog, run_log_id)
            if resolved_run_log is None:
                raise RuntimeError(f"ETL run log not found: {run_log_id}")
            mark_etl_run_success(
                resolved_run_log,
                message=f"VWorld SHP 적재 성공: {source_path.name}",
                extra=asdict(result),
            )
            log_session.commit()
        return result
    except Exception as exc:
        with session_factory() as log_session:
            resolved_run_log = log_session.get(EtlRunLog, run_log_id)
            if resolved_run_log is None:
                raise RuntimeError(f"ETL run log not found: {run_log_id}") from exc
            mark_etl_run_failed(
                log_session,
                resolved_run_log,
                error=exc,
                message=f"VWorld SHP 적재 실패: {source_path.name}",
                exhausted=True,
                config=runtime_config,
            )
            log_session.commit()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VWorld 행정경계 SHP ZIP을 DB에 적재한다.")
    parser.add_argument("zip_paths", nargs="+", help="N3A_G0010000.zip 등 VWorld SHP ZIP 경로")
    parser.add_argument("--database-url", help="TRIPMATE_DATABASE_URL 대신 사용할 DB URL")
    args = parser.parse_args(argv)

    engine = build_engine(args.database_url)
    session_factory = build_session_factory(engine=engine)
    try:
        results = import_vworld_boundary_archives(session_factory, args.zip_paths)
        for result in results:
            print(
                f"{result.source_file_name}: {result.boundary_level} "
                f"{result.row_count} rows, {result.address_code_match_count} code matches"
            )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

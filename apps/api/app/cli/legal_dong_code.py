from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.etl_config import get_etl_dataset_config
from app.db.session import build_engine, build_session_factory
from app.etl.vworld.legal_dong_code_loader import (
    LegalDongCodeCsvLoadResult,
    load_legal_dong_code_csv,
    load_legal_dong_code_zip,
)
from app.models.etl import EtlRunLog
from app.services.etl_runtime import (
    create_etl_run_log,
    mark_etl_run_failed,
    mark_etl_run_success,
)

DATASET_KEY = "legal_dong_code_standard"
SessionFactory = Callable[[], Session]


def import_legal_dong_code_source(
    session_factory: SessionFactory,
    source_path: Path | str,
) -> LegalDongCodeCsvLoadResult:
    runtime_config = get_etl_dataset_config(DATASET_KEY)
    resolved_source_path = Path(source_path)

    with session_factory() as log_session:
        run_log = create_etl_run_log(
            log_session,
            dataset_key=DATASET_KEY,
            run_key=resolved_source_path.stem,
            run_type="manual",
            trigger_date=None,
            config=runtime_config,
        )
        run_log_id = run_log.id
        log_session.commit()

    try:
        with session_factory() as load_session:
            result = _load_source(load_session, resolved_source_path)
            load_session.commit()

        with session_factory() as log_session:
            resolved_run_log = log_session.get(EtlRunLog, run_log_id)
            if resolved_run_log is None:
                raise RuntimeError(f"ETL run log not found: {run_log_id}")
            mark_etl_run_success(
                resolved_run_log,
                message=f"법정동코드 기준 파일 적재 성공: {resolved_source_path.name}",
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
                message=f"법정동코드 기준 파일 적재 실패: {resolved_source_path.name}",
                exhausted=True,
                config=runtime_config,
            )
            log_session.commit()
        raise


def _load_source(session: Session, source_path: Path) -> LegalDongCodeCsvLoadResult:
    suffix = source_path.suffix.lower()
    if suffix == ".zip":
        return load_legal_dong_code_zip(session, source_path)
    if suffix == ".csv":
        return load_legal_dong_code_csv(session, source_path)
    raise ValueError(f"Unsupported legal-dong code source file: {source_path.name}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="법정동코드 CSV/ZIP을 DB에 적재한다.")
    parser.add_argument("source_path", help="법정동코드 CSV 또는 ZIP 경로")
    parser.add_argument("--database-url", help="TRIPMATE_DATABASE_URL 대신 사용할 DB URL")
    args = parser.parse_args(argv)

    engine = build_engine(args.database_url)
    session_factory = build_session_factory(engine=engine)
    try:
        result = import_legal_dong_code_source(session_factory, args.source_path)
        print(
            f"{result.source_file_name}: raw={result.raw_row_count}, "
            f"active={result.active_code_count}, discontinued={result.discontinued_code_count}"
        )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

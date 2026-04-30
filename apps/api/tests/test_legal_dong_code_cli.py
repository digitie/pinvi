from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cli.legal_dong_code import import_legal_dong_code_source
from app.models.address import AddressCodeStandard
from app.models.etl import AdminNotification, EtlRunLog, TelegramSystemNotificationOutbox


def test_import_legal_dong_code_source_records_success_log(
    db_session: Session,
    tmp_path: Path,
) -> None:
    session_factory = _build_session_factory(db_session)
    source_path = _write_data_go_code_csv(tmp_path)

    result = import_legal_dong_code_source(session_factory, source_path)

    with session_factory() as verify_session:
        run_log = verify_session.scalar(select(EtlRunLog))
        address_code = verify_session.get(AddressCodeStandard, "1111010100")

        assert result.active_code_count == 3
        assert run_log is not None
        assert run_log.dataset_key == "legal_dong_code_standard"
        assert run_log.run_type == "manual"
        assert run_log.status == "success"
        assert address_code is not None
        assert address_code.full_legal_dong_name == "서울특별시 종로구 청운동"


def test_import_legal_dong_code_source_persists_failure_log(
    db_session: Session,
    tmp_path: Path,
) -> None:
    session_factory = _build_session_factory(db_session)
    source_path = tmp_path / "bad.txt"
    source_path.write_text("not a supported source", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported legal-dong code source file"):
        import_legal_dong_code_source(session_factory, source_path)

    with session_factory() as verify_session:
        run_log = verify_session.scalar(select(EtlRunLog))
        admin_notification = verify_session.scalar(select(AdminNotification))
        telegram_outbox = verify_session.scalar(select(TelegramSystemNotificationOutbox))

        assert run_log is not None
        assert run_log.status == "failed"
        assert run_log.dataset_key == "legal_dong_code_standard"
        assert admin_notification is not None
        assert admin_notification.etl_run_log_id == run_log.id
        assert telegram_outbox is not None
        assert telegram_outbox.etl_run_log_id == run_log.id


def _build_session_factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)


def _write_data_go_code_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "국토교통부_전국 법정동_20250807.csv"
    csv_path.write_text(
        "\n".join(
            [
                "법정동코드,시도명,시군구명,읍면동명,리명,순위,생성일자,삭제일자,과거법정동코드",
                "1100000000,서울특별시,,,,11,1988-04-23,,",
                "1111000000,서울특별시,종로구,,,1,1988-04-23,,",
                "1111010100,서울특별시,종로구,청운동,,1,1988-04-23,,",
            ]
        ),
        encoding="utf-8",
    )
    return csv_path

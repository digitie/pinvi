from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.etl_config import get_etl_dataset_config
from app.models.etl import AdminNotification, TelegramSystemNotificationOutbox
from app.models.trip import Trip
from app.models.user import User
from app.services.etl_runtime import (
    create_etl_run_log,
    mark_etl_run_failed,
    mark_etl_run_success,
    should_skip_juso_monthly_update,
)


def test_juso_monthly_update_skips_before_10th(db_session: Session) -> None:
    should_skip, run_key, reason = should_skip_juso_monthly_update(
        db_session,
        logical_date=date(2026, 4, 9),
    )

    assert should_skip is True
    assert run_key == "202604"
    assert "10일 이후" in reason


def test_juso_monthly_update_skips_when_trip_exists_on_logical_date(
    db_session: Session,
) -> None:
    user = User(
        email="admin@example.com",
        password_hash="hash",
        display_name="Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        Trip(
            user_id=user.id,
            title="봄 여행",
            destination="통영",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
            planning_status="planned",
        )
    )
    db_session.flush()

    should_skip, run_key, reason = should_skip_juso_monthly_update(
        db_session,
        logical_date=date(2026, 4, 11),
    )

    assert should_skip is True
    assert run_key == "202604"
    assert "여행계획 날짜" in reason


def test_juso_monthly_update_runs_after_10th_without_trip(db_session: Session) -> None:
    should_skip, run_key, reason = should_skip_juso_monthly_update(
        db_session,
        logical_date=date(2026, 4, 13),
    )

    assert should_skip is False
    assert run_key == "202604"
    assert "실행 가능" in reason


def test_juso_monthly_update_skips_after_successful_monthly_run(
    db_session: Session,
) -> None:
    config = get_etl_dataset_config("juso_road_address_korean")
    run_log = create_etl_run_log(
        db_session,
        dataset_key="juso_road_address_korean",
        run_key="202604",
        run_type="scheduled",
        trigger_date=date(2026, 4, 13),
        config=config,
    )
    mark_etl_run_success(run_log, message="ok")
    db_session.flush()

    should_skip, _, reason = should_skip_juso_monthly_update(
        db_session,
        logical_date=date(2026, 4, 14),
    )

    assert should_skip is True
    assert "이미 성공" in reason


def test_failed_etl_run_creates_admin_and_telegram_notifications(
    db_session: Session,
) -> None:
    run_log = create_etl_run_log(
        db_session,
        dataset_key="juso_road_address_korean",
        run_key="202604",
        run_type="scheduled",
        trigger_date=date(2026, 4, 13),
    )

    mark_etl_run_failed(
        db_session,
        run_log,
        error=RuntimeError("download failed"),
        message="Juso 다운로드 실패",
        exhausted=True,
    )
    db_session.flush()

    admin_notification = db_session.scalar(select(AdminNotification))
    telegram_outbox = db_session.scalar(select(TelegramSystemNotificationOutbox))

    assert run_log.status == "failed"
    assert run_log.error_type == "RuntimeError"
    assert admin_notification is not None
    assert admin_notification.recipient_scope == "admins"
    assert telegram_outbox is not None
    assert telegram_outbox.recipient_scope == "privileged_admins"


def test_failed_etl_run_redacts_sensitive_url_values(db_session: Session) -> None:
    run_log = create_etl_run_log(
        db_session,
        dataset_key="legal_dong_code_standard",
        run_key="20260426",
        run_type="scheduled",
        trigger_date=date(2026, 4, 26),
    )

    mark_etl_run_failed(
        db_session,
        run_log,
        error=RuntimeError(
            "GET https://www.data.go.kr/cmm/cmm/fileDownload.do?"
            "serviceKey=secret-service-key&file=1 failed"
        ),
        message="data.go.kr 다운로드 실패: serviceKey=secret-service-key",
        exhausted=True,
    )
    db_session.flush()

    telegram_outbox = db_session.scalar(select(TelegramSystemNotificationOutbox))

    assert "secret-service-key" not in (run_log.message or "")
    assert "secret-service-key" not in (run_log.error_message or "")
    assert "serviceKey=***" in (run_log.error_message or "")
    assert telegram_outbox is not None
    assert "secret-service-key" not in telegram_outbox.payload["error_message"]


def test_failed_etl_run_redacts_opinet_certkey_values(db_session: Session) -> None:
    run_log = create_etl_run_log(
        db_session,
        dataset_key="fuel_avg_price",
        run_key="20260426T050000",
        run_type="scheduled",
        trigger_date=date(2026, 4, 26),
    )

    mark_etl_run_failed(
        db_session,
        run_log,
        error=RuntimeError(
            "GET https://www.opinet.co.kr/api/avgAllPrice.do?"
            "certkey=secret-opinet-key&out=json failed"
        ),
        message="OpiNet request failed: certkey=secret-opinet-key",
        exhausted=True,
    )
    db_session.flush()

    telegram_outbox = db_session.scalar(select(TelegramSystemNotificationOutbox))

    assert "secret-opinet-key" not in (run_log.message or "")
    assert "secret-opinet-key" not in (run_log.error_message or "")
    assert "certkey=***" in (run_log.error_message or "")
    assert telegram_outbox is not None
    assert "secret-opinet-key" not in telegram_outbox.payload["error_message"]


def test_failed_etl_run_redacts_expressway_key_values(db_session: Session) -> None:
    run_log = create_etl_run_log(
        db_session,
        dataset_key="rest_area_oil_price",
        run_key="20260426T060000",
        run_type="scheduled",
        trigger_date=date(2026, 4, 26),
    )

    mark_etl_run_failed(
        db_session,
        run_log,
        error=RuntimeError(
            "GET https://data.ex.co.kr/openapi/business/curStateStation?"
            "key=secret-expressway-key&type=json failed"
        ),
        message="Expressway request failed: key=secret-expressway-key",
        exhausted=True,
    )
    db_session.flush()

    telegram_outbox = db_session.scalar(select(TelegramSystemNotificationOutbox))

    assert "secret-expressway-key" not in (run_log.message or "")
    assert "secret-expressway-key" not in (run_log.error_message or "")
    assert "key=***" in (run_log.error_message or "")
    assert telegram_outbox is not None
    assert "secret-expressway-key" not in telegram_outbox.payload["error_message"]


def test_failed_etl_run_before_retry_exhaustion_does_not_notify(db_session: Session) -> None:
    run_log = create_etl_run_log(
        db_session,
        dataset_key="juso_road_address_korean",
        run_key="202604",
        run_type="scheduled",
        trigger_date=date(2026, 4, 13),
    )

    mark_etl_run_failed(
        db_session,
        run_log,
        error=RuntimeError("temporary timeout"),
        message="Juso 다운로드 일시 실패",
        exhausted=False,
    )
    db_session.flush()

    assert db_session.scalar(select(AdminNotification)) is None
    assert db_session.scalar(select(TelegramSystemNotificationOutbox)) is None
    assert run_log.extra["retry_exhausted"] is False

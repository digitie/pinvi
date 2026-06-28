"""ADR-050 run-failure 통지 payload 단위 테스트 (T-291)."""

from __future__ import annotations

from datetime import UTC, datetime

from pinvi.etl.sensors import OUTBOX_CATEGORY, build_run_failure_payload


def test_payload_is_pii_free_identifiers_only() -> None:
    payload = build_run_failure_payload(
        job_name="pinvi_pii_retention_job",
        run_id="run-123",
        error_class="ValueError",
        occurred_at=datetime(2026, 6, 29, tzinfo=UTC),
    )
    # outbox worker 계약: admin target으로 가려면 audience=admin + text 필요.
    assert payload["audience"] == "admin"
    assert payload["kind"] == OUTBOX_CATEGORY
    assert payload["job_name"] == "pinvi_pii_retention_job"
    assert payload["run_id"] == "run-123"
    assert payload["error_class"] == "ValueError"
    assert payload["occurred_at"] == "2026-06-29T00:00:00+00:00"
    # text도 operational identifier만 담는다(예외 클래스/job/run).
    assert "ValueError" in payload["text"]
    assert "pinvi_pii_retention_job" in payload["text"]
    # run 식별자 + 예외 클래스 + worker 라우팅 키만 — message/stack/email 등 미포함.
    assert set(payload) == {
        "audience",
        "text",
        "kind",
        "job_name",
        "run_id",
        "error_class",
        "occurred_at",
    }


def test_payload_defaults_unknown_error_class() -> None:
    payload = build_run_failure_payload(
        job_name="j",
        run_id="r",
        error_class=None,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert payload["error_class"] == "UnknownError"


def test_payload_truncates_long_error_class() -> None:
    payload = build_run_failure_payload(
        job_name="j",
        run_id="r",
        error_class="X" * 500,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert len(payload["error_class"]) == 200


def test_payload_normalizes_occurred_at_to_utc() -> None:
    from datetime import timedelta, timezone

    kst = timezone(timedelta(hours=9))
    payload = build_run_failure_payload(
        job_name="j",
        run_id="r",
        error_class="RuntimeError",
        occurred_at=datetime(2026, 6, 29, 9, 0, tzinfo=kst),
    )
    assert payload["occurred_at"] == "2026-06-29T00:00:00+00:00"

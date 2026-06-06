"""Security incident schema integration test."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.models.security import SecurityIncident

pytestmark = pytest.mark.asyncio


async def test_security_incident_model_round_trip(session_factory, verified_user) -> None:
    cpo_user_id, _ = verified_user
    request_id = uuid.uuid4()

    async with session_factory() as db:
        incident = SecurityIncident(
            incident_type="admin_export_anomaly",
            severity="high",
            source="admin_audit_log",
            summary="1시간 내 개인정보 export 임계치 초과",
            details={"exported_rows": 1200, "window_minutes": 60},
            affected_user_count=1200,
            notification_required=True,
            assigned_cpo_user_id=uuid.UUID(cpo_user_id),
            request_id=request_id,
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        saved = await db.scalar(
            select(SecurityIncident).where(SecurityIncident.incident_id == incident.incident_id)
        )
        assert saved is not None
        assert saved.status == "open"
        assert saved.details["exported_rows"] == 1200
        assert saved.notification_required is True
        assert saved.assigned_cpo_user_id == uuid.UUID(cpo_user_id)
        assert saved.request_id == request_id


async def test_security_incidents_table_has_status_index(session_factory) -> None:
    async with session_factory() as db:
        result = await db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'app' AND tablename = 'security_incidents'"
            )
        )
        indexes = {row[0] for row in result}

    assert "ix_security_incidents_status_detected_at" in indexes
    assert "ix_security_incidents_severity_detected_at" in indexes

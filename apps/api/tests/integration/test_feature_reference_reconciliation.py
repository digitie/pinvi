"""T-VN-M05 local evidence/projection은 실제 PostgreSQL trigger에서 검증한다."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationLease,
    FeatureReferenceReconciliationServiceClient,
)
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationImportReceipt,
    KtmCurationImportReceiptItem,
)
from app.models.feature_reference_reconciliation import (
    KtmFeatureReferenceReconciliationAppliedReceipt,
    KtmFeatureReferenceReconciliationDeliveryAttempt,
    KtmFeatureReferenceReconciliationImpact,
)
from app.models.feature_suggestion import FeatureSuggestion
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.services.feature_reference_reconciliation import (
    FeatureReferenceReconciliationApplyError,
    ReconciliationApplied,
    ReconciliationBlocked,
    apply_feature_reference_reconciliation_event,
)
from app.services.feature_reference_reconciliation_worker import (
    consume_feature_reference_reconciliation_once,
)


def _lease(
    *,
    event_id: uuid.UUID,
    event_sequence: int,
    event_sha256: str,
    old_feature_id: str,
    old_feature_uuid: uuid.UUID,
    action: str = "rebind",
    replacement_feature_id: str | None = "feature-new",
    replacement_feature_uuid: uuid.UUID | None = None,
) -> FeatureReferenceReconciliationLease:
    replacement_uuid = replacement_feature_uuid or uuid.uuid4()
    return FeatureReferenceReconciliationLease.model_validate(
        {
            "outcome": "leased",
            "lease_epoch": 1,
            "lease_expires_at": "2026-08-21T00:01:00Z",
            "event_sha256": event_sha256,
            "event": {
                "payload_schema_version": 1,
                "event_id": str(event_id),
                "event_sequence": event_sequence,
                "occurred_at": "2026-08-21T00:00:00Z",
                "case_id": str(uuid.uuid4()),
                "resolution_id": str(uuid.uuid4()),
                "action": action,
                "old_feature": {
                    "feature_id": old_feature_id,
                    "feature_uuid": str(old_feature_uuid),
                    "row_revision": 2,
                },
                "replacement_feature": (
                    {
                        "feature_id": replacement_feature_id,
                        "feature_uuid": str(replacement_uuid),
                        "row_revision": 3,
                    }
                    if action == "rebind"
                    else None
                ),
                "manual_retire_transition_id": 1,
                "manual_retire_row_revision_after_transition": 2,
                "command_id": 1,
            },
        }
    )


async def _seed_rows(
    db: AsyncSession,
    *,
    old_feature_id: str,
    old_feature_uuid: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = User(
        email=f"m05-{uuid.uuid4().hex}@pinvi.test",
        password_hash=None,
        nickname="M05",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()
    trip = Trip(
        owner_user_id=user.user_id,
        title="M05 여행",
        start_date=date(2026, 8, 21),
        end_date=date(2026, 8, 21),
    )
    db.add(trip)
    await db.flush()
    db.add(TripDay(trip_id=trip.trip_id, day_index=1))
    await db.flush()
    trip_poi = TripDayPoi(
        trip_id=trip.trip_id,
        day_index=1,
        sort_order="a0",
        feature_id=old_feature_id,
        feature_uuid=old_feature_uuid,
        feature_snapshot={"name": "old"},
        added_by_user_id=user.user_id,
    )
    plan = CuratedTripPlan(
        slug=f"m05-{uuid.uuid4().hex}",
        title="M05 추천",
        created_by_admin_id=user.user_id,
        updated_by_admin_id=user.user_id,
    )
    db.add_all((trip_poi, plan))
    await db.flush()
    curated_poi = CuratedPlanPoi(
        curated_plan_id=plan.curated_plan_id,
        day_index=1,
        sort_order="a0",
        feature_id=old_feature_id,
        feature_uuid=old_feature_uuid,
    )
    terminal_suggestion = FeatureSuggestion(
        requester_user_id=user.user_id,
        suggestion_type="correction",
        target_feature_id=old_feature_id,
        target_feature_uuid=old_feature_uuid,
        kind="place",
        name="이미 끝난 제안",
        lng=Decimal("127.000000"),
        lat=Decimal("37.000000"),
        categories=[],
        status="duplicate",
    )
    db.add_all((curated_poi, terminal_suggestion))
    await db.flush()
    return trip_poi.attachment_id, curated_poi.curated_poi_id, terminal_suggestion.request_id


@pytest.mark.asyncio
async def test_rebind_commits_final_receipt_before_ack_material_and_replays_locally(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_uuid = uuid.uuid4()
    replacement_uuid = uuid.uuid4()
    event_id = uuid.uuid4()
    lease = _lease(
        event_id=event_id,
        event_sequence=1,
        event_sha256="a" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_uuid,
        replacement_feature_uuid=replacement_uuid,
    )
    async with session_factory() as db:
        trip_poi_id, curated_poi_id, terminal_suggestion_id = await _seed_rows(
            db, old_feature_id="feature-old", old_feature_uuid=old_uuid
        )
        applied = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(applied, ReconciliationApplied)
        assert applied.replayed_local_receipt is False
        await db.commit()

    async with session_factory() as db:
        trip = await db.get(TripDayPoi, trip_poi_id)
        curated = await db.get(CuratedPlanPoi, curated_poi_id)
        terminal = await db.get(FeatureSuggestion, terminal_suggestion_id)
        receipt = await db.get(KtmFeatureReferenceReconciliationAppliedReceipt, event_id)
        attempts = list(
            (
                await db.scalars(
                    select(KtmFeatureReferenceReconciliationDeliveryAttempt).where(
                        KtmFeatureReferenceReconciliationDeliveryAttempt.event_id == event_id
                    )
                )
            ).all()
        )
        impacts = list(
            (
                await db.scalars(
                    select(KtmFeatureReferenceReconciliationImpact).where(
                        KtmFeatureReferenceReconciliationImpact.event_id == event_id
                    )
                )
            ).all()
        )
        assert (
            trip is not None
            and curated is not None
            and terminal is not None
            and receipt is not None
        )
        assert (trip.feature_id, trip.feature_uuid) == ("feature-new", replacement_uuid)
        assert (curated.feature_id, curated.feature_uuid) == ("feature-new", replacement_uuid)
        assert (terminal.target_feature_id, terminal.target_feature_uuid) == (
            "feature-old",
            old_uuid,
        )
        assert receipt.receipt_sha256 == applied.local_receipt_sha256
        assert [(attempt.status, attempt.attempt_sequence) for attempt in attempts] == [
            ("applied", 1)
        ]
        assert [(impact.target_relation, impact.outcome) for impact in impacts] == [
            ("curated_plan_pois", "rebind"),
            ("trip_day_pois", "rebind"),
        ]

    async with session_factory() as db:
        replay = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(replay, ReconciliationApplied)
        assert replay.replayed_local_receipt is True
        assert replay.local_receipt_sha256 == applied.local_receipt_sha256
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(FeatureReferenceReconciliationApplyError):
            await apply_feature_reference_reconciliation_event(
                db,
                lease.model_copy(update={"event_sha256": "b" * 64}),
            )
        await db.rollback()


async def _create_admin(session_factory: Any) -> uuid.UUID:
    async with session_factory() as db:
        admin = User(
            email=f"m05-admin-{uuid.uuid4().hex}@pinvi.test",
            password_hash="x",
            nickname="M05 운영자",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        return admin.user_id


@pytest.mark.asyncio
async def test_admin_evidence_api_lists_blocked_and_applied_local_receipts(
    client: Any, session_factory: async_sessionmaker[AsyncSession], auth_cookies: Any
) -> None:
    admin_id = await _create_admin(session_factory)
    applied_event_id = uuid.uuid4()
    blocked_event_id = uuid.uuid4()
    second_blocked_event_id = uuid.uuid4()
    old_feature_uuid = uuid.uuid4()
    replacement_uuid = uuid.uuid4()
    async with session_factory() as db:
        receipt = KtmFeatureReferenceReconciliationAppliedReceipt(
            event_id=applied_event_id,
            event_sequence=10,
            event_sha256="a" * 64,
            action="rebind",
            old_feature_id="feature-old",
            old_feature_uuid=old_feature_uuid,
            replacement_feature_id="feature-new",
            replacement_feature_uuid=replacement_uuid,
            impact_root_sha256="b" * 64,
            impact_count=1,
            receipt_sha256="c" * 64,
        )
        db.add_all(
            (
                receipt,
                KtmFeatureReferenceReconciliationDeliveryAttempt(
                    event_id=applied_event_id,
                    attempt_sequence=1,
                    event_sequence=10,
                    event_sha256="a" * 64,
                    status="applied",
                    block_fingerprint_sha256=None,
                    observation_root_sha256="d" * 64,
                ),
                KtmFeatureReferenceReconciliationImpact(
                    event_id=applied_event_id,
                    impact_index=0,
                    target_relation="trip_day_pois",
                    target_id=uuid.uuid4(),
                    old_feature_id="feature-old",
                    old_feature_uuid=old_feature_uuid,
                    replacement_feature_id="feature-new",
                    replacement_feature_uuid=replacement_uuid,
                    outcome="rebind",
                ),
                KtmFeatureReferenceReconciliationDeliveryAttempt(
                    event_id=blocked_event_id,
                    attempt_sequence=1,
                    event_sequence=11,
                    event_sha256="e" * 64,
                    status="blocked",
                    block_fingerprint_sha256="f" * 64,
                    observation_root_sha256="0" * 64,
                ),
                KtmFeatureReferenceReconciliationDeliveryAttempt(
                    event_id=second_blocked_event_id,
                    attempt_sequence=1,
                    event_sequence=12,
                    event_sha256="1" * 64,
                    status="blocked",
                    block_fingerprint_sha256="2" * 64,
                    observation_root_sha256="3" * 64,
                ),
            )
        )
        await db.commit()

    response = await client.get(
        "/admin/feature-reference-reconciliations?status=all",
        cookies=auth_cookies(str(admin_id)),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert {item["event_id"] for item in items} == {
        str(applied_event_id),
        str(blocked_event_id),
        str(second_blocked_event_id),
    }
    applied = next(item for item in items if item["event_id"] == str(applied_event_id))
    assert applied["status"] == "applied"
    assert applied["receipt"]["receipt_sha256"] == "c" * 64
    blocked = next(item for item in items if item["event_id"] == str(blocked_event_id))
    assert blocked["status"] == "blocked"
    assert blocked["receipt"] is None

    blocked_page = await client.get(
        "/admin/feature-reference-reconciliations?status=blocked&page=1&limit=1",
        cookies=auth_cookies(str(admin_id)),
    )
    assert blocked_page.status_code == 200, blocked_page.text
    blocked_data = blocked_page.json()["data"]
    assert blocked_data["total"] == 2
    assert blocked_data["page"] == 1
    assert blocked_data["limit"] == 1
    assert len(blocked_data["items"]) == 1
    assert blocked_data["items"][0]["status"] == "blocked"
    assert blocked_data["items"][0]["receipt"] is None

    detail = await client.get(
        f"/admin/feature-reference-reconciliations/{applied_event_id}",
        cookies=auth_cookies(str(admin_id)),
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()["data"]
    assert payload["status"] == "applied"
    assert payload["receipt"]["action"] == "rebind"
    assert [(impact["target_relation"], impact["outcome"]) for impact in payload["impacts"]] == [
        ("trip_day_pois", "rebind")
    ]


@pytest.mark.asyncio
async def test_worker_calls_ack_only_after_final_receipt_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_uuid = uuid.uuid4()
    replacement_uuid = uuid.uuid4()
    lease = _lease(
        event_id=uuid.uuid4(),
        event_sequence=3,
        event_sha256="d" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_uuid,
        replacement_feature_uuid=replacement_uuid,
    )
    worker = uuid.uuid4()

    class _ReadClient:
        async def lease(self, *, worker_id: uuid.UUID) -> FeatureReferenceReconciliationLease:
            assert worker_id == worker
            return lease

    class _AckClient:
        called = False

        async def acknowledge(self, **kwargs: object) -> None:
            self.called = True
            assert kwargs["event_id"] == lease.event.event_id
            async with session_factory() as verification_db:
                receipt = await verification_db.get(
                    KtmFeatureReferenceReconciliationAppliedReceipt,
                    lease.event.event_id,
                )
                assert receipt is not None
                assert kwargs["local_receipt_sha256"] == receipt.receipt_sha256

    ack = _AckClient()
    async with session_factory() as db:
        await _seed_rows(db, old_feature_id="feature-old", old_feature_uuid=old_uuid)
        await db.commit()
    result = await consume_feature_reference_reconciliation_once(
        session_factory,
        read_client=cast(FeatureReferenceReconciliationServiceClient, _ReadClient()),
        ack_client=cast(FeatureReferenceReconciliationServiceClient, ack),
        worker_id=worker,
    )
    assert isinstance(result, ReconciliationApplied)
    assert ack.called is True


@pytest.mark.asyncio
async def test_partial_pair_blocks_without_mutation_and_evidence_is_append_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_uuid = uuid.uuid4()
    partial_id: uuid.UUID
    async with session_factory() as db:
        user = User(
            email=f"m05-{uuid.uuid4().hex}@pinvi.test",
            password_hash=None,
            nickname="M05",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        trip = Trip(owner_user_id=user.user_id, title="M05 partial")
        db.add(trip)
        await db.flush()
        db.add(TripDay(trip_id=trip.trip_id, day_index=1))
        await db.flush()
        partial = TripDayPoi(
            trip_id=trip.trip_id,
            day_index=1,
            sort_order="a0",
            feature_id="feature-old",
            feature_uuid=uuid.uuid4(),
            feature_snapshot={},
            added_by_user_id=user.user_id,
        )
        db.add(partial)
        await db.flush()
        partial_id = partial.attachment_id
        lease = _lease(
            event_id=uuid.uuid4(),
            event_sequence=2,
            event_sha256="c" * 64,
            old_feature_id="feature-old",
            old_feature_uuid=old_uuid,
            action="detach",
            replacement_feature_id=None,
        )
        blocked = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(blocked, ReconciliationBlocked)
        await db.commit()

    # 영구 blocker는 worker recheck마다 새 row를 만들지 않는다.
    async with session_factory() as db:
        repeated = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(repeated, ReconciliationBlocked)
        assert repeated.attempt_sequence == 1
        await db.commit()

    # blocker를 해소하면 다음 관측은 terminal receipt와 applied attempt로 전이한다.
    async with session_factory() as db:
        partial = await db.get(TripDayPoi, partial_id)
        assert partial is not None
        partial.feature_uuid = old_uuid
        await db.commit()

    async with session_factory() as db:
        applied = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(applied, ReconciliationApplied)
        await db.commit()

    async with session_factory() as db:
        attempts = list(
            (
                await db.scalars(
                    select(KtmFeatureReferenceReconciliationDeliveryAttempt)
                    .where(
                        KtmFeatureReferenceReconciliationDeliveryAttempt.event_id
                        == lease.event.event_id
                    )
                    .order_by(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence)
                )
            ).all()
        )
        assert [(attempt.attempt_sequence, attempt.status) for attempt in attempts] == [
            (1, "blocked"),
            (2, "applied"),
        ]
        assert attempts[0].block_fingerprint_sha256 is not None
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "UPDATE app.ktm_feature_reference_reconciliation_delivery_attempts "
                    "SET status = 'applied' WHERE event_id = :event_id"
                ),
                {"event_id": lease.event.event_id},
            )
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
async def test_append_only_evidence_trigger_fires_in_replica_mode(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """M05 evidence는 session_replication_role로 우회할 수 없다."""

    old_uuid = uuid.uuid4()
    event_id = uuid.uuid4()
    lease = _lease(
        event_id=event_id,
        event_sequence=29,
        event_sha256="f" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_uuid,
    )
    async with session_factory() as db:
        await _seed_rows(db, old_feature_id="feature-old", old_feature_uuid=old_uuid)
        result = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(result, ReconciliationApplied)
        await db.commit()

    statements = (
        "UPDATE app.ktm_feature_reference_reconciliation_delivery_attempts "
        "SET status = status WHERE event_id = :event_id",
        "DELETE FROM app.ktm_feature_reference_reconciliation_delivery_attempts "
        "WHERE event_id = :event_id",
        "TRUNCATE app.ktm_feature_reference_reconciliation_delivery_attempts",
        "UPDATE app.ktm_feature_reference_reconciliation_applied_receipts "
        "SET action = action WHERE event_id = :event_id",
        "DELETE FROM app.ktm_feature_reference_reconciliation_applied_receipts "
        "WHERE event_id = :event_id",
        "TRUNCATE app.ktm_feature_reference_reconciliation_applied_receipts",
        "UPDATE app.ktm_feature_reference_reconciliation_impacts "
        "SET outcome = outcome WHERE event_id = :event_id",
        "DELETE FROM app.ktm_feature_reference_reconciliation_impacts WHERE event_id = :event_id",
        "TRUNCATE app.ktm_feature_reference_reconciliation_impacts",
    )
    for statement in statements:
        async with session_factory() as db:
            await db.execute(text("SET LOCAL session_replication_role = replica"))
            with pytest.raises(DBAPIError):
                await db.execute(text(statement), {"event_id": event_id})
            await db.rollback()


@pytest.mark.asyncio
async def test_non_owner_runtime_login_cannot_disable_or_bypass_m05_evidence_guard(
    _database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """서비스 runtime DB login은 owner privilege 없이 정상 DML만 받는다."""

    event_id = uuid.uuid4()
    old_uuid = uuid.uuid4()
    lease = _lease(
        event_id=event_id,
        event_sequence=30,
        event_sha256="e" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_uuid,
    )
    role = f"pinvi_m05_runtime_{uuid.uuid4().hex[:12]}"
    password = f"m05-{uuid.uuid4().hex}"
    async with session_factory() as db:
        await _seed_rows(db, old_feature_id="feature-old", old_feature_uuid=old_uuid)
        result = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(result, ReconciliationApplied)
        await db.execute(
            text(
                f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOREPLICATION NOINHERIT PASSWORD '{password}'"
            )
        )
        await db.execute(text(f"GRANT USAGE ON SCHEMA app TO {role}"))
        await db.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {role}")
        )
        await db.execute(text(f"GRANT USAGE ON SCHEMA x_extension TO {role}"))
        await db.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO {role}"))
        await db.commit()

    runtime_url = make_url(_database_url).set(username=role, password=password)
    runtime_engine = create_async_engine(
        runtime_url.render_as_string(hide_password=False),
        poolclass=NullPool,
        future=True,
    )
    guarded_statements = (
        "SET LOCAL session_replication_role = replica",
        "ALTER TABLE app.ktm_feature_reference_reconciliation_delivery_attempts DISABLE TRIGGER USER",
        "DROP SCHEMA app CASCADE",
        "SET ROLE pinvi",
        f"CREATE TABLE x_extension.m05_runtime_{event_id.hex[:12]} (id integer)",
        "UPDATE app.ktm_feature_reference_reconciliation_delivery_attempts "
        "SET status = status WHERE event_id = :event_id",
    )
    try:
        async with runtime_engine.connect() as connection:
            values = await connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolcreaterole, rolcreatedb "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
            assert values.one() == (role, False, False, False)
            runtime_has_membership = await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_auth_members m "
                    "WHERE m.member = current_user::regrole)"
                )
            )
            assert runtime_has_membership is False
            assert (
                await connection.scalar(
                    text("SELECT has_schema_privilege(current_user, 'x_extension', 'USAGE')")
                )
            ) is True
            assert (
                await connection.scalar(
                    text("SELECT has_schema_privilege(current_user, 'x_extension', 'CREATE')")
                )
            ) is False
            x_extension_owner_or_member = await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname = "
                    "'x_extension' AND (n.nspowner = current_user::regrole OR "
                    "pg_has_role(current_user, n.nspowner, 'member')))"
                )
            )
            assert x_extension_owner_or_member is False
            digest = await connection.scalar(
                text("SELECT encode(x_extension.digest('m05', 'sha256'), 'hex')")
            )
            assert isinstance(digest, str) and len(digest) == 64
        for statement in guarded_statements:
            async with runtime_engine.begin() as connection:
                with pytest.raises(DBAPIError):
                    await connection.execute(text(statement), {"event_id": event_id})
    finally:
        await runtime_engine.dispose()
        async with session_factory() as db:
            await db.execute(text(f"DROP OWNED BY {role}"))
            await db.execute(text(f"DROP ROLE {role}"))
            await db.commit()


@pytest.mark.asyncio
async def test_m05_fault_health_is_not_ready_and_does_not_reflect_map_error(
    client: Any,
) -> None:
    from app.core.config import settings
    from app.main import app

    enabled_before = settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled
    settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled = True
    app.state.feature_reference_reconciliation_runtime_fault = "map_pairing_fault"
    try:
        response = await client.get("/health/feature-reference-reconciliation")
    finally:
        app.state.feature_reference_reconciliation_runtime_fault = None
        settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled = enabled_before

    assert response.status_code == 503
    assert response.json() == {
        "enabled": True,
        "ready": False,
        "fault": "map_pairing_fault",
    }


@pytest.mark.asyncio
async def test_receipt_bound_curation_poi_blocks_without_feature_rebind(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_feature_uuid = uuid.uuid4()
    replacement_feature_uuid = uuid.uuid4()
    collection_id = uuid.uuid4()
    item_id = uuid.uuid4()
    etag = f'"sha256:{"a" * 64}"'
    async with session_factory() as db:
        user = User(
            email=f"m05-curation-{uuid.uuid4().hex}@pinvi.test",
            password_hash=None,
            nickname="M05 curation",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        plan = CuratedTripPlan(
            slug=f"m05-curation-{uuid.uuid4().hex}",
            title="M05 curation receipt",
            source_system="kor-travel-map",
            source_curation_collection_id=collection_id,
            source_curation_collection_revision=1,
            source_curation_collection_etag=etag,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash="b" * 64,
            source_curation_item_count=1,
            created_by_admin_id=user.user_id,
            updated_by_admin_id=user.user_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=user.user_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint="c" * 64,
            source_curation_collection_id=collection_id,
            source_curation_collection_revision=1,
            source_curation_collection_etag=etag,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash="b" * 64,
            source_curation_item_count=1,
            mode="refresh",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt.receipt_id,
                source_curation_collection_id=collection_id,
                source_curation_item_id=item_id,
                source_curation_item_revision=1,
                source_curation_item_etag=etag,
                feature_uuid=old_feature_uuid,
            )
        )
        # ORM relationship가 없는 composite FK라 flush 순서를 명시한다.
        await db.flush()
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=1,
                sort_order="a0",
                feature_id="feature-old",
                feature_uuid=old_feature_uuid,
                feature_snapshot={},
                source_curation_import_receipt_id=receipt.receipt_id,
                source_curation_collection_id=collection_id,
                source_curation_item_id=item_id,
                source_curation_item_revision=1,
                source_curation_item_etag=etag,
            )
        )
        await db.commit()

    lease = _lease(
        event_id=uuid.uuid4(),
        event_sequence=20,
        event_sha256="d" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_feature_uuid,
        replacement_feature_uuid=replacement_feature_uuid,
    )
    async with session_factory() as db:
        outcome = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(outcome, ReconciliationBlocked)
        await db.commit()

    async with session_factory() as db:
        poi = await db.scalar(
            select(CuratedPlanPoi).where(
                CuratedPlanPoi.source_curation_import_receipt_id == receipt.receipt_id
            )
        )
        attempt = await db.get(
            KtmFeatureReferenceReconciliationDeliveryAttempt,
            (lease.event.event_id, 1),
        )
        assert poi is not None
        assert (poi.feature_id, poi.feature_uuid) == ("feature-old", old_feature_uuid)
        assert attempt is not None
        assert attempt.status == "blocked"


@pytest.mark.asyncio
async def test_nonterminal_feature_suggestion_blocks_without_target_mutation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_feature_uuid = uuid.uuid4()
    async with session_factory() as db:
        user = User(
            email=f"m05-suggestion-{uuid.uuid4().hex}@pinvi.test",
            password_hash=None,
            nickname="M05 suggestion",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        suggestion = FeatureSuggestion(
            requester_user_id=user.user_id,
            suggestion_type="correction",
            target_feature_id="feature-old",
            target_feature_uuid=old_feature_uuid,
            kind="place",
            name="아직 검토 중",
            lng=Decimal("127.000000"),
            lat=Decimal("37.000000"),
            categories=[],
            status="pending",
        )
        db.add(suggestion)
        await db.commit()

    lease = _lease(
        event_id=uuid.uuid4(),
        event_sequence=21,
        event_sha256="e" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_feature_uuid,
        action="detach",
        replacement_feature_id=None,
    )
    async with session_factory() as db:
        outcome = await apply_feature_reference_reconciliation_event(db, lease)
        assert isinstance(outcome, ReconciliationBlocked)
        await db.commit()

    async with session_factory() as db:
        stored = await db.get(FeatureSuggestion, suggestion.request_id)
        assert stored is not None
        assert (stored.target_feature_id, stored.target_feature_uuid) == (
            "feature-old",
            old_feature_uuid,
        )


@pytest.mark.asyncio
async def test_concurrent_consumer_delivery_uses_one_receipt_and_one_applied_attempt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_feature_uuid = uuid.uuid4()
    lease = _lease(
        event_id=uuid.uuid4(),
        event_sequence=22,
        event_sha256="f" * 64,
        old_feature_id="feature-old",
        old_feature_uuid=old_feature_uuid,
    )
    async with session_factory() as db:
        await _seed_rows(db, old_feature_id="feature-old", old_feature_uuid=old_feature_uuid)
        await db.commit()

    async def apply_once() -> ReconciliationApplied | ReconciliationBlocked:
        async with session_factory() as db:
            outcome = await apply_feature_reference_reconciliation_event(db, lease)
            await db.commit()
            return outcome

    first, second = await asyncio.gather(apply_once(), apply_once())
    assert isinstance(first, ReconciliationApplied)
    assert isinstance(second, ReconciliationApplied)
    assert {first.replayed_local_receipt, second.replayed_local_receipt} == {False, True}

    async with session_factory() as db:
        attempts = list(
            (
                await db.scalars(
                    select(KtmFeatureReferenceReconciliationDeliveryAttempt)
                    .where(
                        KtmFeatureReferenceReconciliationDeliveryAttempt.event_id
                        == lease.event.event_id
                    )
                    .order_by(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence)
                )
            ).all()
        )
        assert [(attempt.status, attempt.attempt_sequence) for attempt in attempts] == [
            ("applied", 1)
        ]

"""ADR-058 cache target sync DDL과 canonical POI 좌표 계약."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
)
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _seed_poi(session_factory, *, snapshot: dict[str, object]) -> TripDayPoi:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        user = User(email=f"cache-target-{uuid.uuid4()}@pinvi.test", status="active")
        db.add(user)
        await db.flush()
        trip = Trip(owner_user_id=user.user_id, title="cache target schema")
        db.add(trip)
        await db.flush()
        db.add(TripDay(trip_id=trip.trip_id, day_index=1))
        await db.flush()
        poi = TripDayPoi(
            trip_id=trip.trip_id,
            day_index=1,
            sort_order="a0",
            feature_snapshot=snapshot,
            added_by_user_id=user.user_id,
        )
        db.add(poi)
        await db.commit()
        await db.refresh(poi)
        return poi


async def test_generated_cache_target_coord_accepts_both_canonical_shapes(session_factory) -> None:  # type: ignore[no-untyped-def]
    nested = await _seed_poi(
        session_factory,
        snapshot={"coord": {"lon": 129.1234567, "lat": 35.1234567}},
    )
    top_level = await _seed_poi(
        session_factory,
        snapshot={"lon": 126.9876543, "lat": 37.1234567},
    )

    assert nested.cache_target_lon == Decimal("129.1234567")
    assert nested.cache_target_lat == Decimal("35.1234567")
    assert top_level.cache_target_lon == Decimal("126.9876543")
    assert top_level.cache_target_lat == Decimal("37.1234567")
    assert nested.cache_target_radius_km == Decimal("5.000")
    assert nested.cache_target_update_enabled is True


async def test_generated_cache_target_coord_fails_hard_on_partial_pair(session_factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(IntegrityError, match="ck_trip_day_pois_cache_coord_pair"):
        await _seed_poi(session_factory, snapshot={"coord": {"lon": 129.1}})


async def test_generated_cache_target_coord_fails_hard_outside_map_bounds(session_factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(IntegrityError, match="ck_trip_day_pois_cache_lon_korea"):
        await _seed_poi(
            session_factory,
            snapshot={"coord": {"lon": 140.0, "lat": 35.0}},
        )


async def test_generated_cache_target_coord_fails_hard_on_conflicting_shapes(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(IntegrityError, match="ck_tdp_cache_lon_consistent"):
        await _seed_poi(
            session_factory,
            snapshot={
                "coord": {"lon": 129.1, "lat": 35.1},
                "lon": 128.1,
                "lat": 35.1,
            },
        )


async def test_cache_target_tombstone_can_outlive_hard_deleted_poi(session_factory) -> None:  # type: ignore[no-untyped-def]
    poi = await _seed_poi(
        session_factory,
        snapshot={"coord": {"lon": 129.1, "lat": 35.1}},
    )
    async with session_factory() as db:
        head = KtmCacheTargetHead(
            poi_id=poi.attachment_id,
            external_system="pinvi",
            target_key=str(poi.attachment_id).lower(),
            desired_state="deleted",
            source_generation=2,
            source_payload_fingerprint=b"d" * 32,
            lon=poi.cache_target_lon,
            lat=poi.cache_target_lat,
            radius_km=poi.cache_target_radius_km,
            update_enabled=False,
        )
        db.add(head)
        await db.flush()
        persisted_poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.attachment_id == poi.attachment_id)
        )
        assert persisted_poi is not None
        await db.delete(persisted_poi)
        await db.commit()

    async with session_factory() as db:
        retained_head = await db.get(KtmCacheTargetHead, poi.attachment_id)
        assert retained_head is not None
        assert retained_head.desired_state == "deleted"


async def test_reclaim_keeps_one_immutable_event_and_distinct_claim_receipts(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    event_id = uuid.uuid4()
    first_claim_id = uuid.uuid4()
    second_claim_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
            )
        )
        db.add(
            KtmCacheTargetEvent(
                event_id=event_id,
                event_type="cache_target.state_applied",
                external_system="pinvi",
                target_key=str(uuid.uuid4()),
                restore_epoch=1,
                source_generation=1,
                target_sequence=1,
                relay_order=1,
                source_payload_fingerprint=b"s" * 32,
                occurred_at=now,
                payload={"status": "applied"},
            )
        )
        db.add_all(
            [
                KtmCacheTargetEventClaim(
                    claim_id=first_claim_id,
                    consumer_id="pinvi-cache-target-consumer",
                    lease_token=uuid.uuid4(),
                    lease_expires_at=now,
                    status="expired",
                    completed_at=now,
                ),
                KtmCacheTargetEventClaim(
                    claim_id=second_claim_id,
                    consumer_id="pinvi-cache-target-consumer",
                    lease_token=uuid.uuid4(),
                    lease_expires_at=now,
                    status="active",
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                KtmCacheTargetEventClaimItem(
                    claim_id=first_claim_id,
                    event_id=event_id,
                    position=1,
                    delivery_cursor="cursor-1",
                    payload_fingerprint=b"p" * 32,
                ),
                KtmCacheTargetEventClaimItem(
                    claim_id=second_claim_id,
                    event_id=event_id,
                    position=1,
                    delivery_cursor="cursor-1",
                    payload_fingerprint=b"p" * 32,
                ),
            ]
        )
        await db.commit()

    async with session_factory() as db:
        inbox_event = await db.get(KtmCacheTargetEvent, event_id)
        receipts = (
            await db.scalars(
                select(KtmCacheTargetEventClaimItem).where(
                    KtmCacheTargetEventClaimItem.event_id == event_id
                )
            )
        ).all()
        assert inbox_event is not None
        assert len(receipts) == 2

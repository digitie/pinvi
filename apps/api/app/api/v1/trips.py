"""`/trips/*` — `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.deps import CurrentUserId, DbSession
from app.schemas.envelope import Envelope
from app.schemas.share_link import ShareLinkCreate, ShareLinkResponse
from app.schemas.trip import TripCreate, TripResponse, TripUpdate
from app.services.trip import (
    TripNotFoundError,
    TripPermissionError,
    TripVersionConflictError,
    create_trip,
    get_trip_for_user,
    invite_companion,
    issue_share_link,
    list_trips_for_owner,
    revoke_share_link,
    update_trip,
)

router = APIRouter(prefix="/trips", tags=["trips"])


def _to_response(trip) -> TripResponse:  # type: ignore[no-untyped-def]
    return TripResponse(
        trip_id=trip.trip_id,
        owner_user_id=trip.owner_user_id,
        title=trip.title,
        description=trip.description,
        region_hint=trip.region_hint,
        start_date=trip.start_date,
        end_date=trip.end_date,
        visibility=trip.visibility,
        status=trip.status,
        version=trip.version,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


@router.get("", response_model=Envelope[list[TripResponse]])
async def list_trips(
    current_user_id: CurrentUserId,
    db: DbSession,
    limit: int = 20,
) -> Envelope[list[TripResponse]]:
    trips = await list_trips_for_owner(db, user_id=uuid.UUID(current_user_id), limit=limit)
    return Envelope.of([_to_response(t) for t in trips])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripResponse],
)
async def create_trip_endpoint(
    body: TripCreate, current_user_id: CurrentUserId, db: DbSession
) -> Envelope[TripResponse]:
    trip = await create_trip(
        db,
        owner_user_id=uuid.UUID(current_user_id),
        title=body.title,
        description=body.description,
        region_hint=body.region_hint,
        start_date=body.start_date,
        end_date=body.end_date,
        visibility=body.visibility,
    )
    for companion in body.companions:
        await invite_companion(
            db,
            trip_id=trip.trip_id,
            email=str(companion.email),
            user_id=None,
            display_name=companion.display_name,
            role=companion.role,
        )
    return Envelope.of(_to_response(trip))


@router.get("/{trip_id}", response_model=Envelope[TripResponse])
async def get_trip_endpoint(
    trip_id: uuid.UUID, current_user_id: CurrentUserId, db: DbSession
) -> Envelope[TripResponse]:
    try:
        trip = await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except TripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_response(trip))


@router.patch("/{trip_id}", response_model=Envelope[TripResponse])
async def update_trip_endpoint(
    trip_id: uuid.UUID,
    body: TripUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
    if_match: Annotated[int, Header(alias="If-Match")],
) -> Envelope[TripResponse]:
    try:
        trip = await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        trip = await update_trip(
            db,
            trip=trip,
            expected_version=if_match,
            patch=body.model_dump(exclude_unset=True),
        )
    except TripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_response(trip))


@router.post(
    "/{trip_id}/share-tokens",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ShareLinkResponse],
)
async def create_share_token(
    trip_id: uuid.UUID,
    body: ShareLinkCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[ShareLinkResponse]:
    trip = await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    share, raw = await issue_share_link(
        db,
        trip_id=trip.trip_id,
        created_by_user_id=uuid.UUID(current_user_id),
        visibility=body.visibility,
        expires_at=body.expires_at,
    )
    url = f"https://app.tripmate.local/trips/{trip.trip_id}/shared/{raw}"
    return Envelope.of(
        ShareLinkResponse(
            share_id=share.share_id,
            trip_id=share.trip_id,
            visibility=share.visibility,  # type: ignore[arg-type]
            token=raw,
            url=url,
            expires_at=share.expires_at,
            revoked_at=share.revoked_at,
            last_used_at=share.last_used_at,
            created_at=share.created_at,
        )
    )


@router.delete(
    "/{trip_id}/share-tokens/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_share_token(
    trip_id: uuid.UUID,
    share_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    try:
        await revoke_share_link(db, share_id=share_id, trip_id=trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

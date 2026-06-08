"""`/trips/*` — `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.etl_bridge.krtour_map import OptionalKrtourMapClientDep
from app.schemas.envelope import Envelope
from app.schemas.share_link import ShareLinkCreate, ShareLinkResponse
from app.schemas.trip import (
    TripCommentCreate,
    TripCommentResponse,
    TripCompanionInvite,
    TripCompanionResponse,
    TripCreate,
    TripResponse,
    TripUpdate,
    TripView,
)
from app.services.realtime_broker import realtime_broker
from app.services.trip import (
    TripCommentNotFoundError,
    TripCompanionConflictError,
    TripNotFoundError,
    TripPermissionError,
    TripVersionConflictError,
    create_comment,
    create_trip,
    delete_comment,
    get_trip_for_user,
    get_trip_owned_by_user,
    invite_companion,
    issue_share_link,
    list_comments,
    list_trips_for_owner,
    remove_companion,
    revoke_share_link,
    update_trip,
)
from app.services.trip_view_builder import build_trip_view

router = APIRouter(prefix="/trips", tags=["trips"])


def _to_response(trip) -> TripResponse:  # type: ignore[no-untyped-def]
    return TripResponse(
        trip_id=trip.trip_id,
        owner_user_id=trip.owner_user_id,
        title=trip.title,
        description=trip.description,
        region_hint=trip.region_hint,
        primary_region_code=trip.primary_region_code,
        primary_region_source=trip.primary_region_source,
        start_date=trip.start_date,
        end_date=trip.end_date,
        visibility=trip.visibility,
        status=trip.status,
        version=trip.version,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


def _to_companion_response(companion) -> TripCompanionResponse:  # type: ignore[no-untyped-def]
    return TripCompanionResponse(
        companion_id=companion.companion_id,
        trip_id=companion.trip_id,
        user_id=companion.user_id,
        invited_email=companion.invited_email,
        invited_nickname=companion.invited_nickname,
        role=companion.role,
        invited_at=companion.invited_at,
        joined_at=companion.joined_at,
        created_at=companion.created_at,
        updated_at=companion.updated_at,
    )


def _to_comment_response(comment) -> TripCommentResponse:  # type: ignore[no-untyped-def]
    return TripCommentResponse(
        comment_id=comment.comment_id,
        trip_id=comment.trip_id,
        author_user_id=comment.author_user_id,
        body=comment.body,
        target_type=comment.target_type,
        target_id=comment.target_id,
        day_index=comment.day_index,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def _raise_trip_http(exc: TripNotFoundError | TripPermissionError) -> NoReturn:
    if isinstance(exc, TripNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


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
        primary_region_code=body.primary_region_code,
        start_date=body.start_date,
        end_date=body.end_date,
        visibility=body.visibility,
    )
    for companion in body.companions:
        await invite_companion(
            db,
            trip=trip,
            invited_by_user_id=uuid.UUID(current_user_id),
            email=str(companion.email),
            display_name=companion.display_name,
            role=companion.role,
        )
    return Envelope.of(_to_response(trip))


@router.get("/{trip_id}", response_model=Envelope[TripView])
async def get_trip_endpoint(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    krtour_client: OptionalKrtourMapClientDep,
) -> Envelope[TripView]:
    try:
        trip = await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    return Envelope.of(
        TripView.model_validate(await build_trip_view(db, trip=trip, krtour_client=krtour_client))
    )


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
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    realtime_broker.publish_event_nowait(
        trip_id=trip.trip_id,
        event_type="trip.updated",
        actor_user_id=uuid.UUID(current_user_id),
        payload={
            "changes": body.model_dump(exclude_unset=True, mode="json"),
            "version": trip.version,
        },
        version=trip.version,
    )
    return Envelope.of(_to_response(trip))


@router.post(
    "/{trip_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripCompanionResponse],
)
async def invite_trip_member(
    trip_id: uuid.UUID,
    body: TripCompanionInvite,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripCompanionResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        trip = await get_trip_owned_by_user(db, trip_id=trip_id, user_id=actor_id)
        companion = await invite_companion(
            db,
            trip=trip,
            invited_by_user_id=actor_id,
            email=str(body.email),
            display_name=body.display_name,
            role=body.role,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripCompanionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = _to_companion_response(companion)
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="trip.member_changed",
        actor_user_id=actor_id,
        payload={"action": "added", "companion": response.model_dump(mode="json")},
    )
    return Envelope.of(response)


@router.delete(
    "/{trip_id}/members/{companion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_trip_member(
    trip_id: uuid.UUID,
    companion_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_owned_by_user(db, trip_id=trip_id, user_id=actor_id)
        await remove_companion(db, trip_id=trip_id, companion_id=companion_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="trip.member_changed",
        actor_user_id=actor_id,
        payload={"action": "removed", "companion_id": str(companion_id)},
    )


@router.get(
    "/{trip_id}/comments",
    response_model=Envelope[list[TripCommentResponse]],
)
async def list_trip_comments(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    limit: int = 50,
) -> Envelope[list[TripCommentResponse]]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    comments = await list_comments(db, trip_id=trip_id, limit=limit)
    return Envelope.of([_to_comment_response(comment) for comment in comments])


@router.post(
    "/{trip_id}/comments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripCommentResponse],
)
async def create_trip_comment(
    trip_id: uuid.UUID,
    body: TripCommentCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripCommentResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=actor_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    comment = await create_comment(
        db,
        trip_id=trip_id,
        author_user_id=actor_id,
        body=body.body,
        target_type=body.target_type,
        target_id=body.target_id,
        day_index=body.day_index,
    )
    response = _to_comment_response(comment)
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="comment.created",
        actor_user_id=actor_id,
        payload={"comment": response.model_dump(mode="json")},
    )
    return Envelope.of(response)


@router.delete(
    "/{trip_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_trip_comment(
    trip_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    actor_id = uuid.UUID(current_user_id)
    try:
        trip = await get_trip_for_user(db, trip_id=trip_id, user_id=actor_id)
        await delete_comment(db, trip=trip, comment_id=comment_id, actor_user_id=actor_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripCommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="comment.deleted",
        actor_user_id=actor_id,
        payload={"comment_id": str(comment_id)},
    )


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
    try:
        trip = await get_trip_owned_by_user(
            db,
            trip_id=trip_id,
            user_id=uuid.UUID(current_user_id),
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    share, raw = await issue_share_link(
        db,
        trip_id=trip.trip_id,
        created_by_user_id=uuid.UUID(current_user_id),
        visibility=body.visibility,
        expires_at=body.expires_at,
    )
    web_base_url = settings.tripmate_web_base_url.rstrip("/")
    url = f"{web_base_url}/trips/{trip.trip_id}/shared/{raw}"
    return Envelope.of(
        ShareLinkResponse(
            share_id=share.share_id,
            trip_id=share.trip_id,
            visibility=share.visibility,
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
    try:
        await get_trip_owned_by_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await revoke_share_link(db, share_id=share_id, trip_id=trip_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)

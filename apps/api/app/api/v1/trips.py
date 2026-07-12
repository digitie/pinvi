"""`/trips/*` — `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from datetime import date, datetime
from json import JSONDecodeError, dumps, loads
from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.api.request_url import public_api_base_url
from app.clients.kor_travel_map import OptionalKorTravelMapHttpClientDep
from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.models.attachment import CuratedPlanAttachment
from app.schemas.envelope import Envelope, EnvelopeMeta, EnvelopeWithMeta
from app.schemas.share_link import ShareLinkCreate, ShareLinkResponse
from app.schemas.storage import (
    AttachmentCreate,
    AttachmentLibraryItem,
    AttachmentLibraryPage,
    AttachmentUpdate,
    DownloadUrlResponse,
)
from app.schemas.trip import (
    TripAttachmentResponse,
    TripCommentCreate,
    TripCommentResponse,
    TripCompanionInvite,
    TripCompanionResponse,
    TripCopyRequest,
    TripCopyResponse,
    TripCreate,
    TripDayCreate,
    TripDayOptimizeRequest,
    TripDayOptimizeResponse,
    TripDayResponse,
    TripDayUpdate,
    TripDeleteRequest,
    TripDistanceMatrixResponse,
    TripResponse,
    TripSharedView,
    TripUpdate,
    TripView,
)
from app.services.poi import PoiNotFoundError, get_poi
from app.services.realtime_broker import realtime_broker
from app.services.rustfs_storage import make_download_url
from app.services.storage_policy import attachment_scope, list_admin_file_library
from app.services.telegram_messages import (
    build_companion_invited_message,
    build_trip_created_message,
)
from app.services.telegram_outbox import enqueue_user_notification
from app.services.trip import (
    TripAttachmentLimitError,
    TripAttachmentNotFoundError,
    TripAttachmentQuotaError,
    TripAttachmentStorageRefError,
    TripBucket,
    TripCommentNotFoundError,
    TripCompanionConflictError,
    TripCopyError,
    TripDayConflictError,
    TripDayNotFoundError,
    TripDayValidationError,
    TripListCursor,
    TripListSort,
    TripNotFoundError,
    TripOptimizeError,
    TripPermissionError,
    TripStatus,
    TripVersionConflictError,
    TripVisibility,
    build_distance_matrix,
    can_manage_trip,
    copy_trip,
    create_attachment,
    create_comment,
    create_trip,
    create_trip_day,
    default_trip_day_date,
    delete_attachment,
    delete_comment,
    delete_or_transfer_trip,
    delete_trip_day,
    get_attachment,
    get_trip_access,
    get_trip_day,
    get_trip_for_share_token,
    get_trip_for_user,
    get_trip_for_user_write,
    get_trip_owned_by_user,
    invite_companion,
    issue_share_link,
    list_attachments,
    list_comments,
    list_trips_for_owner,
    next_available_trip_day_index,
    optimize_trip_day,
    remove_companion,
    revoke_share_link,
    update_attachment,
    update_trip,
    update_trip_day,
    validate_trip_day_payload,
)
from app.services.trip_view_builder import build_trip_view

router = APIRouter(prefix="/trips", tags=["trips"])
_TRIP_CURSOR_VERSION = 2


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


def _to_day_response(day) -> TripDayResponse:  # type: ignore[no-untyped-def]
    return TripDayResponse(
        trip_id=day.trip_id,
        day_index=day.day_index,
        date=day.date,
        title=day.title,
        note=day.note,
        version=day.version,
        created_at=day.created_at,
        updated_at=day.updated_at,
    )


def _to_attachment_response(attachment) -> TripAttachmentResponse:  # type: ignore[no-untyped-def]
    return TripAttachmentResponse(
        attachment_id=attachment.attachment_id,
        trip_id=attachment.trip_id,
        trip_day_index=attachment.trip_day_index,
        trip_poi_id=attachment.trip_poi_id,
        curated_plan_id=attachment.curated_plan_id,
        curated_poi_id=attachment.curated_poi_id,
        notice_plan_id=attachment.notice_plan_id,
        notice_poi_id=attachment.notice_poi_id,
        source_attachment_id=attachment.source_attachment_id,
        bucket=attachment.bucket,
        storage_key=attachment.storage_key,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        public_url=attachment.public_url,
        role=attachment.role,
        description=attachment.description,
        sort_order=attachment.sort_order,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
    )


def _to_attachment_library_item(
    attachment: CuratedPlanAttachment,
    *,
    trip_title: str | None,
    poi_label: str | None,
) -> AttachmentLibraryItem:
    return AttachmentLibraryItem(
        attachment_id=attachment.attachment_id,
        trip_id=attachment.trip_id,
        trip_day_index=attachment.trip_day_index,
        trip_poi_id=attachment.trip_poi_id,
        curated_plan_id=attachment.curated_plan_id,
        curated_poi_id=attachment.curated_poi_id,
        notice_plan_id=attachment.notice_plan_id,
        notice_poi_id=attachment.notice_poi_id,
        source_attachment_id=attachment.source_attachment_id,
        bucket=attachment.bucket,
        storage_key=attachment.storage_key,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        public_url=attachment.public_url,
        role=attachment.role,
        description=attachment.description,
        sort_order=attachment.sort_order,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
        target_scope=attachment_scope(attachment),
        uploaded_by_user_id=attachment.uploaded_by_user_id,
        trip_title=trip_title,
        poi_label=poi_label,
    )


def _raise_attachment_limit(exc: TripAttachmentLimitError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_attachment_storage_ref(exc: TripAttachmentStorageRefError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_attachment_quota(exc: TripAttachmentQuotaError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


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


@router.get("", response_model=EnvelopeWithMeta[list[TripResponse]])
async def list_trips(
    current_user_id: CurrentUserId,
    db: DbSession,
    bucket: Annotated[TripBucket, Query()] = "future",
    q: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
    status_filter: Annotated[TripStatus | None, Query(alias="status")] = None,
    visibility_filter: Annotated[TripVisibility | None, Query(alias="visibility")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Annotated[TripListSort, Query()] = "-updated_at",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> EnvelopeWithMeta[list[TripResponse]]:
    if date_from is not None and date_to is not None and date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "date_to는 date_from 이후여야 합니다.",
            },
        )
    trip_cursor = _decode_trip_cursor(cursor)
    trips, has_more = await list_trips_for_owner(
        db,
        user_id=uuid.UUID(current_user_id),
        bucket=bucket,
        q=q,
        status_filter=status_filter,
        visibility_filter=visibility_filter,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        cursor=trip_cursor,
    )
    next_cursor: str | None = None
    if has_more and trips:
        last = trips[-1]
        if sort == "-updated_at":
            next_cursor = _encode_keyset_cursor(last.updated_at, last.trip_id)
        else:
            next_cursor = _encode_offset_cursor(trip_cursor.offset + limit)
    return EnvelopeWithMeta.of(
        [_to_response(t) for t in trips],
        meta=EnvelopeMeta(cursor=next_cursor, has_more=has_more, limit=limit),
    )


def _encode_offset_cursor(offset: int) -> str:
    raw = dumps({"v": _TRIP_CURSOR_VERSION, "off": offset}, separators=(",", ":")).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _encode_keyset_cursor(updated_at: datetime, trip_id: uuid.UUID) -> str:
    raw = dumps(
        {"v": _TRIP_CURSOR_VERSION, "ua": updated_at.isoformat(), "id": str(trip_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_trip_cursor(cursor: str | None) -> TripListCursor:
    if cursor is None:
        return TripListCursor()
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = loads(urlsafe_b64decode(f"{cursor}{padding}"))
    except (BinasciiError, JSONDecodeError, ValueError, TypeError) as exc:
        raise _invalid_trip_cursor() from exc
    if not isinstance(payload, dict) or payload.get("v") != _TRIP_CURSOR_VERSION:
        raise _invalid_trip_cursor()
    if "ua" in payload or "id" in payload:
        try:
            updated_at = datetime.fromisoformat(str(payload["ua"]))
            trip_id = uuid.UUID(str(payload["id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise _invalid_trip_cursor() from exc
        return TripListCursor(updated_at=updated_at, trip_id=trip_id)
    offset = payload.get("off")
    if not isinstance(offset, int) or offset < 0:
        raise _invalid_trip_cursor()
    return TripListCursor(offset=offset)


def _invalid_trip_cursor() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "VALIDATION_ERROR",
            "message": "cursor 형식이 올바르지 않습니다.",
        },
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripResponse],
)
async def create_trip_endpoint(
    body: TripCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripResponse]:
    owner_id = uuid.UUID(current_user_id)
    trip = await create_trip(
        db,
        owner_user_id=owner_id,
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
            invited_by_user_id=owner_id,
            email=str(companion.email),
            display_name=companion.display_name,
            role=companion.role,
        )
    # T-106 §8 — outbox에 적재만, 전송은 drain worker(재시도 포함).
    await enqueue_user_notification(
        db,
        category="trip_created",
        user_id=owner_id,
        text=build_trip_created_message(
            title=trip.title,
            start_date=trip.start_date,
            end_date=trip.end_date,
            region_hint=trip.region_hint,
        ),
    )
    await db.commit()
    return Envelope.of(_to_response(trip))


@router.get("/{trip_id}", response_model=Envelope[TripView])
async def get_trip_endpoint(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    kor_travel_map_client: OptionalKorTravelMapHttpClientDep,
) -> Envelope[TripView]:
    try:
        trip, role = await get_trip_access(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    return Envelope.of(
        TripView.model_validate(
            await build_trip_view(
                db,
                trip=trip,
                kor_travel_map_client=kor_travel_map_client,
                include_management=can_manage_trip(role),
            )
        )
    )


@router.get("/{trip_id}/files", response_model=Envelope[AttachmentLibraryPage])
async def list_trip_files_endpoint(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    page: int = 1,
    limit: int = 50,
) -> Envelope[AttachmentLibraryPage]:
    try:
        await get_trip_access(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    page = max(1, page)
    limit = min(100, max(1, limit))
    rows, total = await list_admin_file_library(
        db,
        q=None,
        scope=None,
        user_id=None,
        trip_id=trip_id,
        limit=limit,
        offset=(page - 1) * limit,
    )
    return Envelope.of(
        AttachmentLibraryPage(
            items=[
                _to_attachment_library_item(
                    attachment,
                    trip_title=trip_title,
                    poi_label=poi_label,
                )
                for attachment, trip_title, poi_label, _uploaded_by_email in rows
            ],
            total=total,
            page=page,
            limit=limit,
        )
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
        trip = await get_trip_for_user_write(
            db, trip_id=trip_id, user_id=uuid.UUID(current_user_id)
        )
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


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip_endpoint(
    trip_id: uuid.UUID,
    body: TripDeleteRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    actor_id = uuid.UUID(current_user_id)
    try:
        trip = await get_trip_owned_by_user(db, trip_id=trip_id, user_id=actor_id)
        updated = await delete_or_transfer_trip(
            db,
            trip=trip,
            actor_user_id=actor_id,
            mode=body.mode,
            new_owner_user_id=body.new_owner_user_id,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripCopyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="trip.updated",
        actor_user_id=actor_id,
        payload={"mode": body.mode, "version": updated.version},
        version=updated.version,
    )


@router.post(
    "/{trip_id}/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripCopyResponse],
)
async def copy_trip_endpoint(
    trip_id: uuid.UUID,
    body: TripCopyRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripCopyResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        source = await get_trip_for_user(db, trip_id=trip_id, user_id=actor_id)
        trip, created, day_count, poi_count, attachment_count = await copy_trip(
            db,
            source_trip=source,
            actor_user_id=actor_id,
            title=body.title,
            scope=body.scope,
            day_index=body.day_index,
            start_day_index=body.start_day_index,
            end_day_index=body.end_day_index,
            date_shift_days=body.date_shift_days,
            target_trip_id=body.target_trip_id,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (TripCopyError, TripDayNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = TripCopyResponse(
        trip=_to_response(trip),
        created_trip=created,
        copied_day_count=day_count,
        copied_poi_count=poi_count,
        copied_attachment_count=attachment_count,
    )
    realtime_broker.publish_event_nowait(
        trip_id=trip.trip_id,
        event_type="trip.copied",
        actor_user_id=actor_id,
        payload=response.model_dump(mode="json"),
        version=trip.version,
    )
    return Envelope.of(response)


@router.post(
    "/{trip_id}/days",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripDayResponse],
)
async def create_trip_day_endpoint(
    trip_id: uuid.UUID,
    body: TripDayCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripDayResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        trip = await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        day_index = body.day_index
        if day_index is None:
            day_index = await next_available_trip_day_index(db, trip=trip)
        date_value = body.date
        if date_value is None:
            date_value = default_trip_day_date(trip.start_date, day_index)
        await validate_trip_day_payload(
            db,
            trip=trip,
            day_index=day_index,
            date_value=date_value,
        )
        day = await create_trip_day(
            db,
            trip_id=trip_id,
            day_index=day_index,
            date_value=date_value,
            title=body.title,
            note=body.note,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripDayValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = _to_day_response(day)
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="day.created",
        actor_user_id=actor_id,
        payload={"day": response.model_dump(mode="json")},
    )
    return Envelope.of(response)


@router.patch("/{trip_id}/days/{day_index}", response_model=Envelope[TripDayResponse])
async def update_trip_day_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    body: TripDayUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
    if_match: Annotated[int, Header(alias="If-Match")],
) -> Envelope[TripDayResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        trip = await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        patch = body.model_dump(exclude_unset=True)
        if "date" in patch:
            await validate_trip_day_payload(
                db,
                trip=trip,
                day_index=day_index,
                date_value=patch["date"],
                exclude_day_index=day_index,
            )
        day = await update_trip_day(
            db,
            trip_id=trip_id,
            day_index=day_index,
            expected_version=if_match,
            patch=patch,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripDayConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripDayValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = _to_day_response(day)
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="day.updated",
        actor_user_id=actor_id,
        payload={"day": response.model_dump(mode="json")},
    )
    return Envelope.of(response)


@router.delete("/{trip_id}/days/{day_index}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip_day_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    current_user_id: CurrentUserId,
    db: DbSession,
    if_match: Annotated[int, Header(alias="If-Match")],
) -> None:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        await delete_trip_day(db, trip_id=trip_id, day_index=day_index, expected_version=if_match)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    realtime_broker.publish_event_nowait(
        trip_id=trip_id,
        event_type="day.deleted",
        actor_user_id=actor_id,
        payload={"day_index": day_index},
    )


@router.get(
    "/{trip_id}/shared/{token}",
    response_model=Envelope[TripSharedView],
)
async def get_shared_trip_endpoint(
    trip_id: uuid.UUID,
    token: str,
    db: DbSession,
    kor_travel_map_client: OptionalKorTravelMapHttpClientDep,
) -> Envelope[TripSharedView]:
    try:
        trip, share = await get_trip_for_share_token(db, trip_id=trip_id, token=token)
    except TripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    view = TripView.model_validate(
        await build_trip_view(
            db, trip=trip, kor_travel_map_client=kor_travel_map_client, include_management=False
        )
    )
    return Envelope.of(
        TripSharedView(
            visibility=share.visibility,
            trip=view.trip,
            days=view.days,
            broken_feature_count=view.broken_feature_count,
        )
    )


@router.get(
    "/{trip_id}/attachments",
    response_model=Envelope[list[TripAttachmentResponse]],
)
async def list_trip_attachments_endpoint(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[TripAttachmentResponse]]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    attachments = await list_attachments(db, trip_id=trip_id)
    return Envelope.of([_to_attachment_response(attachment) for attachment in attachments])


@router.post(
    "/{trip_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripAttachmentResponse],
)
async def create_trip_attachment_endpoint(
    trip_id: uuid.UUID,
    body: AttachmentCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripAttachmentResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    try:
        attachment = await create_attachment(
            db,
            uploaded_by_user_id=actor_id,
            trip_id=trip_id,
            trip_day_index=None,
            trip_poi_id=None,
            quota_trip_id=trip_id,
            payload=body.model_dump(),
        )
    except TripAttachmentLimitError as exc:
        _raise_attachment_limit(exc)
    except TripAttachmentStorageRefError as exc:
        _raise_attachment_storage_ref(exc)
    except TripAttachmentQuotaError as exc:
        _raise_attachment_quota(exc)
    return Envelope.of(_to_attachment_response(attachment))


@router.patch(
    "/{trip_id}/attachments/{attachment_id}", response_model=Envelope[TripAttachmentResponse]
)
async def update_trip_attachment_endpoint(
    trip_id: uuid.UUID,
    attachment_id: uuid.UUID,
    body: AttachmentUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripAttachmentResponse]:
    """첨부 재정렬(sort_order)/설명 수정 — 편집 권한 필요."""
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        attachment = await update_attachment(
            db,
            attachment_id=attachment_id,
            trip_id=trip_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripAttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_attachment_response(attachment))


@router.delete(
    "/{trip_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_trip_attachment_endpoint(
    trip_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await delete_attachment(db, attachment_id=attachment_id, trip_id=trip_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripAttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get(
    "/{trip_id}/attachments/{attachment_id}/download-url",
    response_model=Envelope[DownloadUrlResponse],
)
async def trip_attachment_download_url_endpoint(
    trip_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    """첨부 본문 접근용 presigned GET URL(읽기 권한 — 동반자 포함)."""
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        attachment = await get_attachment(db, attachment_id=attachment_id, trip_id=trip_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripAttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(
        make_download_url(
            bucket=attachment.bucket,
            storage_key=attachment.storage_key,
            public_url=attachment.public_url,
            public_api_base_url=public_api_base_url(request),
        )
    )


@router.get(
    "/{trip_id}/days/{day_index}/attachments",
    response_model=Envelope[list[TripAttachmentResponse]],
)
async def list_trip_day_attachments_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[TripAttachmentResponse]]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_trip_day(db, trip_id=trip_id, day_index=day_index)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    attachments = await list_attachments(db, trip_id=trip_id, trip_day_index=day_index)
    return Envelope.of([_to_attachment_response(attachment) for attachment in attachments])


@router.post(
    "/{trip_id}/days/{day_index}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripAttachmentResponse],
)
async def create_trip_day_attachment_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    body: AttachmentCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripAttachmentResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        await get_trip_day(db, trip_id=trip_id, day_index=day_index)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    try:
        attachment = await create_attachment(
            db,
            uploaded_by_user_id=actor_id,
            trip_id=trip_id,
            trip_day_index=day_index,
            trip_poi_id=None,
            quota_trip_id=trip_id,
            payload=body.model_dump(),
        )
    except TripAttachmentLimitError as exc:
        _raise_attachment_limit(exc)
    except TripAttachmentStorageRefError as exc:
        _raise_attachment_storage_ref(exc)
    except TripAttachmentQuotaError as exc:
        _raise_attachment_quota(exc)
    return Envelope.of(_to_attachment_response(attachment))


@router.delete(
    "/{trip_id}/days/{day_index}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_trip_day_attachment_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    attachment_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_trip_day(db, trip_id=trip_id, day_index=day_index)
        await delete_attachment(
            db,
            attachment_id=attachment_id,
            trip_id=trip_id,
            trip_day_index=day_index,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (TripDayNotFoundError, TripAttachmentNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get(
    "/{trip_id}/days/{day_index}/attachments/{attachment_id}/download-url",
    response_model=Envelope[DownloadUrlResponse],
)
async def trip_day_attachment_download_url_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    attachment_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_trip_day(db, trip_id=trip_id, day_index=day_index)
        attachment = await get_attachment(
            db,
            attachment_id=attachment_id,
            trip_id=trip_id,
            trip_day_index=day_index,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (TripDayNotFoundError, TripAttachmentNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(
        make_download_url(
            bucket=attachment.bucket,
            storage_key=attachment.storage_key,
            public_url=attachment.public_url,
            public_api_base_url=public_api_base_url(request),
        )
    )


@router.get(
    "/{trip_id}/pois/{poi_id}/attachments",
    response_model=Envelope[list[TripAttachmentResponse]],
)
async def list_trip_poi_attachments_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[TripAttachmentResponse]]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except PoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    attachments = await list_attachments(db, trip_poi_id=poi_id)
    return Envelope.of([_to_attachment_response(attachment) for attachment in attachments])


@router.post(
    "/{trip_id}/pois/{poi_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[TripAttachmentResponse],
)
async def create_trip_poi_attachment_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    body: AttachmentCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripAttachmentResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except PoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    try:
        attachment = await create_attachment(
            db,
            uploaded_by_user_id=actor_id,
            trip_id=None,
            trip_poi_id=poi_id,
            quota_trip_id=trip_id,
            payload=body.model_dump(),
        )
    except TripAttachmentLimitError as exc:
        _raise_attachment_limit(exc)
    except TripAttachmentStorageRefError as exc:
        _raise_attachment_storage_ref(exc)
    except TripAttachmentQuotaError as exc:
        _raise_attachment_quota(exc)
    return Envelope.of(_to_attachment_response(attachment))


@router.patch(
    "/{trip_id}/pois/{poi_id}/attachments/{attachment_id}",
    response_model=Envelope[TripAttachmentResponse],
)
async def update_trip_poi_attachment_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    attachment_id: uuid.UUID,
    body: AttachmentUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripAttachmentResponse]:
    """POI 첨부 재정렬(sort_order)/설명 수정 — 편집 권한 필요."""
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
        attachment = await update_attachment(
            db,
            attachment_id=attachment_id,
            trip_poi_id=poi_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (PoiNotFoundError, TripAttachmentNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_attachment_response(attachment))


@router.delete(
    "/{trip_id}/pois/{poi_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_trip_poi_attachment_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
        await delete_attachment(db, attachment_id=attachment_id, trip_poi_id=poi_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (PoiNotFoundError, TripAttachmentNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get(
    "/{trip_id}/pois/{poi_id}/attachments/{attachment_id}/download-url",
    response_model=Envelope[DownloadUrlResponse],
)
async def trip_poi_attachment_download_url_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    """POI 첨부 presigned GET URL(읽기 권한 — 동반자 포함)."""
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
        attachment = await get_attachment(db, attachment_id=attachment_id, trip_poi_id=poi_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except (PoiNotFoundError, TripAttachmentNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(
        make_download_url(
            bucket=attachment.bucket,
            storage_key=attachment.storage_key,
            public_url=attachment.public_url,
            public_api_base_url=public_api_base_url(request),
        )
    )


@router.get(
    "/{trip_id}/days/{day_index}/distance-matrix",
    response_model=Envelope[TripDistanceMatrixResponse],
)
async def get_trip_day_distance_matrix_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripDistanceMatrixResponse]:
    try:
        await get_trip_for_user(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    pois, matrix, warnings = await build_distance_matrix(db, trip_id=trip_id, day_index=day_index)
    return Envelope.of(
        TripDistanceMatrixResponse(
            trip_id=trip_id,
            day_index=day_index,
            poi_ids=[poi.attachment_id for poi in pois],
            distances_meters=matrix,
            warnings=warnings,
        )
    )


@router.post(
    "/{trip_id}/days/{day_index}/optimize",
    response_model=Envelope[TripDayOptimizeResponse],
)
async def optimize_trip_day_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    body: TripDayOptimizeRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TripDayOptimizeResponse]:
    actor_id = uuid.UUID(current_user_id)
    try:
        if body.persist:
            await get_trip_for_user_write(db, trip_id=trip_id, user_id=actor_id)
        else:
            await get_trip_for_user(db, trip_id=trip_id, user_id=actor_id)
        ordered, moves, total_distance, previous_distance, warnings = await optimize_trip_day(
            db,
            trip_id=trip_id,
            day_index=day_index,
            start_poi_id=body.start_poi_id,
            persist=body.persist,
            strategy=body.strategy,
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        _raise_trip_http(exc)
    except TripDayNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripOptimizeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = TripDayOptimizeResponse(
        trip_id=trip_id,
        day_index=day_index,
        ordered_poi_ids=[poi.attachment_id for poi in ordered],
        moves=[
            {"poi_id": poi.attachment_id, "old_sort_order": old, "new_sort_order": new}
            for poi, old, new in moves
        ],
        distance_meters=total_distance,
        previous_distance_meters=previous_distance,
        warnings=warnings,
    )
    if body.persist and moves:
        realtime_broker.publish_event_nowait(
            trip_id=trip_id,
            event_type="poi.reordered",
            actor_user_id=actor_id,
            payload={"moves": response.model_dump(mode="json")["moves"]},
        )
    return Envelope.of(response)


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
    # T-106 §8 — 초대된 기존 사용자 알림을 outbox에 적재(전송은 worker).
    if companion.user_id is not None:
        await enqueue_user_notification(
            db,
            category="companion_invited",
            user_id=companion.user_id,
            text=build_companion_invited_message(
                trip_title=trip.title,
                display_name=companion.invited_nickname,
            ),
        )
        await db.commit()
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
    web_base_url = settings.pinvi_web_base_url.rstrip("/")
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

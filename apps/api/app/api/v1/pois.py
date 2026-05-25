"""`/trips/{trip_id}/pois/*` — `docs/api/pois.md`."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.core.deps import CurrentUserId, DbSession
from app.schemas.envelope import Envelope
from app.schemas.poi import PoiCreate, PoiReorderRequest, PoiResponse, PoiUpdate
from app.services.poi import (
    PoiNotFoundError,
    PoiVersionConflictError,
    SortOrderConflictError,
    create_poi,
    get_poi,
    reorder_pois,
    soft_delete_poi,
    update_poi,
)
from app.services.trip import (
    TripNotFoundError,
    TripPermissionError,
    get_trip_for_user,
)

router = APIRouter(prefix="/trips/{trip_id}/pois", tags=["pois"])


def _to_response(poi) -> PoiResponse:  # type: ignore[no-untyped-def]
    return PoiResponse(
        attachment_id=poi.attachment_id,
        trip_id=poi.trip_id,
        day_index=poi.day_index,
        sort_order=poi.sort_order,
        feature_id=poi.feature_id,
        feature_link_broken_at=poi.feature_link_broken_at,
        feature_snapshot=poi.feature_snapshot,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        planned_arrival_at=poi.planned_arrival_at,
        planned_departure_at=poi.planned_departure_at,
        user_note=poi.user_note,
        budget_amount=poi.budget_amount,
        actual_amount=poi.actual_amount,
        currency=poi.currency,
        user_url=poi.user_url,
        version=poi.version,
        created_at=poi.created_at,
        updated_at=poi.updated_at,
    )


async def _trip_or_404(db, trip_id: uuid.UUID, user_id: uuid.UUID):  # type: ignore[no-untyped-def]
    try:
        return await get_trip_for_user(db, trip_id=trip_id, user_id=user_id)
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[PoiResponse],
)
async def create_poi_endpoint(
    trip_id: uuid.UUID,
    body: PoiCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[PoiResponse]:
    await _trip_or_404(db, trip_id, uuid.UUID(current_user_id))
    try:
        poi = await create_poi(
            db,
            trip_id=trip_id,
            day_index=body.day_index,
            sort_order=body.sort_order,
            feature_id=body.feature_id,
            feature_snapshot=body.feature_snapshot,
            added_by_user_id=uuid.UUID(current_user_id),
            custom_marker_color=body.custom_marker_color,
            custom_marker_icon=body.custom_marker_icon,
            user_note=body.user_note,
        )
    except SortOrderConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_response(poi))


@router.patch("/{poi_id}", response_model=Envelope[PoiResponse])
async def update_poi_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    body: PoiUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
    if_match: Annotated[int, Header(alias="If-Match")],
) -> Envelope[PoiResponse]:
    await _trip_or_404(db, trip_id, uuid.UUID(current_user_id))
    try:
        poi = await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
        poi = await update_poi(
            db,
            poi=poi,
            expected_version=if_match,
            patch=body.model_dump(exclude_unset=True),
        )
    except PoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PoiVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(_to_response(poi))


@router.delete("/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poi_endpoint(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await _trip_or_404(db, trip_id, uuid.UUID(current_user_id))
    try:
        poi = await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
        await soft_delete_poi(db, poi=poi)
    except PoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.post("/reorder", response_model=Envelope[list[PoiResponse]])
async def reorder_pois_endpoint(
    trip_id: uuid.UUID,
    body: PoiReorderRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[PoiResponse]]:
    await _trip_or_404(db, trip_id, uuid.UUID(current_user_id))
    moves = [(m.poi_id, m.new_sort_order) for m in body.moves]
    try:
        updated = await reorder_pois(db, trip_id=trip_id, moves=moves)
    except PoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except SortOrderConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of([_to_response(p) for p in updated])

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import require_current_user
from app.db.session import get_db
from app.models.trip import PlanPoiAttachment, TripPlanItem
from app.models.user import User
from app.schemas.attachment import (
    PlanPoiAttachmentCreateRequest,
    PlanPoiAttachmentListResponse,
    PlanPoiAttachmentResponse,
)
from app.schemas.trip import TripPlanItemCreateRequest, TripPlanItemResponse
from app.services.plan_poi_attachment import (
    AttachmentAccessDeniedError,
    AttachmentNotFoundError,
    create_trip_attachment,
    create_trip_poi_attachment,
    delete_trip_attachment,
    delete_trip_poi_attachment,
    list_trip_attachments,
    list_trip_poi_attachments,
    to_attachment_response,
)
from app.services.trip_plan import (
    TripPlanAccessDeniedError,
    TripPlanNotFoundError,
    TripPlanValidationError,
    create_trip_plan_item,
)

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get(
    "/{trip_id}/attachments",
    response_model=PlanPoiAttachmentListResponse,
)
def get_trip_attachments(
    trip_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> PlanPoiAttachmentListResponse:
    try:
        attachments = list_trip_attachments(db, current_user=current_user, trip_id=trip_id)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _attachment_list_response(attachments)


@router.post(
    "/{trip_id}/attachments",
    response_model=PlanPoiAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_trip_attachment(
    trip_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> PlanPoiAttachmentResponse:
    try:
        attachment = create_trip_attachment(
            db,
            current_user=current_user,
            trip_id=trip_id,
            payload=payload,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()
    db.refresh(attachment)
    return to_attachment_response(attachment)


@router.delete("/{trip_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_trip_attachment(
    trip_id: UUID,
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> None:
    try:
        delete_trip_attachment(
            db,
            current_user=current_user,
            trip_id=trip_id,
            attachment_id=attachment_id,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()


@router.get(
    "/{trip_id}/pois/{poi_id}/attachments",
    response_model=PlanPoiAttachmentListResponse,
)
def get_trip_poi_attachments(
    trip_id: UUID,
    poi_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> PlanPoiAttachmentListResponse:
    try:
        attachments = list_trip_poi_attachments(
            db,
            current_user=current_user,
            trip_id=trip_id,
            poi_id=poi_id,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _attachment_list_response(attachments)


@router.post(
    "/{trip_id}/pois/{poi_id}/attachments",
    response_model=PlanPoiAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_trip_poi_attachment(
    trip_id: UUID,
    poi_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> PlanPoiAttachmentResponse:
    try:
        attachment = create_trip_poi_attachment(
            db,
            current_user=current_user,
            trip_id=trip_id,
            poi_id=poi_id,
            payload=payload,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()
    db.refresh(attachment)
    return to_attachment_response(attachment)


@router.delete(
    "/{trip_id}/pois/{poi_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_trip_poi_attachment(
    trip_id: UUID,
    poi_id: UUID,
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> None:
    try:
        delete_trip_poi_attachment(
            db,
            current_user=current_user,
            trip_id=trip_id,
            poi_id=poi_id,
            attachment_id=attachment_id,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AttachmentAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()


@router.post(
    "/{trip_id}/days/{trip_day_id}/items",
    response_model=TripPlanItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_trip_day_item(
    trip_id: UUID,
    trip_day_id: UUID,
    payload: TripPlanItemCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> TripPlanItemResponse:
    try:
        item = create_trip_plan_item(
            db,
            current_user=current_user,
            trip_id=trip_id,
            trip_day_id=trip_day_id,
            payload=payload,
        )
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TripPlanAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TripPlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    db.refresh(item)
    return _to_trip_plan_item_response(item)


def _to_trip_plan_item_response(item: TripPlanItem) -> TripPlanItemResponse:
    return TripPlanItemResponse(
        id=item.id,
        trip_day_id=item.trip_day_id,
        resource_type=item.resource_type,
        sort_order=item.sort_order,
        map_feature_id=item.map_feature_id,
        festival_id=item.festival_id,
        resource_key=item.resource_key,
        title_snapshot=item.title_snapshot,
        address_snapshot=item.address_snapshot,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        operating_hours_snapshot=item.operating_hours_snapshot,
        longitude=item.longitude,
        latitude=item.latitude,
        note=item.note,
        resource_metadata=item.resource_metadata,
    )


def _attachment_list_response(
    attachments: list[PlanPoiAttachment],
) -> PlanPoiAttachmentListResponse:
    return PlanPoiAttachmentListResponse(
        items=[to_attachment_response(attachment) for attachment in attachments],
        total=len(attachments),
    )

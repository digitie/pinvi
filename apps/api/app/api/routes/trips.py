from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import require_current_user
from app.db.session import get_db
from app.models.trip import TripPlanItem
from app.models.user import User
from app.schemas.trip import TripPlanItemCreateRequest, TripPlanItemResponse
from app.services.trip_plan import (
    TripPlanAccessDeniedError,
    TripPlanNotFoundError,
    TripPlanValidationError,
    create_trip_plan_item,
)

router = APIRouter(prefix="/trips", tags=["trips"])


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

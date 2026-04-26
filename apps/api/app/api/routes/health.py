from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="tripmate-api")


@router.get("/health/db", response_model=DatabaseHealthResponse)
def database_health(db: Annotated[Session, Depends(get_db)]) -> DatabaseHealthResponse:
    db.execute(text("SELECT 1"))
    return DatabaseHealthResponse(status="ok", database="ok")

"""FastAPI v1 라우터 모음."""

from fastapi import APIRouter

from app.api.v1 import auth, healthz

api_router = APIRouter()
api_router.include_router(healthz.router)
api_router.include_router(auth.router)

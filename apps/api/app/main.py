from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.public import router as public_router
from app.api.routes.regions import router as regions_router
from app.api.routes.storage import router as storage_router
from app.api.routes.trips import router as trips_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(admin_router)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(public_router)
    app.include_router(regions_router)
    app.include_router(storage_router)
    app.include_router(trips_router)
    return app


app = create_app()

"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api_v1.routes import api_v1_router
from app.config import settings
from app.core.cache import close_redis, get_redis
from app.core.database import dispose_engines
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    # Warm Redis connection (best-effort; ignore failures so API can start without it)
    with suppress(Exception):
        await get_redis()
    yield
    with suppress(Exception):
        await close_redis()
    await dispose_engines()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.APP_DEBUG,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    # Request ID + structured access logs
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Routes
    app.include_router(api_v1_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}

    return app


app = create_app()

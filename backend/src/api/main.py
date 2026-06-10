"""FastAPI application — lifespan startup/shutdown and route mounting."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import APIKeyMiddleware, RequestIDMiddleware
from api.routes import actions, memory, query
from bootstrap.startup import initialize_application, shutdown_application
from core.settings import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise all singletons on startup; clean up on shutdown."""
    settings = get_settings()

    logger.info("Starting E-Commerce Operations Brain API")

    initialize_application(settings)

    logger.info("API startup complete")
    yield

    await shutdown_application()
    logger.info("API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    cors_allowed_origins = settings.resolved_cors_allowed_origins()
    app = FastAPI(
        title="E-Commerce Operations Brain",
        description="Multi-agent AI system for e-commerce root-cause analysis",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins or ["http://localhost:3000"],
        allow_credentials=cors_allowed_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(APIKeyMiddleware, api_key=settings.api_key)
    app.add_middleware(RequestIDMiddleware)

    # Routes
    app.include_router(query.router)
    app.include_router(actions.router)
    app.include_router(memory.router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

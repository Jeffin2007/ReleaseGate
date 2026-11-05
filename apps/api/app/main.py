"""
ReleaseGate FastAPI Control Plane Application Entry Point.
Implements bounded governance API gateway, startup validation, and health probes.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1.endpoints.health import router as health_root_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger("releasegate.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Executes fail-fast startup checks and initializes logging.
    """
    # 1. Initialize centralized logging with sensitive pattern redaction
    configure_logging(
        log_level=settings.LOG_LEVEL,
        redact_sensitive=settings.REDACT_SENSITIVE_LOGS,
        log_format=settings.LOG_FORMAT,
    )

    # 2. Startup configuration validation & logging
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} "
        f"[Environment: {settings.ENVIRONMENT}] [Debug: {settings.DEBUG}]"
    )

    # Database URL is automatically sanitized by logging redaction filter
    logger.info(f"Configured Database URL: {settings.DATABASE_URL}")

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")


def create_application() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "ReleaseGate Control Plane API — Evidence-driven data release governance, "
            "independent review orchestration, and hash-bound authorization."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount root-level health probes (/health and /ready)
    app.include_router(health_root_router)

    # Mount versioned API routes (/api/v1/...)
    app.include_router(api_router, prefix=settings.API_PREFIX)

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )

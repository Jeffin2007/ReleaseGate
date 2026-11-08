"""
SQLAlchemy 2.0 database engine and session management.
Supports production PostgreSQL connection pooling and test isolation.
"""

import time
from typing import Generator, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Engine creation with support for PostgreSQL pooling and SQLite (testing)
engine_kwargs = {
    "echo": settings.DB_ECHO,
}

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite configuration for lightweight unit/integration testing
    engine_kwargs.update(
        {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    )
else:
    # Production-grade PostgreSQL pooling configuration
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_pre_ping": settings.DB_POOL_PRE_PING,
        }
    )

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding an isolated database session per request.
    Automatically closes session upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(timeout_seconds: Optional[float] = None) -> Tuple[bool, float, Optional[str]]:
    """
    Executes a lightweight query (SELECT 1) to test database reachability and measure round-trip latency.

    Returns:
        Tuple of (is_connected: bool, latency_ms: float, error_message: Optional[str])
    """
    start_time = time.perf_counter()
    timeout = timeout_seconds or settings.DB_READINESS_TIMEOUT_SECONDS

    try:
        # Establish connection and execute ping query
        with engine.connect() as connection:
            # Set execution timeout if PostgreSQL
            if not settings.DATABASE_URL.startswith("sqlite"):
                connection.execute(
                    text(f"SET statement_timeout = {int(timeout * 1000)}")
                )
            connection.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return True, latency_ms, None
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        logger.warning(f"Database readiness ping failed after {latency_ms}ms: {error_msg}")
        return False, latency_ms, error_msg

# ReleaseGate Control Plane API Foundation

[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python)](https://python.org)
[![SQLAlchemy 2.0](https://img.shields.io/badge/ORM-SQLAlchemy_2.0-red.svg)](https://www.sqlalchemy.org)
[![Alembic](https://img.shields.io/badge/Migrations-Alembic-orange.svg)](https://alembic.sqlalchemy.org)

The **ReleaseGate Control Plane API** serves as the cloud-side governance gateway for the hybrid ReleaseGate system. It manages user authentication, role-based access control (RBAC), release job coordination, human-in-the-loop approvals, and tamper-evident audit logging.

> **Architecture Status**: Frozen ReleaseGate Architecture Baseline v1.0 — Phase 4 Foundation.

---

## Directory Architecture

```
apps/api/
├── alembic.ini                   # Alembic database migration configuration
├── alembic/                      # Database migration environment & versions
│   ├── env.py                    # Dynamic migration runner connected to SQLAlchemy Base
│   ├── script.py.mako            # Migration revision script template
│   └── versions/                 # Revision history (.gitkeep)
├── app/                          # Core FastAPI Application Source
│   ├── main.py                   # Application entry point, lifespan, and CORS setup
│   ├── core/                     # Centralized Core Utilities
│   │   ├── config.py             # Pydantic Settings configuration with fail-fast validation
│   │   └── logging.py            # Centralized logger with sensitive-value redaction
│   ├── api/                      # Versioned Routing Layer
│   │   ├── router.py             # Aggregated router mounting API namespaces
│   │   └── v1/
│   │       └── endpoints/
│   │           └── health.py     # Liveness (/health) and readiness (/ready) endpoints
│   ├── schemas/                  # Pydantic Request & Response Models
│   │   └── health.py             # Health & readiness payload schemas
│   ├── services/                 # Business Logic & Diagnostics
│   │   └── health_service.py     # Health checks and database ping diagnostics
│   └── db/                       # Database Session & Metadata Layer
│       ├── base.py               # SQLAlchemy 2.0 DeclarativeBase
│       └── session.py            # Engine configuration, connection pooling, and get_db dependency
├── tests/                        # Automated Pytest Test Suite
│   ├── conftest.py               # Shared test client and environment fixtures
│   ├── test_config.py            # Configuration & fail-fast validation unit tests
│   ├── test_health.py            # Health and readiness endpoint integration tests
│   └── test_logging.py           # Sensitive data redaction filter tests
├── .env.example                  # Environment configuration template
├── pyproject.toml                # Project metadata & Pytest configuration
├── requirements.txt              # Pinned Python dependencies
└── README.md                     # Backend setup and developer documentation
```

---

## Core Capabilities & Design Decisions

### 1. Centralized Environment Configuration (`app/core/config.py`)
* Built with `pydantic-settings` adhering to 12-Factor application principles.
* Loads environment variables from `.env` or system environment.
* **Fail-Fast Validation**: Rejects invalid database protocol schemes and enforces production constraints (blocks default secrets, prevents SQLite in production).

### 2. Centralized Sensitive-Value Redaction Logging (`app/core/logging.py`)
* Automatically redacts credentials, passwords, Bearer tokens, API keys, database connection strings, SSNs, and payment card numbers before writing to console/log files.

### 3. SQLAlchemy 2.0 Database Layer (`app/db/`)
* Modern `DeclarativeBase` for upcoming data entity definitions.
* Production connection pooling configured with `pool_pre_ping=True`, configurable pool sizes, and graceful reconnection handling.
* Dedicated `check_db_connection()` diagnostic routine with statement timeouts.

### 4. Alembic Migration Setup (`alembic/`)
* Pre-configured and linked directly to `app.db.base.Base.metadata` and `settings.DATABASE_URL`.
* Ready for the upcoming Phase 4 database migration definitions.

### 5. Health & Dependency Readiness Probes
* **`GET /health`** (and `GET /api/v1/health`): Immediate liveness check returning process status, version, and environment.
* **`GET /ready`** (and `GET /api/v1/ready`): Readiness probe executing `SELECT 1` against PostgreSQL. Returns HTTP 200 when ready to accept traffic, or HTTP 503 Service Unavailable when the database is unreachable.

---

## Prerequisites

* **Python 3.10+** (Python 3.11+ recommended)
* **PostgreSQL 14+** (for local development or Docker container)
* **pip** or **virtualenv**

---

## Installation & Local Execution

### 1. Create and Activate Virtual Environment

```bash
# Navigate to the API root
cd apps/api

# Create an isolated Python virtual environment
python3 -m venv .venv

# Activate virtual environment
# On Linux / macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

### 2. Install Pinned Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Local Environment Variables

```bash
cp .env.example .env
```

Edit `.env` to configure your local PostgreSQL connection:

```env
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/releasegate_db
SECRET_KEY=local-development-secret-key-12345
```

### 4. Run the Development Server

```bash
# Start Uvicorn ASGI server with hot reloading
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation will be accessible at:
* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* Health Probe: [http://localhost:8000/health](http://localhost:8000/health)
* Readiness Probe: [http://localhost:8000/ready](http://localhost:8000/ready)

---

## Running Automated Tests

Run the test suite using `pytest`:

```bash
pytest
```

To run with verbose output and test coverage:

```bash
pytest -v
```

---

## Database Migrations (Alembic)

Once database entities are defined in upcoming development phases:

```bash
# Generate a new migration revision
alembic revision --autogenerate -m "create releasegate core tables"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

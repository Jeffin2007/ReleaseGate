"""
Aggregated API Router for ReleaseGate Control Plane.
Mounts modular endpoint routers under versioned namespaces.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import datasets, health

api_router = APIRouter()

# Mount health diagnostics
api_router.include_router(health.router)

# Mount dataset ingestion & governance
api_router.include_router(datasets.router)

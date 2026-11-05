"""
Dataset metadata coordination and local ingestion gateway REST endpoints.
Strictly enforces the ReleaseGate Hybrid Architecture Baseline v1.0:
1. POST /datasets/register-metadata: Pure Cloud Control Plane endpoint that accepts ONLY
   sanitized metadata, SHA-256 hashes, opaque artifact references, and profiling summaries
   sent outbound by the Local Worker.
2. POST /datasets/ingest: Local-worker gateway adapter that streams upload chunks directly
   to the LocalIngestionWorker with bounded memory usage (never calling await file.read()
   to load the full file into Cloud API RAM) and registers only sanitized metadata.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dataset import (
    DatasetIngestResponse,
    DatasetMetadataRegistrationRequest,
    DatasetResponse,
    DatasetVersionResponse,
)
from app.services.dataset_service import (
    DatasetNotFoundError,
    DatasetService,
    DatasetVersionNotFoundError,
)
from engines.dataset_profiler.profiler import ProfilingError
from local_worker.secure_storage import SecureStorageError
from local_worker.validator import DatasetEmptyError, DatasetValidationError

router = APIRouter(prefix="/datasets", tags=["Dataset Ingestion & Governance"])
dataset_service = DatasetService()


@router.post(
    "/register-metadata",
    response_model=DatasetIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Sanitized Dataset Metadata (Cloud Control Plane)",
    description=(
        "Pure Cloud Control Plane endpoint called outbound by the Local Worker. "
        "Receives ONLY sanitized metadata, SHA-256 content hashes, opaque artifact references, "
        "and deterministic profiling summaries. Raw dataset bytes never enter this endpoint."
    ),
)
def register_dataset_metadata(
    registration: DatasetMetadataRegistrationRequest,
    db: Session = Depends(get_db),
) -> DatasetIngestResponse:
    """Register sanitized dataset metadata emitted by the Local Data Processing Plane."""
    try:
        return dataset_service.register_dataset_metadata(
            registration=registration,
            db=db,
        )
    except DatasetNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register dataset metadata: {str(err)}",
        ) from err


@router.post(
    "/ingest",
    response_model=DatasetIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Local Worker Ingestion Gateway (Bounded Stream)",
    description=(
        "Streams a dataset file directly to the LocalIngestionWorker using a bounded file-like stream "
        "(SpooledTemporaryFile) without loading the raw payload into Cloud API memory, then registers "
        "only the sanitized metadata with the Cloud Control Plane."
    ),
)
def ingest_dataset(
    file: UploadFile = File(..., description="Dataset file (CSV, XLSX, JSON)"),
    dataset_name: Optional[str] = Form(None, description="Optional custom dataset name"),
    description: Optional[str] = Form(None, description="Optional dataset description"),
    dataset_id: Optional[uuid.UUID] = Form(None, description="Target dataset ID if creating a new version"),
    db: Session = Depends(get_db),
) -> DatasetIngestResponse:
    """Stream upload directly into LocalIngestionWorker with bounded memory and register sanitized metadata."""
    try:
        filename = file.filename or "uploaded_dataset"

        # Pass the underlying SpooledTemporaryFile stream (file.file) directly to the local worker
        # so the FastAPI route never calls `await file.read()` to buffer unbounded bytes in RAM.
        result = dataset_service.ingest_dataset(
            filename=filename,
            content=file.file,
            dataset_name=dataset_name,
            description=description,
            dataset_id=dataset_id,
            db=db,
        )
        return result
    except (DatasetValidationError, DatasetEmptyError, ProfilingError, SecureStorageError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset validation failed: {str(err)}",
        ) from err
    except DatasetNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during dataset ingestion: {str(err)}",
        ) from err


@router.get(
    "",
    response_model=List[DatasetResponse],
    summary="List Registered Datasets",
    description="Retrieve all registered dataset containers with summary version counts.",
)
def list_datasets(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[DatasetResponse]:
    """List datasets with pagination."""
    return dataset_service.list_datasets(db=db, limit=limit, skip=skip)


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get Dataset Details",
    description="Retrieve a dataset container along with its complete version history and profiling records.",
)
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DatasetResponse:
    """Get single dataset by ID."""
    try:
        return dataset_service.get_dataset(dataset_id=dataset_id, db=db)
    except DatasetNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.get(
    "/{dataset_id}/versions/{version_number}",
    response_model=DatasetVersionResponse,
    summary="Get Specific Dataset Version Profile",
    description="Retrieve profiling metrics, content hash, and secure artifact reference for an exact immutable version.",
)
def get_dataset_version(
    dataset_id: uuid.UUID,
    version_number: int,
    db: Session = Depends(get_db),
) -> DatasetVersionResponse:
    """Get specific version profile."""
    try:
        return dataset_service.get_dataset_version(
            dataset_id=dataset_id,
            version_number=version_number,
            db=db,
        )
    except DatasetVersionNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err

"""
Dataset ingestion and inspection REST endpoints.
Allows authenticated-ready dataset upload, deterministic profiling, and version inspection.
Guarantees raw files remain strictly in local isolated storage.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dataset import DatasetIngestResponse, DatasetResponse, DatasetVersionResponse
from app.services.dataset_service import (
    DatasetNotFoundError,
    DatasetService,
    DatasetVersionNotFoundError,
)
from engines.dataset_profiler.profiler import ProfilingError
from local_worker.validator import DatasetEmptyError, DatasetValidationError

router = APIRouter(prefix="/datasets", tags=["Dataset Ingestion & Governance"])
dataset_service = DatasetService()


@router.post(
    "/ingest",
    response_model=DatasetIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Dataset File",
    description=(
        "Uploads a CSV, XLSX, or JSON dataset. Validates magic bytes and structure, "
        "calculates cryptographic SHA-256 hash, performs deterministic Pandas profiling, "
        "and securely stores the raw data locally outside web directories."
    ),
)
async def ingest_dataset(
    file: UploadFile = File(..., description="Dataset file (CSV, XLSX, JSON)"),
    dataset_name: Optional[str] = Form(None, description="Optional custom dataset name"),
    description: Optional[str] = Form(None, description="Optional dataset description"),
    dataset_id: Optional[uuid.UUID] = Form(None, description="Target dataset ID if creating a new version"),
    db: Session = Depends(get_db),
) -> DatasetIngestResponse:
    """Ingest, validate, hash, profile, and persist a dataset file."""
    try:
        content = await file.read()
        filename = file.filename or "uploaded_dataset"

        result = dataset_service.ingest_dataset(
            filename=filename,
            content=content,
            dataset_name=dataset_name,
            description=description,
            dataset_id=dataset_id,
            db=db,
        )
        return result
    except (DatasetValidationError, DatasetEmptyError, ProfilingError) as err:
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
    summary="List Ingested Datasets",
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

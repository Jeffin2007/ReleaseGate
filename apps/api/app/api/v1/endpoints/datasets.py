"""
Dataset metadata coordination REST endpoints for the Cloud Control Plane API.
Strictly enforces the ReleaseGate Hybrid Architecture Baseline v1.0:
- The Cloud Control Plane accepts ONLY sanitized metadata, SHA-256 content hashes,
  opaque artifact references, and deterministic profiling summaries via POST /datasets/register-metadata.
- Raw file upload routes are strictly EXCLUDED from the Cloud Control Plane API.
"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/datasets", tags=["Dataset Metadata Coordination"])
dataset_service = DatasetService()


@router.post(
    "/register-metadata",
    response_model=DatasetIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Sanitized Dataset Metadata (Cloud Control Plane)",
    description=(
        "Pure Cloud Control Plane metadata endpoint called outbound by the Local Worker. "
        "Receives ONLY sanitized metadata, SHA-256 content hashes, opaque artifact references "
        "(artifact://local/datasets/...), and deterministic profiling summaries. "
        "Zero raw dataset bytes enter or traverse this endpoint."
    ),
)
def register_dataset_metadata(
    registration: DatasetMetadataRegistrationRequest,
    db: Session = Depends(get_db),
) -> DatasetIngestResponse:
    """Register sanitized dataset metadata emitted outbound by the Local Data Processing Plane."""
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
    """List registered datasets with pagination."""
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

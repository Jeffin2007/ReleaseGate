"""
Inspection Runs and Findings coordination REST endpoints for the Cloud Control Plane API.
Provides endpoints for recording inspection runs, retrieving audit summaries,
and querying granular privacy and quality findings.
Enforces multi-tenant organization boundary isolation.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.inspection import (
    FindingResponse,
    InspectionRunCreate,
    InspectionRunResponse,
)
from app.services.inspection_service import (
    CrossOrganizationAccessError,
    InspectionRunNotFoundError,
    InspectionService,
    InspectionServiceError,
)

router = APIRouter(prefix="/inspections", tags=["Inspection & Release Governance"])
inspection_service = InspectionService()


def _resolve_org_id(
    query_org_id: Optional[uuid.UUID] = None,
    header_org_id: Optional[str] = None,
) -> Optional[uuid.UUID]:
    """Helper to extract organization ID from query param or header."""
    if query_org_id:
        return query_org_id
    if header_org_id:
        try:
            return uuid.UUID(header_org_id)
        except ValueError:
            pass
    return None


@router.post(
    "/record",
    response_model=InspectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Completed Inspection Run",
    description=(
        "Pure Cloud Control Plane endpoint called outbound by the Local Worker. "
        "Receives sanitized inspection run summaries, risk scores, and granular findings. "
        "Zero raw dataset bytes or sensitive values are accepted."
    ),
)
def record_inspection_run(
    run_in: InspectionRunCreate,
    organization_id: Optional[uuid.UUID] = Query(None),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
) -> InspectionRunResponse:
    """Record a persistent inspection run and its associated findings."""
    org_id = _resolve_org_id(organization_id, x_organization_id)
    try:
        return inspection_service.record_inspection_run(
            org_id=org_id,
            run_in=run_in,
            db=db,
        )
    except CrossOrganizationAccessError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except InspectionServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get(
    "/{inspection_id}",
    response_model=InspectionRunResponse,
    summary="Get Inspection Run Details",
    description="Fetch a persistent inspection run along with all its granular findings.",
)
def get_inspection_run(
    inspection_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = Query(None),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
) -> InspectionRunResponse:
    """Fetch inspection run by UUID, scoped by organization."""
    org_id = _resolve_org_id(organization_id, x_organization_id)
    try:
        return inspection_service.get_inspection_run(
            org_id=org_id,
            run_id=inspection_id,
            db=db,
        )
    except InspectionRunNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.get(
    "/dataset/{dataset_id}",
    response_model=List[InspectionRunResponse],
    summary="List Inspection Runs for Dataset",
    description="Retrieve all historical inspection runs for a dataset, optionally filtered by version.",
)
def list_inspection_runs_for_dataset(
    dataset_id: uuid.UUID,
    version_id: Optional[uuid.UUID] = Query(None),
    organization_id: Optional[uuid.UUID] = Query(None),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
) -> List[InspectionRunResponse]:
    """List inspection runs for a dataset."""
    org_id = _resolve_org_id(organization_id, x_organization_id)
    return inspection_service.list_inspection_runs_for_dataset(
        org_id=org_id,
        dataset_id=dataset_id,
        db=db,
        version_id=version_id,
    )


@router.get(
    "/versions/{version_id}/findings",
    response_model=List[FindingResponse],
    summary="List Findings for Dataset Version",
    description="Retrieve privacy and quality findings linked to an immutable dataset version.",
)
def list_findings_for_version(
    version_id: uuid.UUID,
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    finding_type: Optional[str] = Query(None, description="Filter by type: PII, QUALITY, POLICY"),
    organization_id: Optional[uuid.UUID] = Query(None),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    db: Session = Depends(get_db),
) -> List[FindingResponse]:
    """List findings for a dataset version."""
    org_id = _resolve_org_id(organization_id, x_organization_id)
    return inspection_service.list_findings_for_version(
        org_id=org_id,
        version_id=version_id,
        db=db,
        severity=severity,
        finding_type=finding_type,
    )

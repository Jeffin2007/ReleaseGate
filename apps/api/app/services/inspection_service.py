"""
Inspection Runs and Findings Service Layer.
Persists inspection runs, risk metrics, and findings, binding them to immutable dataset versions.
Strictly enforces organization-level data isolation.
"""

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.dataset import Dataset, DatasetVersion
from app.db.models.inspection import Finding, InspectionRun, InspectionStatus
from app.schemas.inspection import (
    FindingCreate,
    FindingResponse,
    InspectionRunCreate,
    InspectionRunResponse,
)


class InspectionServiceError(Exception):
    """Base exception for inspection operations."""
    pass


class InspectionRunNotFoundError(InspectionServiceError):
    """Raised when an inspection run does not exist."""
    pass


class CrossOrganizationAccessError(InspectionServiceError):
    """Raised when an entity belongs to a different organization."""
    pass


class InspectionService:
    """
    Manages persistence and retrieval of inspection runs and findings.
    Enforces that queries are strictly bounded by organization_id.
    """

    def record_inspection_run(
        self,
        org_id: uuid.UUID,
        run_in: InspectionRunCreate,
        db: Session,
    ) -> InspectionRunResponse:
        """
        Record a new inspection run and its associated findings.
        Enforces that dataset and dataset version belong to the specified organization.
        """
        dataset = db.scalar(select(Dataset).where(Dataset.id == run_in.dataset_id))
        if not dataset:
            raise InspectionServiceError(f"Dataset '{run_in.dataset_id}' not found.")

        # If dataset has an organization, verify it matches
        if dataset.organization_id is not None and dataset.organization_id != org_id:
            raise CrossOrganizationAccessError(
                f"Dataset '{dataset.id}' belongs to organization '{dataset.organization_id}', "
                f"not '{org_id}'."
            )

        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == run_in.dataset_version_id,
                DatasetVersion.dataset_id == dataset.id,
            )
        )
        if not version:
            raise InspectionServiceError(
                f"DatasetVersion '{run_in.dataset_version_id}' does not belong to dataset '{dataset.id}'."
            )

        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        inspection_run = InspectionRun(
            id=run_id,
            organization_id=org_id,
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            inspection_type=run_in.inspection_type.value,
            status=run_in.status.value,
            risk_score=run_in.risk_score,
            risk_band=run_in.risk_band,
            policy_version=run_in.policy_version,
            is_release_eligible=run_in.is_release_eligible,
            summary_report=run_in.summary_report,
            started_at=now,
            completed_at=now if run_in.status == InspectionStatus.COMPLETED else None,
        )
        db.add(inspection_run)
        db.flush()

        # Add associated findings
        created_findings: List[Finding] = []
        for finding_in in run_in.findings:
            finding = Finding(
                id=uuid.uuid4(),
                organization_id=org_id,
                inspection_run_id=inspection_run.id,
                dataset_version_id=version.id,
                finding_type=finding_in.finding_type.value,
                category=finding_in.category,
                column_name=finding_in.column_name,
                severity=finding_in.severity,
                occurrence_count=finding_in.occurrence_count,
                confidence_score=finding_in.confidence_score,
                message=finding_in.message,
                evidence_ref=finding_in.evidence_ref,
                created_at=now,
            )
            db.add(finding)
            created_findings.append(finding)

        db.commit()
        db.refresh(inspection_run)

        return InspectionRunResponse(
            id=inspection_run.id,
            organization_id=inspection_run.organization_id,
            dataset_id=inspection_run.dataset_id,
            dataset_version_id=inspection_run.dataset_version_id,
            inspection_type=inspection_run.inspection_type,
            status=inspection_run.status,
            risk_score=inspection_run.risk_score,
            risk_band=inspection_run.risk_band,
            policy_version=inspection_run.policy_version,
            is_release_eligible=inspection_run.is_release_eligible,
            summary_report=inspection_run.summary_report,
            started_at=inspection_run.started_at,
            completed_at=inspection_run.completed_at,
            findings_count=len(created_findings),
            findings=[FindingResponse.model_validate(f) for f in created_findings],
        )

    def get_inspection_run(
        self,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        db: Session,
    ) -> InspectionRunResponse:
        """
        Fetch inspection run by ID, strictly verifying organization ownership.
        """
        run = db.scalar(
            select(InspectionRun).where(
                InspectionRun.id == run_id,
                InspectionRun.organization_id == org_id,
            )
        )
        if not run:
            raise InspectionRunNotFoundError(
                f"InspectionRun '{run_id}' not found for organization '{org_id}'."
            )

        findings = db.scalars(
            select(Finding)
            .where(
                Finding.inspection_run_id == run.id,
                Finding.organization_id == org_id,
            )
            .order_by(desc(Finding.created_at))
        ).all()

        return InspectionRunResponse(
            id=run.id,
            organization_id=run.organization_id,
            dataset_id=run.dataset_id,
            dataset_version_id=run.dataset_version_id,
            inspection_type=run.inspection_type,
            status=run.status,
            risk_score=run.risk_score,
            risk_band=run.risk_band,
            policy_version=run.policy_version,
            is_release_eligible=run.is_release_eligible,
            summary_report=run.summary_report,
            started_at=run.started_at,
            completed_at=run.completed_at,
            findings_count=len(findings),
            findings=[FindingResponse.model_validate(f) for f in findings],
        )

    def list_inspection_runs_for_dataset(
        self,
        org_id: uuid.UUID,
        dataset_id: uuid.UUID,
        db: Session,
        version_id: Optional[uuid.UUID] = None,
    ) -> List[InspectionRunResponse]:
        """List all inspection runs for a dataset within an organization."""
        query = select(InspectionRun).where(
            InspectionRun.organization_id == org_id,
            InspectionRun.dataset_id == dataset_id,
        )
        if version_id:
            query = query.where(InspectionRun.dataset_version_id == version_id)

        runs = db.scalars(query.order_by(desc(InspectionRun.started_at))).all()
        return [self.get_inspection_run(org_id, r.id, db) for r in runs]

    def list_findings_for_version(
        self,
        org_id: uuid.UUID,
        version_id: uuid.UUID,
        db: Session,
        severity: Optional[str] = None,
    ) -> List[FindingResponse]:
        """Query findings connected to a dataset version, scoped by organization."""
        query = select(Finding).where(
            Finding.organization_id == org_id,
            Finding.dataset_version_id == version_id,
        )
        if severity:
            query = query.where(Finding.severity == severity.upper())

        findings = db.scalars(query.order_by(desc(Finding.created_at))).all()
        return [FindingResponse.model_validate(f) for f in findings]

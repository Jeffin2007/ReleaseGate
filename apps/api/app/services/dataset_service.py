"""
Dataset Metadata Coordination Service for the Cloud Control Plane.
Strictly adheres to the ReleaseGate Hybrid Architecture Baseline v1.0:
- The Cloud Control Plane receives ONLY sanitized metadata, SHA-256 content hashes,
  opaque artifact references (artifact://local/datasets/...), and profiling summaries.
- Raw dataset files, validation, hashing, profiling, and storage execute exclusively
  inside the Local Data Processing Plane (local-worker).
"""

import uuid
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import (
    DatasetIngestResponse,
    DatasetMetadataRegistrationRequest,
    DatasetProfileSchema,
    DatasetResponse,
    DatasetVersionResponse,
)
from local_worker.secure_storage import LocalDatasetStorage

logger = get_logger("releasegate.services.dataset")


class DatasetServiceError(Exception):
    """Base exception for dataset service operations."""
    pass


class DatasetNotFoundError(DatasetServiceError):
    """Raised when a requested dataset container is not found."""
    pass


class DatasetVersionNotFoundError(DatasetServiceError):
    """Raised when a requested dataset version is not found."""
    pass


class DatasetService:
    """
    Cloud Control Plane Metadata Coordination Service.
    Persists sanitized dataset metadata, content hashes, and profiling summaries in PostgreSQL.
    Contains ZERO raw dataset file ingestion logic.
    """

    def register_dataset_metadata(
        self,
        registration: DatasetMetadataRegistrationRequest,
        db: Session,
        require_existing_dataset: bool = False,
        organization_id: Optional[uuid.UUID] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> DatasetIngestResponse:
        """
        Pure Cloud Control Plane metadata registration handler.
        Accepts ONLY sanitized metadata, SHA-256 hash, opaque artifact ref, and profiling summary
        emitted outbound by the Local Data Processing Plane. Zero raw dataset bytes enter this method.
        """
        dataset: Optional[Dataset] = None
        if registration.dataset_id:
            dataset = db.scalar(select(Dataset).where(Dataset.id == registration.dataset_id))
            if not dataset and require_existing_dataset:
                raise DatasetNotFoundError(
                    f"Dataset with ID {registration.dataset_id} does not exist."
                )

        if dataset:
            latest_version_num = db.scalar(
                select(DatasetVersion.version_number)
                .where(DatasetVersion.dataset_id == dataset.id)
                .order_by(desc(DatasetVersion.version_number))
                .limit(1)
            ) or 0
            version_number = latest_version_num + 1
        else:
            target_id = registration.dataset_id or uuid.uuid4()
            dataset = Dataset(
                id=target_id,
                name=registration.dataset_name.strip(),
                description=registration.description,
                organization_id=organization_id,
                created_by=created_by,
            )
            db.add(dataset)
            db.flush()
            version_number = 1

        # Ensure the opaque artifact reference matches the sequential version number
        expected_ref = LocalDatasetStorage.build_artifact_ref(
            dataset_id=dataset.id,
            version_number=version_number,
            content_hash=registration.content_hash.lower(),
            ext=registration.file_format,
        )
        effective_ref = (
            registration.local_artifact_ref
            if f"/v{version_number}/" in registration.local_artifact_ref
            else expected_ref
        )

        version_id = uuid.uuid4()
        dataset_version = DatasetVersion(
            id=version_id,
            dataset_id=dataset.id,
            version_number=version_number,
            content_hash=registration.content_hash.lower(),
            file_format=registration.file_format.lower(),
            file_size=registration.file_size,
            local_artifact_ref=effective_ref,
            dataset_metadata=registration.profile.model_dump(),
        )
        db.add(dataset_version)

        dataset.current_version_id = version_id
        db.commit()
        db.refresh(dataset)
        db.refresh(dataset_version)

        logger.info(
            f"Registered sanitized dataset metadata '{dataset.name}' (ID: {dataset.id}) "
            f"version v{version_number} [SHA256: {dataset_version.content_hash}] "
            f"[Ref: {dataset_version.local_artifact_ref}]"
        )

        return DatasetIngestResponse(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            version_id=dataset_version.id,
            version_number=dataset_version.version_number,
            content_hash=dataset_version.content_hash,
            local_artifact_ref=dataset_version.local_artifact_ref,
            profile=registration.profile,
            message="Dataset metadata registered successfully in Cloud Control Plane.",
        )

    def get_dataset(self, dataset_id: uuid.UUID, db: Session) -> DatasetResponse:
        """Fetch dataset by ID along with its version history."""
        dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
        if not dataset:
            raise DatasetNotFoundError(f"Dataset with ID {dataset_id} was not found.")

        versions = db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number)
        ).all()

        version_responses = [
            DatasetVersionResponse(
                id=v.id,
                dataset_id=v.dataset_id,
                version_number=v.version_number,
                content_hash=v.content_hash,
                file_format=v.file_format,
                file_size=v.file_size,
                local_artifact_ref=v.local_artifact_ref,
                metadata=DatasetProfileSchema.model_validate(v.dataset_metadata),
                created_at=v.created_at,
            )
            for v in versions
        ]

        return DatasetResponse(
            id=dataset.id,
            organization_id=dataset.organization_id,
            name=dataset.name,
            description=dataset.description,
            current_version_id=dataset.current_version_id,
            created_at=dataset.created_at,
            versions=version_responses,
        )

    def list_datasets(self, db: Session, limit: int = 100, skip: int = 0) -> List[DatasetResponse]:
        """List datasets with pagination."""
        datasets = db.scalars(
            select(Dataset)
            .order_by(desc(Dataset.created_at))
            .offset(skip)
            .limit(limit)
        ).all()

        return [self.get_dataset(d.id, db) for d in datasets]

    def get_dataset_version(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        db: Session,
    ) -> DatasetVersionResponse:
        """Fetch a specific immutable version of a dataset."""
        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.version_number == version_number,
            )
        )
        if not version:
            raise DatasetVersionNotFoundError(
                f"Version {version_number} for dataset {dataset_id} was not found."
            )

        return DatasetVersionResponse(
            id=version.id,
            dataset_id=version.dataset_id,
            version_number=version.version_number,
            content_hash=version.content_hash,
            file_format=version.file_format,
            file_size=version.file_size,
            local_artifact_ref=version.local_artifact_ref,
            metadata=DatasetProfileSchema.model_validate(version.dataset_metadata),
            created_at=version.created_at,
        )

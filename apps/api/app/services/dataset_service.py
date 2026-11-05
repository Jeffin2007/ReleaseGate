"""
Dataset ingestion, profiling, and storage coordination service.
Orchestrates file validation, cryptographic hashing, deterministic Pandas profiling,
secure local filesystem persistence, and SQLAlchemy metadata recording.
"""

import uuid
from typing import List, Optional, Tuple
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import (
    DatasetIngestResponse,
    DatasetProfileSchema,
    DatasetResponse,
    DatasetVersionResponse,
)
from engines.dataset_profiler import DatasetProfiler, ProfilingResult
from local_worker.secure_storage import LocalDatasetStorage
from local_worker.validator import validate_dataset_upload

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
    High-level business service for local dataset ingestion.
    Enforces that raw dataset files remain strictly in local storage
    and exposes only secure artifact references.
    """

    def __init__(self, storage: Optional[LocalDatasetStorage] = None):
        self.storage = storage or LocalDatasetStorage()

    def ingest_dataset(
        self,
        filename: str,
        content: bytes,
        db: Session,
        dataset_name: Optional[str] = None,
        description: Optional[str] = None,
        dataset_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> DatasetIngestResponse:
        """
        Validate, hash, profile, and persist a new dataset or new dataset version.

        1. Validates format (CSV, XLSX, JSON) and security signatures.
        2. Profiles dataset deterministically using Pandas.
        3. Persists file to local secure storage outside web directories.
        4. Creates or updates Dataset parent record in database.
        5. Inserts immutable DatasetVersion record with SHA-256 hash and secure artifact ref.
        """
        # Step 1: Validate file format and security guards
        file_format = validate_dataset_upload(filename=filename, content=content)

        # Step 2: Deterministic profiling via Pandas
        profile_result: ProfilingResult = DatasetProfiler.profile(
            content=content,
            file_format=file_format,
        )

        # Step 3: Determine dataset container
        if dataset_id:
            # Updating an existing dataset with a new version
            dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
            if not dataset:
                raise DatasetNotFoundError(f"Dataset with ID {dataset_id} does not exist.")

            # Calculate next sequential version number
            latest_version_num = db.scalar(
                select(DatasetVersion.version_number)
                .where(DatasetVersion.dataset_id == dataset.id)
                .order_by(desc(DatasetVersion.version_number))
                .limit(1)
            ) or 0
            version_number = latest_version_num + 1
        else:
            # Create new dataset entity
            dataset_id = uuid.uuid4()
            effective_name = dataset_name.strip() if dataset_name and dataset_name.strip() else filename
            dataset = Dataset(
                id=dataset_id,
                name=effective_name,
                description=description,
                organization_id=organization_id,
                created_by=created_by,
            )
            db.add(dataset)
            db.flush()  # Flush so dataset.id is available
            version_number = 1

        # Step 4: Persist raw content to local isolated storage (read-only)
        artifact_ref, file_size, content_hash = self.storage.store_dataset(
            dataset_id=dataset.id,
            version_number=version_number,
            content=content,
            ext=file_format,
        )

        # Step 5: Insert immutable DatasetVersion record
        version_id = uuid.uuid4()
        dataset_version = DatasetVersion(
            id=version_id,
            dataset_id=dataset.id,
            version_number=version_number,
            content_hash=content_hash,
            file_format=file_format,
            file_size=file_size,
            local_artifact_ref=artifact_ref,
            dataset_metadata=profile_result.to_dict(),
        )
        db.add(dataset_version)

        # Step 6: Link current_version_id on parent dataset
        dataset.current_version_id = version_id
        db.commit()
        db.refresh(dataset)
        db.refresh(dataset_version)

        logger.info(
            f"Successfully ingested dataset '{dataset.name}' (ID: {dataset.id}) "
            f"version v{version_number} [SHA256: {content_hash}] [Ref: {artifact_ref}]"
        )

        profile_schema = DatasetProfileSchema.model_validate(profile_result.to_dict())

        return DatasetIngestResponse(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            version_id=dataset_version.id,
            version_number=dataset_version.version_number,
            content_hash=dataset_version.content_hash,
            local_artifact_ref=dataset_version.local_artifact_ref,
            profile=profile_schema,
            message="Dataset successfully ingested, cryptographically hashed, and profiled locally.",
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

    def get_raw_dataset_bytes(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        db: Session,
    ) -> Tuple[bytes, str, str]:
        """
        Internal worker helper: read raw dataset bytes from local secure storage.
        Verifies SHA-256 digest integrity during read.
        Returns: (content_bytes, file_format, content_hash)
        """
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

        content = self.storage.read_dataset(version.local_artifact_ref)
        return content, version.file_format, version.content_hash

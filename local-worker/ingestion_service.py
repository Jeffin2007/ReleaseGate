"""
Local Worker Ingestion & Processing Service.
Executes exclusively inside the Local Processing Plane (Environment B).
Owns raw dataset validation, bounded-memory streaming, SHA-256 hashing,
deterministic Pandas profiling, and local encrypted/read-only file storage.
Emits ONLY sanitized metadata payloads for outbound registration with the Cloud Control Plane.
"""

from dataclasses import asdict, dataclass
import io
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Union
import uuid

from engines.dataset_profiler import DatasetProfiler, ProfilingResult

try:
    from local_worker.secure_storage import LocalDatasetStorage
    from local_worker.validator import (
        DEFAULT_MAX_FILE_SIZE_BYTES,
        validate_dataset_stream,
        validate_dataset_upload,
    )
except ImportError:
    from .secure_storage import LocalDatasetStorage
    from .validator import (
        DEFAULT_MAX_FILE_SIZE_BYTES,
        validate_dataset_stream,
        validate_dataset_upload,
    )


@dataclass(frozen=True)
class SanitizedIngestionPayload:
    """
    Sanitized metadata envelope produced by the Local Worker for outbound
    registration with the Cloud Control Plane.
    Contains ZERO raw dataset bytes and ZERO absolute filesystem paths.
    """
    dataset_id: uuid.UUID
    dataset_name: str
    description: Optional[str]
    version_number: int
    content_hash: str
    file_format: str
    file_size: int
    local_artifact_ref: str
    profile: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LocalIngestionWorker:
    """
    Local Data Plane worker responsible for ingesting raw datasets locally.
    Ensures raw dataset bytes never cross into the Cloud Control Plane.
    """

    def __init__(
        self,
        storage: Optional[LocalDatasetStorage] = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ):
        self.storage = storage or LocalDatasetStorage()
        self.max_file_size_bytes = max_file_size_bytes

    def process_local_file_or_stream(
        self,
        filename: str,
        source: Union[bytes, BinaryIO, Path],
        dataset_id: Optional[uuid.UUID] = None,
        version_number: int = 1,
        dataset_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> SanitizedIngestionPayload:
        """
        Execute local ingestion pipeline on a file path, binary stream, or byte buffer:
        1. Validates format, magic bytes, and size limits with bounded memory.
        2. Streams content to local isolated storage while calculating SHA-256 hash.
        3. Runs deterministic Pandas profiling locally.
        4. Returns a SanitizedIngestionPayload containing only metadata, hash, and opaque ref.
        """
        target_dataset_id = dataset_id or uuid.uuid4()
        effective_name = (
            dataset_name.strip()
            if dataset_name and dataset_name.strip()
            else Path(filename).name
        )

        # Convert source to a seekable binary stream for bounded chunk processing
        if isinstance(source, bytes):
            file_format = validate_dataset_upload(
                filename=filename,
                content=source,
                max_size_bytes=self.max_file_size_bytes,
            )
            artifact_ref, file_size, content_hash = self.storage.store_dataset(
                dataset_id=target_dataset_id,
                version_number=version_number,
                content=source,
                ext=file_format,
            )
            raw_bytes_for_profiling = source
        elif isinstance(source, Path):
            with open(source, "rb") as f:
                file_format, _ = validate_dataset_stream(
                    filename=filename,
                    stream=f,
                    max_size_bytes=self.max_file_size_bytes,
                )
                artifact_ref, file_size, content_hash = self.storage.store_dataset_stream(
                    dataset_id=target_dataset_id,
                    version_number=version_number,
                    stream=f,
                    ext=file_format,
                    max_size_bytes=self.max_file_size_bytes,
                )
            raw_bytes_for_profiling = self.storage.read_dataset(artifact_ref)
        else:
            # BinaryIO stream
            file_format, _ = validate_dataset_stream(
                filename=filename,
                stream=source,
                max_size_bytes=self.max_file_size_bytes,
            )
            artifact_ref, file_size, content_hash = self.storage.store_dataset_stream(
                dataset_id=target_dataset_id,
                version_number=version_number,
                stream=source,
                ext=file_format,
                max_size_bytes=self.max_file_size_bytes,
            )
            raw_bytes_for_profiling = self.storage.read_dataset(artifact_ref)

        # Run deterministic Pandas profiling locally inside the Data Plane
        try:
            profile_result: ProfilingResult = DatasetProfiler.profile(
                content=raw_bytes_for_profiling,
                file_format=file_format,
            )
        except Exception:
            # Clean up stored artifact if profiling fails on malformed tabular structure
            self.storage.delete_artifact_for_retention(artifact_ref)
            raise

        return SanitizedIngestionPayload(
            dataset_id=target_dataset_id,
            dataset_name=effective_name,
            description=description,
            version_number=version_number,
            content_hash=content_hash,
            file_format=file_format,
            file_size=file_size,
            local_artifact_ref=artifact_ref,
            profile=profile_result.to_dict(),
        )

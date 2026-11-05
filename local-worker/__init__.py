"""
Local Worker package for dataset processing, secure storage, and outbound cloud communication.
"""

from local_worker.cloud_client import CloudClientError, CloudControlPlaneClient
from local_worker.hashing import (
    calculate_sha256_bytes,
    calculate_sha256_file,
    calculate_sha256_stream,
)
from local_worker.ingestion_service import LocalIngestionWorker, SanitizedIngestionPayload
from local_worker.secure_storage import (
    LocalDatasetStorage,
    SecureStorageError,
    StorageIntegrityError,
)
from local_worker.validator import (
    DatasetEmptyError,
    DatasetValidationError,
    validate_dataset_stream,
    validate_dataset_upload,
)

__all__ = [
    "calculate_sha256_bytes",
    "calculate_sha256_file",
    "calculate_sha256_stream",
    "LocalDatasetStorage",
    "SecureStorageError",
    "StorageIntegrityError",
    "DatasetValidationError",
    "DatasetEmptyError",
    "validate_dataset_upload",
    "validate_dataset_stream",
    "LocalIngestionWorker",
    "SanitizedIngestionPayload",
    "CloudControlPlaneClient",
    "CloudClientError",
]

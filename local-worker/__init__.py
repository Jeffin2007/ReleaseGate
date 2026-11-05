"""
Local worker package for dataset processing and secure storage.
"""

from local_worker.hashing import (
    calculate_sha256_bytes,
    calculate_sha256_file,
    calculate_sha256_stream,
)
from local_worker.secure_storage import (
    LocalDatasetStorage,
    SecureStorageError,
    StorageIntegrityError,
)
from local_worker.validator import (
    DatasetEmptyError,
    DatasetValidationError,
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
]

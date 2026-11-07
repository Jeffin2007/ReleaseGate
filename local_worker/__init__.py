"""
Python package bridge for the hyphenated `local-worker` directory.
Allows `import local_worker` and `from local_worker.xyz import ...` to resolve
directly to `/local-worker` across all environments without relying on OS symlinks.
"""

from pathlib import Path

_hyphenated_dir = str((Path(__file__).resolve().parent.parent / "local-worker").resolve())
if _hyphenated_dir not in __path__:
    __path__.insert(0, _hyphenated_dir)

from local_worker.cloud_client import CloudClientError, CloudControlPlaneClient  # noqa: E402
from local_worker.hashing import (  # noqa: E402
    calculate_sha256_bytes,
    calculate_sha256_file,
    calculate_sha256_stream,
)
from local_worker.ingestion_service import (  # noqa: E402
    LocalIngestionWorker,
    SanitizedIngestionPayload,
)
from local_worker.secure_storage import (  # noqa: E402
    LocalDatasetStorage,
    SecureStorageError,
    StorageIntegrityError,
)
from local_worker.inspection_pipeline import (  # noqa: E402
    AuditableInspectionResult,
    DatasetInspectionWorkflow,
    InspectionWorkflowError,
)
from local_worker.validator import (  # noqa: E402
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
    "DatasetInspectionWorkflow",
    "AuditableInspectionResult",
    "InspectionWorkflowError",
]

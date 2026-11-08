"""
Local Worker package for dataset processing, secure storage, and outbound cloud communication.

Exports are resolved lazily so importing a lightweight module (for example
``local_worker.secure_storage`` from the MCP plane) does not import the API
plane's SQLAlchemy models through the inspection pipeline.
"""

from importlib import import_module
from typing import Dict, Tuple

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "calculate_sha256_bytes": ("hashing", "calculate_sha256_bytes"),
    "calculate_sha256_file": ("hashing", "calculate_sha256_file"),
    "calculate_sha256_stream": ("hashing", "calculate_sha256_stream"),
    "LocalDatasetStorage": ("secure_storage", "LocalDatasetStorage"),
    "SecureStorageError": ("secure_storage", "SecureStorageError"),
    "StorageIntegrityError": ("secure_storage", "StorageIntegrityError"),
    "DatasetValidationError": ("validator", "DatasetValidationError"),
    "DatasetEmptyError": ("validator", "DatasetEmptyError"),
    "validate_dataset_upload": ("validator", "validate_dataset_upload"),
    "validate_dataset_stream": ("validator", "validate_dataset_stream"),
    "LocalIngestionWorker": ("ingestion_service", "LocalIngestionWorker"),
    "SanitizedIngestionPayload": ("ingestion_service", "SanitizedIngestionPayload"),
    "CloudControlPlaneClient": ("cloud_client", "CloudControlPlaneClient"),
    "CloudClientError": ("cloud_client", "CloudClientError"),
    "DatasetInspectionWorkflow": ("inspection_pipeline", "DatasetInspectionWorkflow"),
    "AuditableInspectionResult": ("inspection_pipeline", "AuditableInspectionResult"),
    "InspectionWorkflowError": ("inspection_pipeline", "InspectionWorkflowError"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'local_worker' has no attribute {name!r}") from exc
    module = import_module(f"local_worker.{module_name}")
    value = getattr(module, attribute)
    globals()[name] = value
    return value

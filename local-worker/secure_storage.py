"""
Secure local dataset storage manager.
Ensures raw datasets remain strictly isolated in local on-prem storage
and generates opaque, non-enumerable artifact references without leaking absolute filesystem paths.
"""

import os
import stat
from pathlib import Path
from typing import Optional, Tuple
from uuid import UUID

try:
    from local_worker.hashing import calculate_sha256_bytes, calculate_sha256_file
except ImportError:
    try:
        from .hashing import calculate_sha256_bytes, calculate_sha256_file
    except ImportError:
        from hashing import calculate_sha256_bytes, calculate_sha256_file

# Default local storage location: isolated from web/frontend public folders
DEFAULT_LOCAL_STORAGE_DIR = Path("storage/raw_datasets").resolve()


class SecureStorageError(Exception):
    """Base exception for secure storage operations."""
    pass


class StorageIntegrityError(SecureStorageError):
    """Raised when file content does not match expected cryptographic hash."""
    pass


class LocalDatasetStorage:
    """
    Manages local dataset artifact storage with read-only permission enforcement
    and opaque reference resolution.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir or DEFAULT_LOCAL_STORAGE_DIR).resolve()
        self._ensure_storage_directory()

    def _ensure_storage_directory(self) -> None:
        """Create secure storage root with restricted directory permissions (0o700)."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.base_dir, stat.S_IRWXU)  # rwx------ (owner only)
        except Exception:
            pass  # Fallback if filesystem does not support POSIX permission chmod

    @staticmethod
    def build_artifact_ref(dataset_id: UUID, version_number: int, content_hash: str, ext: str) -> str:
        """
        Generate opaque, non-enumerable uniform artifact reference.
        Example: artifact://local/datasets/a1b2c3d4-e5f6.../v1/7f83b165...csv
        Never reveals the local host machine's absolute filesystem directory tree.
        """
        clean_ext = ext.lstrip(".").lower()
        return f"artifact://local/datasets/{dataset_id}/v{version_number}/{content_hash}.{clean_ext}"

    def get_internal_path(self, dataset_id: UUID, version_number: int, content_hash: str, ext: str) -> Path:
        """
        Calculate internal storage path for an artifact.
        Directory structure: <base_dir>/<dataset_id>/v<version_number>/<content_hash>.<ext>
        """
        clean_ext = ext.lstrip(".").lower()
        version_dir = self.base_dir / str(dataset_id) / f"v{version_number}"
        return version_dir / f"{content_hash}.{clean_ext}"

    def resolve_ref_to_internal_path(self, artifact_ref: str) -> Path:
        """
        Resolve an opaque artifact_ref back to the internal local Path.
        Validates path traversal prevention.
        """
        if not artifact_ref.startswith("artifact://local/datasets/"):
            raise SecureStorageError(f"Invalid artifact reference scheme: {artifact_ref}")

        parts = artifact_ref.replace("artifact://local/datasets/", "").split("/")
        if len(parts) != 3:
            raise SecureStorageError(f"Malformed artifact reference format: {artifact_ref}")

        dataset_id_str, version_str, filename = parts
        try:
            dataset_id = UUID(dataset_id_str)
        except ValueError:
            raise SecureStorageError(f"Invalid UUID in artifact reference: {dataset_id_str}")

        internal_path = (self.base_dir / str(dataset_id) / version_str / filename).resolve()

        # Path traversal guard: must be strictly inside self.base_dir
        if not str(internal_path).startswith(str(self.base_dir)):
            raise SecureStorageError("Path traversal attempt detected in artifact reference")

        return internal_path

    def store_dataset(
        self,
        dataset_id: UUID,
        version_number: int,
        content: bytes,
        ext: str,
        expected_hash: Optional[str] = None,
    ) -> Tuple[str, int, str]:
        """
        Store raw dataset content locally.
        Computes SHA-256 digest, enforces read-only file permissions,
        and returns (artifact_ref, byte_size, content_hash).
        """
        content_hash = calculate_sha256_bytes(content)
        if expected_hash and content_hash.lower() != expected_hash.lower():
            raise StorageIntegrityError(
                f"Calculated content hash ({content_hash}) does not match expected hash ({expected_hash})"
            )

        internal_path = self.get_internal_path(dataset_id, version_number, content_hash, ext)
        internal_path.parent.mkdir(parents=True, exist_ok=True)

        if internal_path.exists():
            # Already exists with matching hash; verify integrity
            existing_hash = calculate_sha256_file(internal_path)
            if existing_hash != content_hash:
                raise StorageIntegrityError(
                    f"Existing file hash mismatch: stored={existing_hash}, new={content_hash}"
                )
        else:
            # Write raw bytes
            with open(internal_path, "wb") as f:
                f.write(content)

            # Enforce read-only file permissions (0o400 - read by owner only, cannot be overwritten)
            try:
                os.chmod(internal_path, stat.S_IRUSR)
            except Exception:
                pass

        artifact_ref = self.build_artifact_ref(dataset_id, version_number, content_hash, ext)
        byte_size = len(content)

        return artifact_ref, byte_size, content_hash

    def read_dataset(self, artifact_ref: str) -> bytes:
        """
        Retrieve raw dataset bytes from local storage and verify SHA-256 integrity.
        """
        internal_path = self.resolve_ref_to_internal_path(artifact_ref)
        if not internal_path.is_file():
            raise FileNotFoundError(f"Stored dataset artifact not found for ref: {artifact_ref}")

        with open(internal_path, "rb") as f:
            content = f.read()

        # Verify integrity against hash in filename
        expected_hash = internal_path.stem
        actual_hash = calculate_sha256_bytes(content)
        if actual_hash != expected_hash:
            raise StorageIntegrityError(
                f"Data corruption detected: file content hash {actual_hash} != {expected_hash}"
            )

        return content

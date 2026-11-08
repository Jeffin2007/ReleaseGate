"""
Secure local dataset storage manager.
Ensures raw datasets remain strictly isolated in local on-prem storage
and generates opaque, non-enumerable artifact references without leaking absolute filesystem paths.
Supports bounded-memory streaming writes, read-only immutable permissions, and controlled retention cleanup.
"""

import hashlib
import os
import shutil
import stat
from pathlib import Path
from typing import BinaryIO, Optional, Tuple
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
    Manages local dataset artifact storage with read-only permission enforcement,
    bounded-memory streaming persistence, opaque reference resolution,
    and controlled retention deletion.
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
        Store raw dataset content locally from bytes.
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
        try:
            os.chmod(internal_path.parent, stat.S_IRWXU)
        except Exception:
            pass

        if internal_path.exists():
            existing_hash = calculate_sha256_file(internal_path)
            if existing_hash != content_hash:
                raise StorageIntegrityError(
                    f"Existing file hash mismatch: stored={existing_hash}, new={content_hash}"
                )
        else:
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

    def store_dataset_stream(
        self,
        dataset_id: UUID,
        version_number: int,
        stream: BinaryIO,
        ext: str,
        max_size_bytes: int = 100 * 1024 * 1024,
        chunk_size: int = 65536,
        expected_hash: Optional[str] = None,
    ) -> Tuple[str, int, str]:
        """
        Store raw dataset from a binary stream with strictly bounded memory usage.
        Streams chunks to a temporary staging file while computing SHA-256 hash on the fly,
        then atomically moves the verified file to its immutable content-addressed path.
        """
        if hasattr(stream, "seek"):
            stream.seek(0)

        version_dir = self.base_dir / str(dataset_id) / f"v{version_number}"
        version_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(version_dir, stat.S_IRWXU)
        except Exception:
            pass

        temp_staging_path = version_dir / f".staging_{dataset_id}_{version_number}.tmp"
        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(temp_staging_path, "wb") as out_f:
                while chunk := stream.read(chunk_size):
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        raise SecureStorageError(
                            f"Stream size exceeds maximum allowed limit of {max_size_bytes} bytes"
                        )
                    hasher.update(chunk)
                    out_f.write(chunk)

            if total_bytes == 0:
                raise SecureStorageError("Cannot store empty dataset stream (0 bytes)")

            content_hash = hasher.hexdigest().lower()
            if expected_hash and content_hash != expected_hash.lower():
                raise StorageIntegrityError(
                    f"Stream content hash ({content_hash}) does not match expected hash ({expected_hash})"
                )

            final_path = self.get_internal_path(dataset_id, version_number, content_hash, ext)
            if final_path.exists():
                existing_hash = calculate_sha256_file(final_path)
                if existing_hash != content_hash:
                    raise StorageIntegrityError("Existing artifact hash mismatch")
                temp_staging_path.unlink(missing_ok=True)
            else:
                temp_staging_path.replace(final_path)
                try:
                    os.chmod(final_path, stat.S_IRUSR)
                except Exception:
                    pass

            artifact_ref = self.build_artifact_ref(dataset_id, version_number, content_hash, ext)
            return artifact_ref, total_bytes, content_hash

        except Exception:
            if temp_staging_path.exists():
                try:
                    os.chmod(temp_staging_path, stat.S_IRUSR | stat.S_IWUSR)
                    temp_staging_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise

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

    def delete_artifact_for_retention(self, artifact_ref: str) -> bool:
        """
        Controlled retention/deletion handler.
        Safely restores write permissions (0o600) on read-only (0o400) artifacts and parent directories
        before unlinking, ensuring storage remains manageable for authorized lifecycle cleanup.
        """
        internal_path = self.resolve_ref_to_internal_path(artifact_ref)
        if not internal_path.exists():
            return False

        try:
            # Restore owner write permission on parent directory and file so unlink succeeds
            if internal_path.parent.exists():
                os.chmod(internal_path.parent, stat.S_IRWXU)
            os.chmod(internal_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

        internal_path.unlink()

        # Clean up empty version directory if no other files remain
        try:
            if internal_path.parent.exists() and not any(internal_path.parent.iterdir()):
                internal_path.parent.rmdir()
        except Exception:
            pass

        return True

    def purge_dataset_directory(self, dataset_id: UUID) -> bool:
        """
        Controlled retention handler to purge all local versions of a dataset.
        Restores write permissions recursively before removing the dataset directory tree.
        """
        dataset_dir = (self.base_dir / str(dataset_id)).resolve()
        if not str(dataset_dir).startswith(str(self.base_dir)) or not dataset_dir.exists():
            return False

        for root, dirs, files in os.walk(dataset_dir):
            for d in dirs:
                try:
                    os.chmod(Path(root) / d, stat.S_IRWXU)
                except Exception:
                    pass
            for f in files:
                try:
                    os.chmod(Path(root) / f, stat.S_IRUSR | stat.S_IWUSR)
                except Exception:
                    pass

        shutil.rmtree(dataset_dir)
        return True

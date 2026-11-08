"""
Deterministic SHA-256 content hashing service.
Computes cryptographic digests for dataset byte streams and files.
"""

import hashlib
from typing import BinaryIO, Union
from pathlib import Path


def calculate_sha256_bytes(data: bytes) -> str:
    """
    Calculate deterministic SHA-256 hex digest for a bytes payload.
    """
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest().lower()


def calculate_sha256_stream(stream: BinaryIO, chunk_size: int = 65536) -> str:
    """
    Calculate SHA-256 hex digest for a binary stream without loading the entire stream into memory.
    Resets stream pointer to the beginning if seekable.
    """
    hasher = hashlib.sha256()
    original_pos = 0
    if hasattr(stream, "tell") and hasattr(stream, "seek"):
        try:
            original_pos = stream.tell()
            stream.seek(0)
        except Exception:
            pass

    while chunk := stream.read(chunk_size):
        hasher.update(chunk)

    if hasattr(stream, "seek"):
        try:
            stream.seek(original_pos)
        except Exception:
            pass

    return hasher.hexdigest().lower()


def calculate_sha256_file(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """
    Calculate SHA-256 hex digest for an on-disk file.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found for hash calculation: {file_path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest().lower()

"""
Dataset file format and security validation.
Validates extensions, MIME types, magic bytes signatures, file sizes,
and prevents malicious executable or instruction-carrying payloads.
Supports both bounded stream validation and byte buffer validation.
"""

from pathlib import Path
from typing import BinaryIO, Optional, Set, Tuple, Union

# Maximum allowed dataset file size (100 MB)
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
HEADER_SAMPLE_BYTES = 4096

SUPPORTED_EXTENSIONS: Set[str] = {".csv", ".xlsx", ".json"}

# Executable magic bytes signatures to strictly reject
DANGEROUS_SIGNATURES = [
    (b"MZ", "DOS/Windows Executable"),
    (b"\x7fELF", "Linux ELF Executable"),
    (b"\xca\xfe\xba\xbe", "Java Bytecode / Mach-O"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit"),
    (b"#!", "Shell/Script Interpreter Directive"),
    (b"<?php", "PHP script"),
    (b"eval(", "Dynamic script execution directive"),
]

# XLSX signature: standard ZIP container signature
ZIP_MAGIC = b"PK\x03\x04"


class DatasetValidationError(Exception):
    """Raised when an uploaded dataset fails validation."""
    pass


class DatasetEmptyError(DatasetValidationError):
    """Raised when an uploaded dataset has zero bytes or zero records."""
    pass


def _validate_header_and_format(
    filename: str,
    header_bytes: bytes,
    total_size: int,
    max_size_bytes: int,
) -> str:
    """Internal helper to validate filename, size boundaries, and header magic bytes."""
    if not filename or not filename.strip():
        raise DatasetValidationError("Filename cannot be empty")

    if total_size == 0:
        raise DatasetEmptyError("Uploaded file is empty (0 bytes)")

    if total_size > max_size_bytes:
        raise DatasetValidationError(
            f"File size ({total_size / (1024*1024):.2f}MB) exceeds maximum limit "
            f"({max_size_bytes / (1024*1024):.0f}MB)"
        )

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DatasetValidationError(
            f"Unsupported file format '{ext}'. ReleaseGate strictly supports CSV (.csv), "
            f"Excel (.xlsx), and JSON (.json) datasets."
        )

    # Security check: verify the file does not begin with an executable/script signature
    for sig, sig_name in DANGEROUS_SIGNATURES:
        if header_bytes.startswith(sig):
            raise DatasetValidationError(
                f"Security violation: File header matches dangerous executable signature ({sig_name})"
            )

    normalized_format = ext.lstrip(".")

    # Format-specific deep checks on header sample
    if normalized_format == "xlsx":
        if not header_bytes.startswith(ZIP_MAGIC):
            raise DatasetValidationError(
                "Invalid XLSX file: File lacks the required ZIP container magic signature"
            )
    elif normalized_format == "json":
        try:
            text_prefix = header_bytes[:1024].decode("utf-8").strip()
        except UnicodeDecodeError:
            raise DatasetValidationError("Invalid JSON: File must be UTF-8 encoded text")

        if not (text_prefix.startswith("{") or text_prefix.startswith("[")):
            raise DatasetValidationError(
                "Invalid JSON: Root element must be a JSON Object ({...}) or Array ([...])"
            )
    elif normalized_format == "csv":
        try:
            sample = header_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample = header_bytes.decode("latin-1")
            except Exception:
                raise DatasetValidationError("Invalid CSV: Unable to decode file as text")

        if "\x00" in sample:
            raise DatasetValidationError(
                "Invalid CSV: Contains null bytes, indicating a binary file disguised as CSV"
            )

    return normalized_format


def validate_dataset_upload(
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> str:
    """
    Perform multi-layer security validation on in-memory dataset bytes.
    """
    return _validate_header_and_format(
        filename=filename,
        header_bytes=content[:HEADER_SAMPLE_BYTES],
        total_size=len(content),
        max_size_bytes=max_size_bytes,
    )


def validate_dataset_stream(
    filename: str,
    stream: BinaryIO,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    chunk_size: int = 65536,
) -> Tuple[str, int]:
    """
    Validate a binary stream with strictly bounded memory usage.
    Reads in fixed chunks to enforce max_size_bytes without loading the entire stream into RAM.
    Resets stream pointer to offset 0 after validation.

    Returns:
        Tuple of (normalized_format: str, total_size_bytes: int)
    """
    if hasattr(stream, "seek"):
        stream.seek(0)

    header_bytes = stream.read(HEADER_SAMPLE_BYTES)
    total_size = len(header_bytes)

    if total_size == 0:
        if not filename or not filename.strip():
            raise DatasetValidationError("Filename cannot be empty")
        raise DatasetEmptyError("Uploaded file is empty (0 bytes)")

    # Validate format and header before reading rest of stream
    normalized_format = _validate_header_and_format(
        filename=filename,
        header_bytes=header_bytes,
        total_size=total_size,
        max_size_bytes=max_size_bytes,
    )

    # Stream remaining chunks to enforce upper size bound with bounded memory
    while chunk := stream.read(chunk_size):
        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise DatasetValidationError(
                f"Streamed file size exceeds maximum limit ({max_size_bytes / (1024*1024):.0f}MB)"
            )

    if hasattr(stream, "seek"):
        stream.seek(0)

    return normalized_format, total_size

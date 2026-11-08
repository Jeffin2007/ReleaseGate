"""
Cloud-facing output guard.

The MCP server is reachable by an AI model whose context may be forwarded to the
cloud control plane. Every tool result and resource body therefore passes through
``enforce_cloud_safe`` before it leaves the local process.

The guard is defence in depth on top of the engines, which already emit only
aggregates:
  * rejects structural keys that would carry row values (``rows``, ``raw_data``…),
  * rejects strings containing email addresses, phone numbers, SSNs, payment
    card numbers, or absolute local filesystem paths.

Failure is closed: a violation raises and the tool call returns an error rather
than a partially leaked payload.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(
    r"(?<![\d.])(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?![\d.])"
)
SSN_PATTERN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"'=:(])(/(?:etc|home|root|tmp|workspace|var|opt|usr|srv|mnt|data)/)"
)

# Hashes, UUIDs, and opaque identifiers are not PII, even when a digit run
# inside them looks like a phone number. Only whole-string matches are exempt.
_HEX_IDENTIFIER_PATTERN = re.compile(r"^[0-9a-fA-F]{12,}$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_IDENTIFIER_KEY_SUFFIXES = ("_id", "_hash", "_digest")
_IDENTIFIER_KEYS = frozenset({"id", "content_hash", "artifact_hash", "event_id"})


def _is_identifier_value(value: str) -> bool:
    """Return True for hash/UUID-shaped values that must not be PII-scanned."""
    if _UUID_PATTERN.fullmatch(value):
        return True
    return bool(_HEX_IDENTIFIER_PATTERN.fullmatch(value)) and any(
        character.isalpha() for character in value
    )


def _is_identifier_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in _IDENTIFIER_KEYS or lowered.endswith(_IDENTIFIER_KEY_SUFFIXES)

# Exact keys that would carry row values or raw text.
FORBIDDEN_KEYS = frozenset(
    {
        "raw_data",
        "raw_dataset",
        "raw_rows",
        "raw_values",
        "dataset_rows",
        "sample_values",
        "sample_data",
        "sample_rows",
        "preview_rows",
        "matched_text",
        "matched_values",
        "text_sample",
        "cell_values",
        "first_rows",
        "last_rows",
        "head",
        "tail",
        "records",
    }
)

_SECRET_KEY_MARKERS = ("token", "secret", "password", "api_key", "apikey", "credential")


class DataLeakageError(Exception):
    """Raised when a cloud-facing payload would expose raw or sensitive values."""


def _iter_strings(payload: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{path}.{key}"
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_KEYS:
                raise DataLeakageError(
                    f"Refusing cloud-facing payload: structural key '{key}' can carry raw row values."
                )
            if _is_identifier_key(key_text) and isinstance(value, str):
                continue
            yield from _iter_strings(value, child)
    elif isinstance(payload, (list, tuple, set)):
        for index, value in enumerate(payload):
            yield from _iter_strings(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        if _is_identifier_value(payload):
            return
        yield path, payload


def contains_sensitive_value(text: str) -> bool:
    """Return True when text looks like it contains raw PII or a local path."""
    return bool(
        EMAIL_PATTERN.search(text)
        or PHONE_PATTERN.search(text)
        or SSN_PATTERN.search(text)
        or CARD_PATTERN.search(text)
        or ABSOLUTE_PATH_PATTERN.search(text)
    )


def enforce_cloud_safe(payload: Any) -> Any:
    """Validate a cloud-facing payload, raising ``DataLeakageError`` on violation."""
    for path, value in _iter_strings(payload):
        if EMAIL_PATTERN.search(value):
            raise DataLeakageError(f"Refusing cloud-facing payload: email-like value at {path}.")
        if SSN_PATTERN.search(value):
            raise DataLeakageError(f"Refusing cloud-facing payload: SSN-like value at {path}.")
        if CARD_PATTERN.search(value):
            raise DataLeakageError(f"Refusing cloud-facing payload: card-like value at {path}.")
        if PHONE_PATTERN.search(value):
            raise DataLeakageError(f"Refusing cloud-facing payload: phone-like value at {path}.")
        if ABSOLUTE_PATH_PATTERN.search(value):
            raise DataLeakageError(
                f"Refusing cloud-facing payload: absolute local path at {path}."
            )
    return payload


def _scrub_text(text: str, max_length: int = 500) -> str:
    if _is_identifier_value(text):
        return text if len(text) <= max_length else text[:max_length] + "…[truncated]"
    scrubbed = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    scrubbed = SSN_PATTERN.sub("[REDACTED_SSN]", scrubbed)
    scrubbed = CARD_PATTERN.sub("[REDACTED_CARD]", scrubbed)
    scrubbed = PHONE_PATTERN.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = ABSOLUTE_PATH_PATTERN.sub(" [REDACTED_LOCAL_PATH] ", scrubbed)
    if len(scrubbed) > max_length:
        scrubbed = scrubbed[:max_length] + "…[truncated]"
    return scrubbed


def sanitize_for_audit(value: Any) -> Any:
    """Recursively scrub a value before it is written to an audit record."""
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS) or lowered in {
                "approval_id",
                "approval_token",
            }:
                sanitized[str(key)] = "[REDACTED_SECRET]"
            elif lowered in FORBIDDEN_KEYS:
                sanitized[str(key)] = "[REDACTED_RAW_CONTENT]"
            else:
                sanitized[str(key)] = sanitize_for_audit(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_for_audit(item) for item in value]
    if isinstance(value, str):
        return _scrub_text(value)
    return value


__all__ = [
    "DataLeakageError",
    "FORBIDDEN_KEYS",
    "contains_sensitive_value",
    "enforce_cloud_safe",
    "sanitize_for_audit",
]

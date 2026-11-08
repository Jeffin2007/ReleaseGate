"""
Centralized logging configuration with sensitive-value redaction.
Prevents credentials, tokens, authorization headers, and PII patterns from leaking into logs.
"""

import logging
import re
import sys
from typing import Any, List, Pattern

# Regular expressions for identifying sensitive patterns in log messages
SENSITIVE_PATTERNS: List[Pattern[str]] = [
    # 1. Database URLs: postgresql://user:password@host...
    re.compile(r"(://[^:\s@]+:)([^@\s]+)(@)", re.IGNORECASE),
    # 2. Bearer tokens in headers: Authorization: Bearer <token> or Bearer <token>
    re.compile(r"(?i)\b(Bearer\s+)(\S+)"),
    # 3. Standalone JWT-like tokens (three base64url segments starting with eyJ)
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]+)?\b"),
    # 4. Key-value secret assignments: token=..., password=..., secret=..., pwd=...
    re.compile(
        r"(?i)\b(password|secret|token|api_key|apikey|access_token|refresh_token|auth_token|authorization|private_key|pwd)\s*[:=]\s*['\"]?(?!Bearer\s+)([^'\"\s,;&]+)['\"]?"
    ),
    # 5. Credit Card numbers (13-16 digits)
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    # 6. US Social Security Number pattern (XXX-XX-XXXX)
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
]

REDACTION_MASK = "[REDACTED]"


class SensitiveRedactionFilter(logging.Filter):
    """
    Log filter that scrubs credentials, tokens, and PII patterns from log records.
    """

    def __init__(self, enabled: bool = True):
        super().__init__()
        self.enabled = enabled

    def redact_text(self, text: str) -> str:
        if not self.enabled or not text:
            return text

        result = text
        # Redact database URL credentials: user:***@host
        result = SENSITIVE_PATTERNS[0].sub(r"\g<1>***\g<3>", result)

        # Redact Bearer tokens: Bearer [REDACTED]
        result = SENSITIVE_PATTERNS[1].sub(r"\g<1>" + REDACTION_MASK, result)

        # Redact standalone JWT tokens
        result = SENSITIVE_PATTERNS[2].sub(REDACTION_MASK, result)

        # Redact key-value pairs: token=[REDACTED]
        result = SENSITIVE_PATTERNS[3].sub(r"\1=" + REDACTION_MASK, result)

        # Redact payment card numbers
        result = SENSITIVE_PATTERNS[4].sub(REDACTION_MASK, result)

        # Redact SSN patterns
        result = SENSITIVE_PATTERNS[5].sub(REDACTION_MASK, result)

        return result

    def filter(self, record: logging.LogRecord) -> bool:
        if self.enabled:
            if isinstance(record.msg, str):
                record.msg = self.redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: self.redact_text(str(v)) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        self.redact_text(str(arg)) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
        return True


def configure_logging(
    log_level: str = "INFO",
    redact_sensitive: bool = True,
    log_format: str = "text",
) -> None:
    """
    Initialize centralized application logging.
    Attaches sensitive redaction filter to handlers.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    date_format = "%Y-%m-%d %H:%M:%S"
    if log_format == "json":
        format_str = (
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"message":"%(message)s"}'
        )
    else:
        format_str = (
            "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s"
        )

    formatter = logging.Formatter(fmt=format_str, datefmt=date_format)

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    # Attach redaction filter
    redaction_filter = SensitiveRedactionFilter(enabled=redact_sensitive)
    handler.addFilter(redaction_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplicate lines
    root_logger.handlers = [handler]

    # Configure third-party loggers to avoid noise
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience getter for namespaced loggers."""
    return logging.getLogger(name)

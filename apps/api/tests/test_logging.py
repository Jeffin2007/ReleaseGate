"""
Automated unit tests for centralized logging sensitive data redaction filter.
"""

import logging
from app.core.logging import SensitiveRedactionFilter


def test_redaction_filter_scrubs_database_passwords():
    """Verify database connection strings with passwords are redacted."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = "Connecting to postgresql://admin:super_secret_pw123@db.internal:5432/db"
    redacted = filter_obj.redact_text(raw_message)

    assert "super_secret_pw123" not in redacted
    assert "postgresql://admin:***@db.internal:5432/db" in redacted


def test_redaction_filter_scrubs_tokens_and_secrets():
    """Verify key-value tokens, api keys, and passwords are redacted."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = "Authentication error for user_id=42 token=eyJhbGciOiJIUzI1NiJ9.abc.def and api_key=sk-123456789"
    redacted = filter_obj.redact_text(raw_message)

    assert "eyJhbGciOiJIUzI1NiJ9.abc.def" not in redacted
    assert "sk-123456789" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_filter_scrubs_bearer_tokens():
    """Verify Bearer authorization header values are redacted."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = "Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    redacted = filter_obj.redact_text(raw_message)

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "Bearer [REDACTED]" in redacted


def test_redaction_filter_scrubs_ssn_pattern():
    """Verify SSN pattern is masked."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = "Detected taxpayer record with SSN 123-45-6789 in table"
    redacted = filter_obj.redact_text(raw_message)

    assert "123-45-6789" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_filter_log_record():
    """Verify logging.LogRecord message gets redacted by filter."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="User session established with secret='my_jwt_secret_token'",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)
    assert "my_jwt_secret_token" not in record.msg
    assert "[REDACTED]" in record.msg


def test_redaction_filter_scrubs_standalone_jwt():
    """Verify standalone JWT tokens in payload or message bodies are redacted."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = (
        "Incoming payload decoded unverified token: "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG6pQGs_W4w4w4w4w4"
    )
    redacted = filter_obj.redact_text(raw_message)

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_filter_scrubs_dsn_database_passwords():
    """Verify key-value DSN connection strings with passwords are redacted."""
    filter_obj = SensitiveRedactionFilter(enabled=True)
    raw_message = "ODBC connection initialized: Host=db.internal;Port=5432;User=admin;Password=secret_db_pass_99;Database=releasegate"
    redacted = filter_obj.redact_text(raw_message)

    assert "secret_db_pass_99" not in redacted
    assert "Password=[REDACTED]" in redacted

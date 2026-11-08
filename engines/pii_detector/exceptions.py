"""
Exceptions for the Local Privacy and PII Detection Engine.
"""


class PIIDetectionError(Exception):
    """Base exception for all PII detection errors."""
    pass


class LanguageModelUnavailableError(PIIDetectionError):
    """Raised when an NLP language model is missing or fails to load."""
    pass


class UnsupportedLanguageError(PIIDetectionError):
    """Raised when an unsupported language is requested."""
    pass


class InvalidDatasetError(PIIDetectionError):
    """Raised when a dataset cannot be loaded or scanned."""
    pass

"""
Exceptions for the Deterministic Data Quality Validator.
"""


class QualityValidationError(Exception):
    """Base exception for all quality validation errors."""
    pass


class InvalidRuleConfigurationError(QualityValidationError):
    """Raised when a validation rule is malformed or invalid."""
    pass


class InvalidDatasetForValidation(QualityValidationError):
    """Raised when a dataset cannot be parsed or evaluated for quality."""
    pass

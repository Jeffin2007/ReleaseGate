"""
Exceptions for the Safe Dataset Transformation Engine.
"""


class TransformationEngineError(Exception):
    """Base exception for all transformation engine errors."""
    pass


class DisallowedOperationError(TransformationEngineError):
    """Raised when an unapproved or disallowed operation is attempted."""
    pass


class InvalidTransformationSpecError(TransformationEngineError):
    """Raised when a transformation specification is malformed or invalid."""
    pass


class ArbitraryCodeExecutionRejectedError(TransformationEngineError):
    """Raised when code strings, lambda expressions, SQL, or shell injections are detected."""
    pass

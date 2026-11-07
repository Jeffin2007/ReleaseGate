"""
Exceptions for the Deterministic Release Policy and Risk Engine.
"""


class PolicyEngineError(Exception):
    """Base exception for all policy engine errors."""
    pass


class InvalidPolicyConfigurationError(PolicyEngineError):
    """Raised when policy configuration or version is invalid."""
    pass


class MissingEvaluationEvidenceError(PolicyEngineError):
    """Raised when critical required evidence is missing during strict evaluation."""
    pass

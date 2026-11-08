"""
Safe Dataset Transformation Engine.
Provides controlled, allowlisted transformations without executing arbitrary code
or modifying original datasets.
"""

from .exceptions import (
    ArbitraryCodeExecutionRejectedError,
    DisallowedOperationError,
    InvalidTransformationSpecError,
    TransformationEngineError,
)
from .schemas import (
    FilterOperator,
    FilterRowsOp,
    GeneralizationStrategy,
    GeneralizeColumnOp,
    MaskColumnOp,
    MaskingStrategy,
    OperationSummary,
    OperationType,
    PseudonymizeColumnOp,
    RemoveColumnOp,
    TransformationOperation,
    TransformationPreview,
    TransformationProvenance,
    TransformationResult,
    TransformationSpec,
)
from .transformer import TransformationEngine

__all__ = [
    "TransformationEngine",
    "TransformationSpec",
    "TransformationOperation",
    "OperationType",
    "MaskingStrategy",
    "GeneralizationStrategy",
    "FilterOperator",
    "RemoveColumnOp",
    "MaskColumnOp",
    "PseudonymizeColumnOp",
    "GeneralizeColumnOp",
    "FilterRowsOp",
    "OperationSummary",
    "TransformationPreview",
    "TransformationProvenance",
    "TransformationResult",
    "TransformationEngineError",
    "DisallowedOperationError",
    "InvalidTransformationSpecError",
    "ArbitraryCodeExecutionRejectedError",
]

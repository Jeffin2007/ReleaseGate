"""
Safe Dataset Transformation Engine.
Executes controlled, allowlisted transformations to mitigate release risks:
- Column removal
- Column masking and redaction
- Deterministic HMAC-SHA256 pseudonymization
- Generalization (numeric binning, date truncation, categorical bucketing)
- Declarative row filtering
- Complete immutability of original datasets
- Cryptographic provenance and aggregate preview generation
- Automated post-transformation re-validation (privacy, quality, release policy)
"""

from datetime import datetime, timezone
import hashlib
import hmac
import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
import pandas as pd

from engines.dataset_profiler import DatasetProfiler, ProfilingError
from engines.pii_detector import PIIDetector, PIIDetectorConfig
from engines.policy_engine import PolicyConfig, PolicyEngine
from engines.quality_validator import QualityValidationConfig, QualityValidator

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

# Prohibited substrings for arbitrary code injection prevention
BANNED_CODE_PATTERNS = [
    r"__import__",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\bimport\s+os\b",
    r"\bimport\s+sys\b",
    r";\s*rm\s+-rf",
    r"\bdrop\s+table\b",
    r"<script",
]


class TransformationEngine:
    """
    Local transformation engine executing declarative, allowlisted mutations.
    Guarantees that input datasets remain strictly immutable.
    """

    @classmethod
    def _scan_for_arbitrary_code(cls, obj: Any) -> None:
        """
        Recursively scan objects and strings for code injection, SQL injection,
        or shell execution patterns.
        """
        if isinstance(obj, str):
            for pattern in BANNED_CODE_PATTERNS:
                if re.search(pattern, obj, re.IGNORECASE):
                    raise ArbitraryCodeExecutionRejectedError(
                        f"Prohibited executable expression or injection attempt detected: '{obj}'"
                    )
        elif isinstance(obj, dict):
            for k, v in obj.items():
                cls._scan_for_arbitrary_code(k)
                cls._scan_for_arbitrary_code(v)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                cls._scan_for_arbitrary_code(item)

    @classmethod
    def validate_spec(cls, df: pd.DataFrame, spec: TransformationSpec) -> None:
        """
        Validate that the transformation specification conforms to safety constraints
        and references valid columns.
        """
        if not spec.operations:
            raise InvalidTransformationSpecError("Transformation specification must contain at least one operation.")

        cls._scan_for_arbitrary_code(spec.model_dump())

        # Track active columns throughout the pipeline
        current_cols = set(df.columns)

        for op in spec.operations:
            target_col = op.column_name
            if target_col not in current_cols and op.op_type != OperationType.FILTER_ROWS:
                raise InvalidTransformationSpecError(
                    f"Operation '{op.op_type}' references non-existent column '{target_col}'."
                )

            if isinstance(op, RemoveColumnOp):
                current_cols.discard(target_col)
            elif isinstance(op, GeneralizeColumnOp):
                if op.strategy == GeneralizationStrategy.NUMERIC_BINNING:
                    if not op.bins or len(op.bins) < 2:
                        raise InvalidTransformationSpecError(
                            f"Numeric binning requires at least 2 boundary values in 'bins'."
                        )
                elif op.strategy == GeneralizationStrategy.CATEGORY_BUCKETING:
                    if not op.category_mapping:
                        raise InvalidTransformationSpecError(
                            "Category bucketing requires a non-empty 'category_mapping' dictionary."
                        )

    @staticmethod
    def _mask_email(val: str) -> str:
        """Helper to mask email while preserving domain structure (e.g. j***e@domain.com)."""
        val = str(val).strip()
        if "@" not in val:
            return "[REDACTED_EMAIL]"
        parts = val.split("@", 1)
        user, domain = parts[0], parts[1]
        if len(user) <= 2:
            masked_user = user[0] + "***" if user else "***"
        else:
            masked_user = user[0] + "***" + user[-1]
        return f"{masked_user}@{domain}"

    @staticmethod
    def _mask_phone(val: str) -> str:
        """Helper to mask telephone numbers keeping only last 4 digits visible."""
        val = str(val).strip()
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 4:
            return f"***-***-{digits[-4:]}"
        return "***-***-****"

    @staticmethod
    def _mask_last_4(val: str) -> str:
        """Helper to mask generic credentials keeping only trailing 4 characters."""
        val = str(val).strip()
        if len(val) > 4:
            return f"***-**-{val[-4:]}"
        return "****"

    @classmethod
    def _pseudonymize_value(cls, val: Any, salt: str, prefix: str) -> str:
        """Deterministic keyed HMAC-SHA256 token generation."""
        val_str = str(val).strip()
        token = hmac.new(
            salt.encode("utf-8"),
            val_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:12]
        return f"{prefix}{token}"

    @classmethod
    def apply_transformations(
        cls,
        df: pd.DataFrame,
        spec: TransformationSpec,
        dataset_id: str,
        input_version: int,
        output_version: int,
        input_hash: str,
        input_artifact_ref: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, TransformationProvenance, TransformationPreview]:
        """
        Execute transformations deterministically on a deep clone of the DataFrame.
        The input DataFrame is guaranteed not to be modified.
        """
        cls.validate_spec(df, spec)

        # Work strictly on a deep clone to preserve source dataset immutability
        transformed_df = df.copy(deep=True)
        rows_before = len(df)
        cols_before = len(df.columns)

        columns_removed: List[str] = []
        columns_modified: List[str] = []
        operation_summaries: List[OperationSummary] = []
        applied_ops_log: List[Dict[str, Any]] = []

        global_salt = spec.global_salt or f"releasegate_salt_{dataset_id}"

        for op in spec.operations:
            target_col = op.column_name

            if isinstance(op, RemoveColumnOp):
                transformed_df.drop(columns=[target_col], inplace=True)
                columns_removed.append(target_col)
                summary = OperationSummary(
                    op_type=OperationType.REMOVE_COLUMN,
                    target_column=target_col,
                    affected_count=rows_before,
                    details={"action": "Column removed completely"},
                )
                operation_summaries.append(summary)
                applied_ops_log.append(op.model_dump())

            elif isinstance(op, MaskColumnOp):
                non_null_mask = transformed_df[target_col].notna()
                affected = int(non_null_mask.sum())

                if op.strategy == MaskingStrategy.FULL_REDACTION:
                    transformed_df.loc[non_null_mask, target_col] = op.placeholder
                elif op.strategy == MaskingStrategy.PARTIAL_EMAIL:
                    transformed_df.loc[non_null_mask, target_col] = transformed_df.loc[
                        non_null_mask, target_col
                    ].apply(cls._mask_email)
                elif op.strategy == MaskingStrategy.PARTIAL_PHONE:
                    transformed_df.loc[non_null_mask, target_col] = transformed_df.loc[
                        non_null_mask, target_col
                    ].apply(cls._mask_phone)
                elif op.strategy == MaskingStrategy.LAST_4_VISIBLE:
                    transformed_df.loc[non_null_mask, target_col] = transformed_df.loc[
                        non_null_mask, target_col
                    ].apply(cls._mask_last_4)
                elif op.strategy == MaskingStrategy.CUSTOM_PLACEHOLDER:
                    transformed_df.loc[non_null_mask, target_col] = op.placeholder

                if target_col not in columns_modified:
                    columns_modified.append(target_col)

                summary = OperationSummary(
                    op_type=OperationType.MASK_COLUMN,
                    target_column=target_col,
                    affected_count=affected,
                    details={"strategy": op.strategy.value, "placeholder": op.placeholder},
                )
                operation_summaries.append(summary)
                applied_ops_log.append(op.model_dump())

            elif isinstance(op, PseudonymizeColumnOp):
                salt = op.salt or global_salt
                non_null_mask = transformed_df[target_col].notna()
                affected = int(non_null_mask.sum())

                transformed_df.loc[non_null_mask, target_col] = transformed_df.loc[
                    non_null_mask, target_col
                ].apply(lambda x: cls._pseudonymize_value(x, salt, op.prefix))

                if target_col not in columns_modified:
                    columns_modified.append(target_col)

                summary = OperationSummary(
                    op_type=OperationType.PSEUDONYMIZE_COLUMN,
                    target_column=target_col,
                    affected_count=affected,
                    details={"prefix": op.prefix},
                )
                operation_summaries.append(summary)
                applied_ops_log.append(op.model_dump())

            elif isinstance(op, GeneralizeColumnOp):
                non_null_mask = transformed_df[target_col].notna()
                affected = int(non_null_mask.sum())

                if op.strategy == GeneralizationStrategy.NUMERIC_BINNING:
                    num_series = pd.to_numeric(transformed_df[target_col], errors="coerce")
                    labels = op.bin_labels if op.bin_labels else False
                    binned = pd.cut(
                        num_series,
                        bins=op.bins,  # type: ignore
                        labels=labels,
                        include_lowest=True,
                    )
                    transformed_df[target_col] = binned.astype(str)

                elif op.strategy == GeneralizationStrategy.DATE_TRUNCATION:
                    dt_series = pd.to_datetime(transformed_df[target_col], errors="coerce")
                    if op.date_interval == "YEAR":
                        transformed_df.loc[non_null_mask, target_col] = dt_series[non_null_mask].dt.strftime("%Y")
                    elif op.date_interval == "MONTH":
                        transformed_df.loc[non_null_mask, target_col] = dt_series[non_null_mask].dt.strftime("%Y-%m")
                    elif op.date_interval == "DECADE":
                        decades = (dt_series[non_null_mask].dt.year // 10) * 10
                        transformed_df.loc[non_null_mask, target_col] = decades.astype(str) + "s"

                elif op.strategy == GeneralizationStrategy.CATEGORY_BUCKETING:
                    mapping = op.category_mapping or {}
                    transformed_df.loc[non_null_mask, target_col] = transformed_df.loc[
                        non_null_mask, target_col
                    ].map(mapping).fillna(transformed_df.loc[non_null_mask, target_col])

                if target_col not in columns_modified:
                    columns_modified.append(target_col)

                summary = OperationSummary(
                    op_type=OperationType.GENERALIZE_COLUMN,
                    target_column=target_col,
                    affected_count=affected,
                    details={"strategy": op.strategy.value},
                )
                operation_summaries.append(summary)
                applied_ops_log.append(op.model_dump())

            elif isinstance(op, FilterRowsOp):
                series = transformed_df[target_col]
                rows_prior = len(transformed_df)

                if op.operator == FilterOperator.EQUALS:
                    mask = series == op.value
                elif op.operator == FilterOperator.NOT_EQUALS:
                    mask = series != op.value
                elif op.operator == FilterOperator.GREATER_THAN:
                    mask = pd.to_numeric(series, errors="coerce") > float(op.value)
                elif op.operator == FilterOperator.GREATER_THAN_OR_EQUAL:
                    mask = pd.to_numeric(series, errors="coerce") >= float(op.value)
                elif op.operator == FilterOperator.LESS_THAN:
                    mask = pd.to_numeric(series, errors="coerce") < float(op.value)
                elif op.operator == FilterOperator.LESS_THAN_OR_EQUAL:
                    mask = pd.to_numeric(series, errors="coerce") <= float(op.value)
                elif op.operator == FilterOperator.IN_LIST:
                    mask = series.isin(op.values_list or [])
                elif op.operator == FilterOperator.NOT_IN_LIST:
                    mask = ~series.isin(op.values_list or [])
                elif op.operator == FilterOperator.IS_NULL:
                    mask = series.isna()
                elif op.operator == FilterOperator.IS_NOT_NULL:
                    mask = series.notna()
                else:
                    raise DisallowedOperationError(f"Unsupported filter operator '{op.operator}'")

                transformed_df = transformed_df[mask].copy()
                rows_after_op = len(transformed_df)
                dropped = rows_prior - rows_after_op

                summary = OperationSummary(
                    op_type=OperationType.FILTER_ROWS,
                    target_column=target_col,
                    affected_count=dropped,
                    details={"operator": op.operator.value, "rows_retained": rows_after_op},
                )
                operation_summaries.append(summary)
                applied_ops_log.append(op.model_dump())

        rows_after = len(transformed_df)
        cols_after = len(transformed_df.columns)

        preview = TransformationPreview(
            input_row_count=rows_before,
            output_row_count=rows_after,
            rows_removed=rows_before - rows_after,
            input_column_count=cols_before,
            output_column_count=cols_after,
            columns_removed=columns_removed,
            columns_modified=columns_modified,
            operation_summaries=operation_summaries,
        )

        # Compute deterministic output hash from serialized CSV representation
        csv_buffer = io.StringIO()
        transformed_df.to_csv(csv_buffer, index=False)
        output_hash = hashlib.sha256(csv_buffer.getvalue().encode("utf-8")).hexdigest()

        transformation_id = str(uuid.uuid4())
        provenance = TransformationProvenance(
            transformation_id=transformation_id,
            dataset_id=dataset_id,
            input_version=input_version,
            output_version=output_version,
            input_hash=input_hash,
            output_hash=output_hash,
            applied_operations=applied_ops_log,
            transformed_at_utc=datetime.now(timezone.utc).isoformat(),
            input_artifact_ref=input_artifact_ref,
        )

        return transformed_df, provenance, preview

    @classmethod
    def serialize_dataframe(cls, df: pd.DataFrame, file_format: str) -> bytes:
        """Serialize DataFrame to bytes according to format."""
        fmt = file_format.lower().lstrip(".")
        buf = io.BytesIO()
        if fmt == "csv":
            df.to_csv(buf, index=False, encoding="utf-8")
        elif fmt == "xlsx":
            df.to_excel(buf, index=False, engine="openpyxl")
        elif fmt == "json":
            df.to_json(buf, orient="records", indent=2)
        else:
            raise TransformationEngineError(f"Unsupported serialization format: '{file_format}'")
        return buf.getvalue()

    @classmethod
    def transform_dataset_bytes(
        cls,
        content: bytes,
        file_format: str,
        spec: TransformationSpec,
        dataset_id: str,
        input_version: int,
        output_version: int,
        storage: Optional[Any] = None,
        run_post_verification: bool = True,
        pii_config: Optional[PIIDetectorConfig] = None,
        quality_config: Optional[QualityValidationConfig] = None,
        policy_config: Optional[PolicyConfig] = None,
        metadata_context: Optional[Dict[str, Any]] = None,
    ) -> TransformationResult:
        """
        Safely execute transformations on raw dataset bytes:
        1. Loads bytes into memory without code execution.
        2. Computes input SHA-256 hash.
        3. Executes transformations on isolated clone.
        4. Serializes output bytes and computes output SHA-256 hash.
        5. Stores new transformed artifact in storage if storage is provided.
        6. Re-evaluates privacy, data quality, and release policy on the transformed dataset.
        """
        try:
            df = DatasetProfiler.load_dataframe(content, file_format)
        except ProfilingError as exc:
            raise InvalidTransformationSpecError(f"Failed to load dataset for transformation: {str(exc)}") from exc

        input_hash = hashlib.sha256(content).hexdigest()

        transformed_df, provenance, preview = cls.apply_transformations(
            df=df,
            spec=spec,
            dataset_id=dataset_id,
            input_version=input_version,
            output_version=output_version,
            input_hash=input_hash,
        )

        output_bytes = cls.serialize_dataframe(transformed_df, file_format)
        computed_output_hash = hashlib.sha256(output_bytes).hexdigest()

        # Update provenance output hash with exact serialized bytes hash
        provenance = TransformationProvenance(
            transformation_id=provenance.transformation_id,
            dataset_id=provenance.dataset_id,
            input_version=provenance.input_version,
            output_version=provenance.output_version,
            input_hash=provenance.input_hash,
            output_hash=computed_output_hash,
            applied_operations=provenance.applied_operations,
            transformed_at_utc=provenance.transformed_at_utc,
            input_artifact_ref=provenance.input_artifact_ref,
        )

        output_artifact_ref = None
        if storage is not None:
            output_artifact_ref, _, _ = storage.store_dataset(
                dataset_id=uuid.UUID(dataset_id) if isinstance(dataset_id, str) else dataset_id,
                version_number=output_version,
                content=output_bytes,
                ext=file_format.lower().lstrip("."),
            )

        post_pii_report = None
        post_quality_report = None
        post_policy_evaluation = None

        if run_post_verification:
            # 1. Re-run Privacy & PII scanning on transformed data
            pii_detector = PIIDetector(config=pii_config)
            pii_rep = pii_detector.scan_dataframe(
                df=transformed_df,
                dataset_id=dataset_id,
                version_number=output_version,
            )
            post_pii_report = pii_rep.to_cloud_metadata()

            # 2. Re-run Data Quality validation on transformed data
            quality_validator = QualityValidator(config=quality_config)
            qual_rep = quality_validator.validate_dataframe(
                df=transformed_df,
                dataset_id=dataset_id,
                version_number=output_version,
            )
            post_quality_report = qual_rep.to_cloud_metadata()

            # 3. Re-run Release Policy & Risk scoring
            policy_engine = PolicyEngine(policy_config=policy_config)
            meta = metadata_context or {}
            meta.update({
                "dataset_name": meta.get("dataset_name", f"Transformed Dataset v{output_version}"),
                "description": meta.get("description", "Sanitized and transformed release candidate"),
                "file_format": file_format,
                "file_size": len(output_bytes),
                "content_hash": computed_output_hash,
            })
            prov = {
                "license": meta.get("license", "Apache-2.0"),
                "source_url": meta.get("source_url", "https://releasegate.internal/local"),
            }
            ctx = {"domain": meta.get("domain", "general"), "retention_policy": "365_days"}

            pol_eval = policy_engine.evaluate(
                dataset_id=dataset_id,
                version_number=output_version,
                pii_report=post_pii_report,
                quality_report=post_quality_report,
                metadata=meta,
                provenance=prov,
                context=ctx,
            )
            post_policy_evaluation = pol_eval.to_cloud_metadata()

        return TransformationResult(
            dataset_id=dataset_id,
            input_version=input_version,
            output_version=output_version,
            input_hash=input_hash,
            output_hash=computed_output_hash,
            provenance=provenance,
            preview=preview,
            output_artifact_ref=output_artifact_ref,
            post_pii_report=post_pii_report,
            post_quality_report=post_quality_report,
            post_policy_evaluation=post_policy_evaluation,
        )

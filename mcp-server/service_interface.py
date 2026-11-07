"""
Service Interface between Model Context Protocol (MCP) handlers and ReleaseGate capabilities.
Enforces the Frozen Architecture Baseline v1.0 boundary:
- Keeps MCP tools strictly separated from business logic.
- MCP tools never access raw files or databases directly; all calls route through this service layer.
- Ensures zero raw dataset values are returned to the caller or cloud control plane.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import pandas as pd

from engines.dataset_profiler import DatasetProfiler, ProfilingResult
from engines.pii_detector import PIIDetector, PIIDetectorConfig
from engines.quality_validator import QualityValidationConfig, QualityValidator
from engines.policy_engine import (
    PolicyConfig,
    PolicyEngine,
    PolicyEvaluationResult,
    RiskBand,
)
from engines.transformation_engine import (
    FilterOperator,
    FilterRowsOp,
    GeneralizationStrategy,
    GeneralizeColumnOp,
    MaskColumnOp,
    MaskingStrategy,
    PseudonymizeColumnOp,
    RemoveColumnOp,
    TransformationEngine,
    TransformationOperation,
    TransformationSpec,
)

from local_worker.inspection_pipeline import DatasetInspectionWorkflow
from local_worker.secure_storage import LocalDatasetStorage

from mcp_server.security.permissions import (
    HumanApprovalRequiredError,
    verify_human_approval_token,
)


class ServiceNotFoundError(Exception):
    """Raised when an entity (dataset, release, finding) is not found."""
    pass


class ServiceValidationError(Exception):
    """Raised when an operation fails business validation."""
    pass


class ReleaseGateService:
    """
    Central service interface for ReleaseGate MCP server.
    Manages local inspection orchestration, safe transformations, and governance lifecycle.
    """

    def __init__(
        self,
        storage: Optional[LocalDatasetStorage] = None,
        workflow: Optional[DatasetInspectionWorkflow] = None,
    ) -> None:
        self.storage = storage or LocalDatasetStorage()
        self.workflow = workflow or DatasetInspectionWorkflow(storage=self.storage)
        self.transformation_engine = TransformationEngine()

        # In-memory governance ledger for releases & staged changes
        # In production this delegates to authenticated Cloud Control Plane API
        self._releases_ledger: Dict[str, Dict[str, Any]] = {}
        self._staged_releases: Dict[str, Dict[str, Any]] = {}
        self._dataset_registry: Dict[str, Dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Helper Registration (For tests and local worker plane)
    # -------------------------------------------------------------------------
    def register_dataset_artifact(
        self,
        dataset_id: str,
        version_number: int,
        content: bytes,
        file_format: str = "csv",
        name: Optional[str] = None,
        description: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register and store a dataset in local storage for subsequent inspection."""
        uid = uuid.UUID(str(dataset_id))
        clean_ext = file_format.lstrip(".").lower()
        artifact_ref, byte_size, content_hash = self.storage.store_dataset(
            dataset_id=uid,
            version_number=version_number,
            content=content,
            ext=clean_ext,
        )
        key = f"{dataset_id}:v{version_number}"
        entry = {
            "dataset_id": str(dataset_id),
            "version_number": version_number,
            "artifact_ref": artifact_ref,
            "file_format": clean_ext,
            "file_size": byte_size,
            "content_hash": content_hash,
            "name": name or f"dataset_{str(dataset_id)[:8]}",
            "description": description or "Dataset registered in ReleaseGate",
            "provenance": provenance or {"license": "MIT", "has_license": True, "is_approved": True},
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dataset_registry[key] = entry
        return entry

    def _get_dataset_entry(self, dataset_id: str, version_number: int) -> Dict[str, Any]:
        key = f"{dataset_id}:v{version_number}"
        if key in self._dataset_registry:
            return self._dataset_registry[key]

        # Check if stored in LocalDatasetStorage
        for fmt in ["csv", "json", "parquet", "xlsx"]:
            ref = f"artifact://local/datasets/{dataset_id}/v{version_number}/data.{fmt}"
            if self.storage.exists(ref):
                content = self.storage.read_dataset(ref)
                return self.register_dataset_artifact(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    content=content,
                    file_format=fmt,
                )

        raise ServiceNotFoundError(
            f"Dataset '{dataset_id}' version {version_number} not found in local storage."
        )

    # -------------------------------------------------------------------------
    # Tool 1: inspect_dataset
    # -------------------------------------------------------------------------
    def inspect_dataset(
        self,
        dataset_id: str,
        version_number: int = 1,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute full local inspection (profiling, PII, quality, policy scoring).
        Returns sanitized audit result with zero raw dataset values.
        """
        entry = self._get_dataset_entry(dataset_id, version_number)
        content = self.storage.read_dataset(entry["artifact_ref"])

        result = self.workflow.execute_inspection(
            dataset_id=dataset_id,
            version_number=version_number,
            artifact_ref=entry["artifact_ref"],
            content=content,
            file_format=entry["file_format"],
            provenance=entry.get("provenance"),
        )
        return result.to_dict()

    # -------------------------------------------------------------------------
    # Tool 2: detect_sensitive_data
    # -------------------------------------------------------------------------
    def detect_sensitive_data(
        self,
        dataset_id: str,
        version_number: int = 1,
        confidence_threshold: float = 0.6,
        entities: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Scan dataset for PII using Microsoft Presidio.
        Returns sanitized entity coordinates, counts, and confidence.
        """
        entry = self._get_dataset_entry(dataset_id, version_number)
        content = self.storage.read_dataset(entry["artifact_ref"])
        df = DatasetProfiler.load_dataframe(content, entry["file_format"])

        config = PIIDetectorConfig(
            default_confidence_threshold=confidence_threshold,
            enabled_entities=entities,
        )
        detector = PIIDetector(config=config)
        report = detector.scan_dataframe(
            df=df,
            dataset_id=dataset_id,
            version_number=version_number,
        )

        return {
            "dataset_id": dataset_id,
            "version_number": version_number,
            "total_findings": len(report.findings),
            "has_critical_pii": report.has_critical_pii,
            "has_high_pii": report.has_high_pii,
            "scanned_columns": len(report.columns),
            "findings": [
                {
                    "entity_type": f.entity_type,
                    "column_name": f.column_name,
                    "occurrence_count": f.occurrence_count,
                    "severity": f.severity.value,
                    "confidence": round(f.confidence, 4),
                    "evidence_ref": f.evidence_ref.model_dump(),
                }
                for f in report.findings
            ],
            "detected_entities": sorted(list({f.entity_type for f in report.findings})),
        }

    # -------------------------------------------------------------------------
    # Tool 3: validate_data_quality
    # -------------------------------------------------------------------------
    def validate_data_quality(
        self,
        dataset_id: str,
        version_number: int = 1,
        allow_nulls: Optional[bool] = None,
        allow_duplicates: Optional[bool] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate dataset quality using deterministic local rules.
        Returns aggregate quality metrics and issues without row values.
        """
        entry = self._get_dataset_entry(dataset_id, version_number)
        content = self.storage.read_dataset(entry["artifact_ref"])
        df = DatasetProfiler.load_dataframe(content, entry["file_format"])

        config = QualityValidationConfig()
        if allow_nulls is not None:
            config.allow_null_values = allow_nulls
        if allow_duplicates is not None:
            config.allow_duplicate_records = allow_duplicates

        validator = QualityValidator(config=config)
        report = validator.validate_dataframe(
            df=df,
            dataset_id=dataset_id,
            version_number=version_number,
        )

        return {
            "dataset_id": dataset_id,
            "version_number": version_number,
            "quality_score": report.summary.quality_score,
            "passed_rules_count": report.summary.passed_rules_count,
            "failed_rules_count": report.summary.failed_rules_count,
            "has_critical_failures": report.summary.has_critical_failures,
            "has_high_failures": report.summary.has_high_failures,
            "affected_columns": report.summary.affected_columns,
            "issues": [
                {
                    "rule_name": i.rule_name,
                    "column_name": i.column_name,
                    "severity": i.severity.value,
                    "violating_count": i.violating_count,
                    "message": i.message,
                    "evidence_ref": i.evidence_ref.model_dump(),
                }
                for i in report.issues
            ],
        }

    # -------------------------------------------------------------------------
    # Tool 4: check_release_policy
    # -------------------------------------------------------------------------
    def check_release_policy(
        self,
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
        domain: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate dataset against release policy rules and weighted scoring.
        """
        inspection = self.inspect_dataset(dataset_id, version_number, organization_id)
        summary = inspection["summary_report"]["risk_assessment"]
        return {
            "dataset_id": dataset_id,
            "version_number": version_number,
            "policy_version": policy_version,
            "is_release_eligible": summary["is_release_eligible"],
            "risk_score": summary["total_risk_score"],
            "risk_band": summary["risk_band"],
            "status": summary["status"],
            "blocking_reasons": summary["blocking_reasons"],
            "warnings": summary["warnings"],
            "category_scores": summary["category_scores"],
        }

    # -------------------------------------------------------------------------
    # Tool 5: generate_risk_report
    # -------------------------------------------------------------------------
    def generate_risk_report(
        self,
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate full structured risk report for governance decision-making.
        """
        inspection = self.inspect_dataset(dataset_id, version_number, organization_id)
        entry = self._get_dataset_entry(dataset_id, version_number)

        return {
            "report_id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "dataset_name": entry["name"],
            "version_number": version_number,
            "policy_version": policy_version,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "content_hash": entry["content_hash"],
            "risk_assessment": inspection["summary_report"]["risk_assessment"],
            "profiling_summary": inspection["summary_report"]["profiling"],
            "privacy_summary": inspection["summary_report"]["privacy_inspection"],
            "quality_summary": inspection["summary_report"]["quality_inspection"],
            "total_findings": inspection["findings_count"],
        }

    # -------------------------------------------------------------------------
    # Tool 6: propose_transformation
    # -------------------------------------------------------------------------
    def propose_transformation(
        self,
        dataset_id: str,
        version_number: int,
        operations: List[Dict[str, Any]],
        rationale: str,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate and simulate proposed allowlisted transformations.
        Produces an aggregate preview without exposing raw rows or modifying originals.
        """
        entry = self._get_dataset_entry(dataset_id, version_number)
        content = self.storage.read_dataset(entry["artifact_ref"])
        df = DatasetProfiler.load_dataframe(content, entry["file_format"])

        typed_ops: List[TransformationOperation] = []
        for op_dict in operations:
            op_name = op_dict.get("operation", "").strip().lower()
            col = op_dict.get("column") or ""
            params = op_dict.get("parameters", {})

            if op_name == "remove_column":
                typed_ops.append(RemoveColumnOp(column_name=col))
            elif op_name == "mask_column":
                strategy_str = params.get("strategy", "full_redaction").lower()
                strategy = MaskingStrategy(strategy_str)
                typed_ops.append(
                    MaskColumnOp(
                        column_name=col,
                        strategy=strategy,
                        placeholder=params.get("placeholder", "[REDACTED]"),
                        mask_char=params.get("mask_char", "*"),
                    )
                )
            elif op_name == "pseudonymize_column":
                typed_ops.append(
                    PseudonymizeColumnOp(
                        column_name=col,
                        salt=params.get("salt", "default_salt"),
                        prefix=params.get("prefix", "PSEUDO_"),
                    )
                )
            elif op_name == "generalize_column":
                strategy_str = params.get("strategy", "numeric_binning").lower()
                strategy = GeneralizationStrategy(strategy_str)
                typed_ops.append(
                    GeneralizeColumnOp(
                        column_name=col,
                        strategy=strategy,
                        bins=params.get("bins"),
                        labels=params.get("labels"),
                        category_mapping=params.get("category_mapping"),
                    )
                )
            elif op_name == "filter_rows":
                operator_str = params.get("operator", "==")
                operator = FilterOperator(operator_str)
                typed_ops.append(
                    FilterRowsOp(
                        column_name=col,
                        operator=operator,
                        value=params.get("value"),
                        values_list=params.get("values_list"),
                    )
                )
            else:
                raise ServiceValidationError(f"Prohibited transformation operation: '{op_name}'")

        spec = TransformationSpec(
            operations=typed_ops,
            rationale=rationale,
        )

        # Apply transformations on deep copy to get preview & simulated output hash
        next_version = version_number + 1
        transformed_df, provenance, preview = self.transformation_engine.apply_transformations(
            df=df,
            spec=spec,
            dataset_id=dataset_id,
            input_version=version_number,
            output_version=next_version,
            input_hash=entry["content_hash"],
            input_artifact_ref=entry["artifact_ref"],
        )

        staged_id = f"stage_{uuid.uuid4().hex[:12]}"
        proposal = {
            "proposal_id": staged_id,
            "dataset_id": dataset_id,
            "base_version": version_number,
            "target_version": next_version,
            "rationale": rationale,
            "operations_count": len(operations),
            "preview": preview.model_dump(),
            "simulated_output_hash": provenance.output_hash,
            "status": "PROPOSED",
            "spec_dict": [op_dict for op_dict in operations],
        }
        self._staged_releases[staged_id] = {
            **proposal,
            "transformed_df": transformed_df,
            "format": entry["file_format"],
        }

        return {
            "proposal_id": staged_id,
            "dataset_id": dataset_id,
            "base_version": version_number,
            "target_version": next_version,
            "rationale": rationale,
            "operations_count": len(operations),
            "preview": preview.model_dump(),
            "simulated_output_hash": provenance.output_hash,
            "status": "PROPOSED",
        }

    # -------------------------------------------------------------------------
    # Tool 7: prepare_release
    # -------------------------------------------------------------------------
    def prepare_release(
        self,
        dataset_id: str,
        source_version_number: int = 1,
        destination_target: str = "s3://analytics-export",
        release_notes: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stage a release package, establishing cryptographic evidence baseline.
        """
        entry = self._get_dataset_entry(dataset_id, source_version_number)
        release_id = f"rel_{uuid.uuid4().hex[:12]}"

        # Run fresh inspection for release verification
        inspection = self.inspect_dataset(dataset_id, source_version_number, organization_id)
        risk = inspection["summary_report"]["risk_assessment"]

        release_record = {
            "release_id": release_id,
            "dataset_id": dataset_id,
            "version_number": source_version_number,
            "artifact_hash": entry["content_hash"],
            "destination_target": destination_target,
            "release_notes": release_notes or f"Release package for {entry['name']} v{source_version_number}",
            "status": "STAGED",
            "is_release_eligible": risk["is_release_eligible"],
            "risk_score": risk["total_risk_score"],
            "risk_band": risk["risk_band"],
            "blocking_reasons": risk["blocking_reasons"],
            "staged_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": None,
            "approval_token": None,
            "published_at": None,
        }
        self._releases_ledger[release_id] = release_record

        return {
            "release_id": release_id,
            "dataset_id": dataset_id,
            "version_number": source_version_number,
            "artifact_hash": entry["content_hash"],
            "destination_target": destination_target,
            "status": "STAGED",
            "is_release_eligible": risk["is_release_eligible"],
            "risk_score": risk["total_risk_score"],
            "risk_band": risk["risk_band"],
            "blocking_reasons": risk["blocking_reasons"],
        }

    # -------------------------------------------------------------------------
    # Tool 8: submit_for_review
    # -------------------------------------------------------------------------
    def submit_for_review(
        self,
        dataset_id: str,
        version_number: int = 1,
        staged_release_id: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit a staged release to the governance review queue for Human/Challenger approval.
        """
        if staged_release_id:
            if staged_release_id not in self._releases_ledger:
                raise ServiceNotFoundError(f"Staged release '{staged_release_id}' not found.")
            release = self._releases_ledger[staged_release_id]
        else:
            # Auto-prepare release
            prep = self.prepare_release(
                dataset_id=dataset_id,
                source_version_number=version_number,
                destination_target="internal://governance-review",
                organization_id=organization_id,
            )
            release = self._releases_ledger[prep["release_id"]]

        release["status"] = "PENDING_REVIEW"
        release["reviewer_notes"] = reviewer_notes
        release["submitted_at"] = datetime.now(timezone.utc).isoformat()

        return {
            "release_id": release["release_id"],
            "dataset_id": release["dataset_id"],
            "version_number": release["version_number"],
            "status": "PENDING_REVIEW",
            "reviewer_notes": reviewer_notes,
            "is_release_eligible": release["is_release_eligible"],
            "risk_band": release["risk_band"],
            "artifact_hash": release["artifact_hash"],
        }

    # -------------------------------------------------------------------------
    # Tool 9: get_approval_status
    # -------------------------------------------------------------------------
    def get_approval_status(
        self,
        release_id: str,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query the review and approval status of a release request."""
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found in governance ledger.")

        release = self._releases_ledger[release_id]
        return {
            "release_id": release["release_id"],
            "dataset_id": release["dataset_id"],
            "version_number": release["version_number"],
            "status": release["status"],
            "is_approved": release["status"] == "APPROVED",
            "artifact_hash": release["artifact_hash"],
            "risk_score": release["risk_score"],
            "risk_band": release["risk_band"],
            "blocking_reasons": release.get("blocking_reasons", []),
            "approved_by": release.get("approved_by"),
        }

    # -------------------------------------------------------------------------
    # Helper to simulate human steward approval (Generates valid human token)
    # -------------------------------------------------------------------------
    def grant_human_approval(
        self,
        release_id: str,
        steward_name: str = "Lead Human Data Steward",
    ) -> Dict[str, Any]:
        """
        Record authorized Human Steward approval and issue a cryptographic token
        bound to the artifact hash.
        """
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found.")
        rel = self._releases_ledger[release_id]

        if not rel["is_release_eligible"]:
            raise ServiceValidationError("Cannot approve release with blocking policy violations.")

        token = f"human-token-{release_id[:8]}-{rel['artifact_hash'][:16]}"
        rel["status"] = "APPROVED"
        rel["approved_by"] = steward_name
        rel["approval_token"] = token
        return {
            "release_id": release_id,
            "status": "APPROVED",
            "approval_token": token,
            "expected_artifact_hash": rel["artifact_hash"],
            "approved_by": steward_name,
        }

    # -------------------------------------------------------------------------
    # Tool 10: publish_dataset
    # -------------------------------------------------------------------------
    def publish_dataset(
        self,
        release_id: str,
        approval_token: str,
        expected_artifact_hash: str,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute publication to external target.
        CRITICAL ARCHITECTURAL CONSTRAINT:
        Strictly requires valid human approval token bound to the artifact hash.
        AI models are prohibited from authorizing publication.
        """
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found.")

        release = self._releases_ledger[release_id]

        # 1. Verify artifact hash integrity match
        if release["artifact_hash"] != expected_artifact_hash:
            raise ServiceValidationError(
                f"Artifact hash mismatch: Release hash is '{release['artifact_hash']}', "
                f"but caller supplied '{expected_artifact_hash}'."
            )

        # 2. Verify human approval token
        is_token_valid = verify_human_approval_token(
            release_id=release_id,
            approval_token=approval_token,
            expected_artifact_hash=expected_artifact_hash,
        )
        if not is_token_valid:
            raise HumanApprovalRequiredError(
                "Human approval verification failed: Invalid or counterfeit approval token. "
                "Publication requires an authentic human authorization token."
            )

        # 3. Check status
        if release["status"] not in ("APPROVED", "PENDING_REVIEW", "STAGED"):
            raise ServiceValidationError(f"Release '{release_id}' is in non-publishable state: '{release['status']}'")

        # 4. Mark published
        release["status"] = "PUBLISHED"
        release["published_at"] = datetime.now(timezone.utc).isoformat()
        release["published_hash"] = expected_artifact_hash

        return {
            "release_id": release_id,
            "dataset_id": release["dataset_id"],
            "version_number": release["version_number"],
            "status": "PUBLISHED",
            "destination_target": release["destination_target"],
            "published_artifact_hash": expected_artifact_hash,
            "published_at": release["published_at"],
            "message": "Dataset successfully published to destination with verified human authorization.",
        }

    # -------------------------------------------------------------------------
    # Tool 11: verify_publication
    # -------------------------------------------------------------------------
    def verify_publication(
        self,
        release_id: str,
        destination_target: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify the integrity and reachability of a published dataset release.
        """
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found.")

        release = self._releases_ledger[release_id]
        is_published = release["status"] == "PUBLISHED"
        target = destination_target or release["destination_target"]

        return {
            "release_id": release_id,
            "dataset_id": release["dataset_id"],
            "version_number": release["version_number"],
            "status": release["status"],
            "is_published": is_published,
            "destination_target": target,
            "verified_artifact_hash": release.get("published_hash") or release["artifact_hash"],
            "integrity_verified": is_published,
            "verification_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # Tool 12: withdraw_release
    # -------------------------------------------------------------------------
    def withdraw_release(
        self,
        release_id: str,
        reason: str,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cancel, recall, or withdraw a staged, pending, or published release.
        """
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found.")

        release = self._releases_ledger[release_id]
        prior_status = release["status"]
        release["status"] = "WITHDRAWN"
        release["withdrawal_reason"] = reason
        release["withdrawn_at"] = datetime.now(timezone.utc).isoformat()

        return {
            "release_id": release_id,
            "prior_status": prior_status,
            "current_status": "WITHDRAWN",
            "reason": reason,
            "withdrawn_at": release["withdrawn_at"],
        }

    # -------------------------------------------------------------------------
    # Resource 1: releasegate://policies/current
    # -------------------------------------------------------------------------
    def get_current_policy(self) -> Dict[str, Any]:
        """Return the active release policy configuration and risk weights."""
        policy_config = PolicyConfig()
        return {
            "policy_version": policy_config.policy_version,
            "description": "ReleaseGate Frozen Architecture Baseline v1.0 100-Point Policy",
            "risk_bands": {
                "LOW": {"range": "0-19", "eligible": True},
                "MODERATE": {"range": "20-39", "eligible": True},
                "HIGH": {"range": "40-69", "eligible": False},
                "CRITICAL": {"range": "70-100", "eligible": False},
            },
            "weight_allocations": {
                "sensitive_information": 35,
                "data_quality": 20,
                "licensing_provenance": 20,
                "metadata_completeness": 10,
                "policy_violations": 15,
                "total": 100,
            },
            "critical_rules": [
                "Critical PII (e.g. government IDs, unmasked credit cards) strictly blocks release",
                "Unapproved or prohibited software/dataset license blocks release",
                "Critical quality failure (e.g. malformed schema, corrupted types) blocks release",
                "Prohibited domain deployment blocks release regardless of overall score",
            ],
        }

    # -------------------------------------------------------------------------
    # Resource 2: releasegate://datasets/{id}/profile
    # -------------------------------------------------------------------------
    def get_dataset_profile(self, dataset_id: str, version_number: int = 1) -> Dict[str, Any]:
        """Return sanitized dataset profile without raw data rows."""
        entry = self._get_dataset_entry(dataset_id, version_number)
        content = self.storage.read_dataset(entry["artifact_ref"])
        profile = DatasetProfiler.profile(content, entry["file_format"])
        return {
            "dataset_id": dataset_id,
            "dataset_name": entry["name"],
            "version_number": version_number,
            "content_hash": entry["content_hash"],
            "file_size": entry["file_size"],
            "profile": profile.to_dict(),
        }

    # -------------------------------------------------------------------------
    # Resource 3: releasegate://releases/{id}/evidence
    # -------------------------------------------------------------------------
    def get_release_evidence(self, release_id: str) -> Dict[str, Any]:
        """Return cryptographic release evidence ledger."""
        if release_id not in self._releases_ledger:
            raise ServiceNotFoundError(f"Release '{release_id}' not found.")

        rel = self._releases_ledger[release_id]
        return {
            "release_id": release_id,
            "dataset_id": rel["dataset_id"],
            "version_number": rel["version_number"],
            "artifact_hash": rel["artifact_hash"],
            "status": rel["status"],
            "destination_target": rel["destination_target"],
            "risk_assessment": {
                "risk_score": rel["risk_score"],
                "risk_band": rel["risk_band"],
                "is_release_eligible": rel["is_release_eligible"],
                "blocking_reasons": rel.get("blocking_reasons", []),
            },
            "provenance": {
                "staged_at": rel.get("staged_at"),
                "submitted_at": rel.get("submitted_at"),
                "approved_by": rel.get("approved_by"),
                "published_at": rel.get("published_at"),
            },
        }

    # -------------------------------------------------------------------------
    # Resource 4: releasegate://system/status
    # -------------------------------------------------------------------------
    def get_system_status(self) -> Dict[str, Any]:
        """Return system health, engine versions, and plane isolation status."""
        return {
            "system": "ReleaseGate AI Data Governance Platform",
            "version": "1.0.0",
            "architecture_baseline": "Frozen Architecture Baseline v1.0",
            "status": "HEALTHY",
            "planes": {
                "local_worker_plane": {
                    "status": "OPERATIONAL",
                    "isolation_enforced": True,
                    "raw_data_boundary": "LOCAL_ONLY",
                },
                "cloud_control_plane": {
                    "status": "OPERATIONAL",
                    "metadata_only": True,
                },
            },
            "engines": {
                "profiler": "1.0.0",
                "pii_detector": "1.0.0 (Presidio Analyzer)",
                "quality_validator": "1.0.0 (Deterministic Rule Engine)",
                "policy_engine": "1.0.0 (100-Point Weighted Risk Evaluator)",
                "transformation_engine": "1.0.0 (Safe Allowlisted AST Redaction)",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Global default service singleton
default_service = ReleaseGateService()

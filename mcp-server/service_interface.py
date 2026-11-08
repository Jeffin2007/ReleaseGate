"""
Service interface between the MCP layer and ReleaseGate capabilities.

This module is the only place in ``mcp-server/`` that touches the local
filesystem (through ``DatasetStoragePort``) or the inspection engines. MCP tools
and resources receive plain arguments, call a method here, and serialize the
sanitized response. No MCP handler imports SQLAlchemy, opens a path, runs a
query, or evaluates code.

Tenant isolation is enforced on every read and write: dataset and release
records are keyed by organization, and a lookup from another organization fails
with the same "not found" response as a genuinely missing record.

Publication authorization is delegated to ``HumanApprovalAuthority``. The
service refuses to publish unless a human approval record exists for the exact
release, artifact hash, and organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
import re
import secrets
import threading
from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pandas as pd

from engines.dataset_profiler import DatasetProfiler
from engines.pii_detector import PIIDetector, PIIDetectorConfig
from engines.policy_engine import PolicyConfig, PolicyEngine
from engines.quality_validator import (
    ColumnRule,
    DatasetLevelRules,
    QualitySeverity,
    QualityValidationConfig,
    QualityValidator,
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
    TransformationEngineError,
    TransformationSpec,
)

from local_worker.secure_storage import LocalDatasetStorage

from mcp_server.security.approvals import (
    HumanApprovalAuthority,
    HumanApprovalRecord,
)


class ServiceNotFoundError(Exception):
    """Raised when a record does not exist for the caller's organization."""


class ServiceValidationError(Exception):
    """Raised when a request is well-formed but cannot be satisfied safely."""


class DatasetStoragePort(Protocol):
    """Storage boundary; implementations may be local, encrypted, or remote."""

    def store_dataset(
        self,
        dataset_id: UUID,
        version_number: int,
        content: bytes,
        ext: str,
    ) -> Tuple[str, int, str]:
        ...

    def read_dataset(self, artifact_ref: str) -> bytes:
        ...


@dataclass(frozen=True)
class DatasetRecord:
    """A dataset version registered for one organization."""

    organization_id: str
    dataset_id: str
    version_number: int
    artifact_ref: str
    file_format: str
    file_size: int
    content_hash: str
    name: str
    description: str
    provenance: Dict[str, Any]
    registered_at: str


@dataclass
class ReleaseRecord:
    """Governance lifecycle record for a staged release."""

    release_id: str
    organization_id: str
    dataset_id: str
    version_number: int
    artifact_hash: str
    destination_target: str
    release_notes: str
    status: str
    is_release_eligible: bool
    risk_score: float
    risk_band: str
    blocking_reasons: List[str] = field(default_factory=list)
    reviewer_notes: Optional[str] = None
    submitted_at: Optional[str] = None
    staged_at: str = ""
    published_at: Optional[str] = None
    published_hash: Optional[str] = None
    withdrawn_at: Optional[str] = None
    withdrawal_reason: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        return {
            "release_id": self.release_id,
            "dataset_id": self.dataset_id,
            "version_number": self.version_number,
            "artifact_hash": self.artifact_hash,
            "destination_target": self.destination_target,
            "status": self.status,
            "is_release_eligible": self.is_release_eligible,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "blocking_reasons": self.blocking_reasons,
            "reviewer_notes": self.reviewer_notes,
            "staged_at": self.staged_at,
            "submitted_at": self.submitted_at,
            "published_at": self.published_at,
        }


_ORG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_ALLOWED_POLICY_VERSION = PolicyConfig().policy_version
_MAX_PROPOSALS = 500


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReleaseGateService:
    """Organization-scoped governance service behind the MCP tools."""

    def __init__(
        self,
        storage: Optional[DatasetStoragePort] = None,
        approval_authority: Optional[HumanApprovalAuthority] = None,
        transformation_engine: Optional[TransformationEngine] = None,
        pseudonym_secret: Optional[str] = None,
        approval_ttl_seconds: Optional[int] = None,
    ) -> None:
        self._storage: DatasetStoragePort = storage or LocalDatasetStorage()
        self._policy_engine = PolicyEngine()
        effective_ttl = approval_ttl_seconds
        if effective_ttl is None:
            try:
                effective_ttl = int(os.environ.get("RELEASEGATE_APPROVAL_TTL_SECONDS", "900"))
            except ValueError:
                effective_ttl = 900
        self._approvals = approval_authority or HumanApprovalAuthority(
            ttl_seconds=effective_ttl
        )
        self._transformation_engine = transformation_engine or TransformationEngine()
        self._pseudonym_secret = (
            pseudonym_secret
            or os.environ.get("RELEASEGATE_PSEUDONYMIZATION_SECRET")
            or secrets.token_hex(32)
        )
        self._datasets: Dict[Tuple[str, str, int], DatasetRecord] = {}
        self._releases: Dict[str, ReleaseRecord] = {}
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration (local worker / trusted control channel)
    # ------------------------------------------------------------------
    def register_dataset_artifact(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        content: bytes,
        version_number: int = 1,
        file_format: str = "csv",
        name: Optional[str] = None,
        description: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> DatasetRecord:
        """Store a dataset version for one organization. Never exposed as an MCP tool."""
        self._require_organization(organization_id)
        dataset_uuid = self._parse_dataset_uuid(dataset_id)
        clean_format = file_format.lower().lstrip(".")
        if not content:
            raise ServiceValidationError("Dataset content cannot be empty.")
        if clean_format not in {"csv", "json", "xlsx", "parquet"}:
            raise ServiceValidationError(f"Unsupported dataset format: {file_format!r}")

        storage_uuid = uuid5(NAMESPACE_URL, f"releasegate:{organization_id}:{dataset_uuid}")
        try:
            artifact_ref, byte_size, content_hash = self._storage.store_dataset(
                dataset_id=storage_uuid,
                version_number=version_number,
                content=content,
                ext=clean_format,
            )
        except Exception as exc:  # storage details stay behind the boundary
            raise ServiceValidationError(
                "Local dataset storage rejected the artifact."
            ) from exc

        record = DatasetRecord(
            organization_id=organization_id,
            dataset_id=str(dataset_uuid),
            version_number=version_number,
            artifact_ref=artifact_ref,
            file_format=clean_format,
            file_size=byte_size,
            content_hash=content_hash,
            name=(name or f"dataset_{str(dataset_uuid)[:8]}").strip()[:200],
            description=(description or "Registered in ReleaseGate").strip()[:500],
            provenance=dict(provenance or {"license": "MIT", "has_license": True, "is_approved": True}),
            registered_at=_utcnow_iso(),
        )
        with self._lock:
            self._datasets[(organization_id, record.dataset_id, version_number)] = record
        return record

    # ------------------------------------------------------------------
    # Tool 1: inspect_dataset
    # ------------------------------------------------------------------
    def inspect_dataset(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, version_number)
        return self._execute_inspection(record, domain=domain)

    def _execute_inspection(
        self, record: DatasetRecord, domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compose the deterministic local engines without importing the API plane's
        ORM schemas. The MCP service must remain free of database dependencies.
        """
        started_at = datetime.now(timezone.utc)
        content = self._read_artifact(record)
        try:
            df = DatasetProfiler.load_dataframe(content, record.file_format)
            profiling = DatasetProfiler.profile(content, record.file_format)
            pii_report = PIIDetector().scan_dataframe(
                df=df,
                dataset_id=record.dataset_id,
                version_number=record.version_number,
            )
            quality_report = QualityValidator().validate_dataframe(
                df=df,
                dataset_id=record.dataset_id,
                version_number=record.version_number,
            )
            policy_metadata = {
                "dataset_name": record.name,
                "description": record.description,
                "file_size": record.file_size,
                "content_hash": record.content_hash,
                "intended_use": "internal_release_governance",
                "domain": domain or "general_analytics",
                "data_custodian": "release_steward",
                **profiling.to_dict(),
            }
            policy_result = self._policy_engine.evaluate(
                dataset_id=record.dataset_id,
                version_number=record.version_number,
                pii_report=pii_report,
                quality_report=quality_report,
                metadata=policy_metadata,
                provenance=record.provenance,
                context={
                    "domain": domain or "internal_analytics",
                    "has_retention_policy": True,
                },
            )
        except Exception as exc:
            raise ServiceValidationError("Dataset inspection failed.") from exc

        findings: List[Dict[str, Any]] = []
        for finding in pii_report.findings:
            findings.append(
                {
                    "finding_type": "PII",
                    "category": finding.entity_type,
                    "column_name": finding.column_name,
                    "severity": finding.severity.value,
                    "occurrence_count": finding.occurrence_count,
                    "confidence_score": round(finding.confidence, 4),
                    "message": (
                        f"Detected {finding.occurrence_count} sensitive {finding.entity_type} "
                        f"instance(s) in column '{finding.column_name}'."
                    ),
                    "evidence_ref": finding.evidence_ref.model_dump(),
                }
            )
        for issue in quality_report.issues:
            findings.append(
                {
                    "finding_type": "QUALITY",
                    "category": issue.rule_name,
                    "column_name": issue.column_name,
                    "severity": issue.severity.value,
                    "occurrence_count": issue.violating_count,
                    "confidence_score": 1.0,
                    "message": issue.message,
                    "evidence_ref": issue.evidence_ref.model_dump(),
                }
            )

        risk = policy_result.score_breakdown
        summary_report = {
            "risk_assessment": {
                "total_risk_score": risk.total_risk_score,
                "risk_band": risk.risk_band.value,
                "is_release_eligible": policy_result.is_release_eligible,
                "status": policy_result.status.value,
                "blocking_reasons": policy_result.blocking_reasons,
                "warnings": policy_result.warnings,
                "category_scores": {
                    "sensitive_information": risk.sensitive_information.score,
                    "data_quality": risk.data_quality.score,
                    "licensing_provenance": risk.licensing_provenance.score,
                    "metadata_completeness": risk.metadata_completeness.score,
                    "policy_violations": risk.policy_violations.score,
                },
            },
            "profiling": profiling.to_dict(),
            "privacy_inspection": {
                "total_findings": len(pii_report.findings),
                "has_critical_pii": pii_report.has_critical_pii,
                "has_high_pii": pii_report.has_high_pii,
                "scanned_columns": len(pii_report.columns),
                "detected_entities": sorted(
                    {finding.entity_type for finding in pii_report.findings}
                ),
            },
            "quality_inspection": {
                "quality_score": quality_report.summary.quality_score,
                "total_rules_evaluated": quality_report.summary.total_rules_evaluated,
                "passed_rules_count": quality_report.summary.passed_rules_count,
                "failed_rules_count": quality_report.summary.failed_rules_count,
                "has_critical_failures": quality_report.summary.has_critical_failures,
                "has_high_failures": quality_report.summary.has_high_failures,
                "affected_columns": quality_report.summary.affected_columns,
            },
            "governance": {
                "policy_version": policy_result.policy_version,
                "evaluated_at_utc": policy_result.evaluated_at_utc,
            },
        }

        return {
            "dataset_id": record.dataset_id,
            "dataset_version_id": str(uuid4()),
            "version_number": record.version_number,
            "inspection_type": "FULL_SCAN",
            "status": "COMPLETED",
            "risk_score": risk.total_risk_score,
            "risk_band": risk.risk_band.value,
            "policy_version": policy_result.policy_version,
            "is_release_eligible": policy_result.is_release_eligible,
            "summary_report": summary_report,
            "findings_count": len(findings),
            "findings": findings,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Tool 2: detect_sensitive_data
    # ------------------------------------------------------------------
    def detect_sensitive_data(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        confidence_threshold: float = 0.6,
        entities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, version_number)
        df = self._load_dataframe(record)
        try:
            detector = PIIDetector(
                config=PIIDetectorConfig(
                    confidence_threshold=confidence_threshold,
                    supported_entities=entities,
                )
            )
            report = detector.scan_dataframe(
                df=df,
                dataset_id=record.dataset_id,
                version_number=record.version_number,
            )
        except Exception as exc:
            raise ServiceValidationError("Sensitive data detection failed.") from exc

        return {
            "dataset_id": record.dataset_id,
            "version_number": record.version_number,
            "total_findings": len(report.findings),
            "has_critical_pii": report.has_critical_pii,
            "has_high_pii": report.has_high_pii,
            "scanned_columns": len(report.columns),
            "detected_entities": sorted({finding.entity_type for finding in report.findings}),
            "findings": [
                {
                    "entity_type": finding.entity_type,
                    "column_name": finding.column_name,
                    "occurrence_count": finding.occurrence_count,
                    "severity": finding.severity.value,
                    "confidence": round(finding.confidence, 4),
                    "evidence_ref": finding.evidence_ref.model_dump(),
                }
                for finding in report.findings
            ],
        }

    # ------------------------------------------------------------------
    # Tool 3: validate_data_quality
    # ------------------------------------------------------------------
    def validate_data_quality(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        allow_nulls: Optional[bool] = None,
        allow_duplicates: Optional[bool] = None,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, version_number)
        df = self._load_dataframe(record)

        dataset_rules = DatasetLevelRules(
            no_duplicate_rows=False if allow_duplicates is True else True
        )
        column_rules: List[ColumnRule] = []
        if allow_nulls is not None:
            column_rules = [
                ColumnRule(
                    column_name=str(column),
                    allow_null=allow_nulls,
                    severity=QualitySeverity.HIGH,
                )
                for column in df.columns
            ]
        config = QualityValidationConfig(
            dataset_rules=dataset_rules,
            column_rules=column_rules,
        )
        try:
            report = QualityValidator(config=config).validate_dataframe(
                df=df,
                dataset_id=record.dataset_id,
                version_number=record.version_number,
            )
        except Exception as exc:
            raise ServiceValidationError("Data quality validation failed.") from exc

        summary = report.summary
        return {
            "dataset_id": record.dataset_id,
            "version_number": record.version_number,
            "quality_score": summary.quality_score,
            "passed_rules_count": summary.passed_rules_count,
            "failed_rules_count": summary.failed_rules_count,
            "has_critical_failures": summary.has_critical_failures,
            "has_high_failures": summary.has_high_failures,
            "affected_columns": summary.affected_columns,
            "issues": [
                {
                    "rule_name": issue.rule_name,
                    "rule_type": issue.rule_type.value,
                    "column_name": issue.column_name,
                    "severity": issue.severity.value,
                    "violating_count": issue.violating_count,
                    "violating_percentage": issue.violating_percentage,
                    "message": issue.message,
                    "evidence_ref": issue.evidence_ref.model_dump(),
                }
                for issue in report.issues
            ],
        }

    # ------------------------------------------------------------------
    # Tool 4: check_release_policy
    # ------------------------------------------------------------------
    def check_release_policy(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        if policy_version != _ALLOWED_POLICY_VERSION:
            raise ServiceValidationError(
                f"Policy version {policy_version!r} is not available; "
                f"the active policy is {_ALLOWED_POLICY_VERSION}."
            )
        inspection = self.inspect_dataset(
            organization_id=organization_id,
            dataset_id=dataset_id,
            version_number=version_number,
            domain=domain,
        )
        risk = inspection["summary_report"]["risk_assessment"]
        return {
            "dataset_id": inspection["dataset_id"],
            "version_number": inspection["version_number"],
            "policy_version": inspection["policy_version"],
            "domain": domain or "general_analytics",
            "is_release_eligible": risk["is_release_eligible"],
            "risk_score": risk["total_risk_score"],
            "risk_band": risk["risk_band"],
            "status": risk["status"],
            "blocking_reasons": risk["blocking_reasons"],
            "warnings": risk["warnings"],
            "category_scores": risk["category_scores"],
        }

    # ------------------------------------------------------------------
    # Tool 5: generate_risk_report
    # ------------------------------------------------------------------
    def generate_risk_report(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        policy_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        if policy_version != _ALLOWED_POLICY_VERSION:
            raise ServiceValidationError(
                f"Policy version {policy_version!r} is not available; "
                f"the active policy is {_ALLOWED_POLICY_VERSION}."
            )
        inspection = self.inspect_dataset(
            organization_id=organization_id,
            dataset_id=dataset_id,
            version_number=version_number,
        )
        record = self._get_dataset(organization_id, dataset_id, version_number)
        summary = inspection["summary_report"]
        return {
            "report_id": str(uuid4()),
            "dataset_id": record.dataset_id,
            "dataset_name": record.name,
            "version_number": record.version_number,
            "policy_version": inspection["policy_version"],
            "generated_at_utc": _utcnow_iso(),
            "content_hash": record.content_hash,
            "risk_assessment": summary["risk_assessment"],
            "profiling_summary": summary["profiling"],
            "privacy_summary": summary["privacy_inspection"],
            "quality_summary": summary["quality_inspection"],
            "total_findings": inspection["findings_count"],
        }

    # ------------------------------------------------------------------
    # Tool 6: propose_transformation
    # ------------------------------------------------------------------
    def propose_transformation(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        operations: List[Dict[str, Any]],
        rationale: str,
        version_number: int = 1,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, version_number)
        df = self._load_dataframe(record)
        spec = self._build_transformation_spec(
            organization_id=organization_id,
            dataset_id=record.dataset_id,
            operations=operations,
            rationale=rationale,
        )
        try:
            _preview_df, provenance, preview = self._transformation_engine.apply_transformations(
                df=df,
                spec=spec,
                dataset_id=record.dataset_id,
                input_version=record.version_number,
                output_version=record.version_number + 1,
                input_hash=record.content_hash,
                input_artifact_ref=record.artifact_ref,
            )
        except TransformationEngineError as exc:
            raise ServiceValidationError("Transformation proposal is invalid.") from exc
        except Exception as exc:
            raise ServiceValidationError("Transformation simulation failed.") from exc

        proposal_id = f"prop_{uuid4().hex[:16]}"
        result = {
            "proposal_id": proposal_id,
            "dataset_id": record.dataset_id,
            "base_version": record.version_number,
            "target_version": record.version_number + 1,
            "rationale": rationale,
            "operations_count": len(operations),
            "preview": preview.model_dump(),
            "simulated_output_hash": provenance.output_hash,
            "status": "PROPOSED",
        }
        with self._lock:
            self._proposals[proposal_id] = {
                "proposal_id": proposal_id,
                "organization_id": organization_id,
                "dataset_id": record.dataset_id,
                "base_version": record.version_number,
                "simulated_output_hash": provenance.output_hash,
                "operations_count": len(operations),
            }
            if len(self._proposals) > _MAX_PROPOSALS:
                for stale_key in list(self._proposals)[: len(self._proposals) - _MAX_PROPOSALS]:
                    self._proposals.pop(stale_key, None)
        return result

    # ------------------------------------------------------------------
    # Tool 7: prepare_release
    # ------------------------------------------------------------------
    def prepare_release(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        source_version_number: int = 1,
        destination_target: str,
        release_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, source_version_number)
        inspection = self.inspect_dataset(
            organization_id=organization_id,
            dataset_id=record.dataset_id,
            version_number=record.version_number,
        )
        risk = inspection["summary_report"]["risk_assessment"]
        release = ReleaseRecord(
            release_id=f"rel_{secrets.token_hex(6)}",
            organization_id=organization_id,
            dataset_id=record.dataset_id,
            version_number=record.version_number,
            artifact_hash=record.content_hash,
            destination_target=destination_target,
            release_notes=(release_notes or "Release package")[:1000],
            status="STAGED",
            is_release_eligible=bool(risk["is_release_eligible"]),
            risk_score=float(risk["total_risk_score"]),
            risk_band=str(risk["risk_band"]),
            blocking_reasons=list(risk["blocking_reasons"]),
            staged_at=_utcnow_iso(),
        )
        with self._lock:
            self._releases[release.release_id] = release
        return {
            **release.public_dict(),
            "approval_required": True,
            "message": (
                "Release staged with a hash-bound evidence baseline. Submission for review "
                "and an out-of-band human approval are required before publication."
            ),
        }

    # ------------------------------------------------------------------
    # Tool 8: submit_for_review
    # ------------------------------------------------------------------
    def submit_for_review(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
        staged_release_id: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if staged_release_id is not None:
            release = self._get_release(organization_id, staged_release_id)
            if release.dataset_id != str(self._parse_dataset_uuid(dataset_id)):
                raise ServiceValidationError("The staged release does not belong to this dataset.")
            if release.version_number != version_number:
                raise ServiceValidationError("The staged release does not match this dataset version.")
        else:
            prepared = self.prepare_release(
                organization_id=organization_id,
                dataset_id=dataset_id,
                source_version_number=version_number,
                destination_target="internal://governance-review",
                release_notes=reviewer_notes,
            )
            release = self._get_release(organization_id, prepared["release_id"])

        with self._lock:
            if release.status not in ("STAGED", "PENDING_REVIEW"):
                raise ServiceValidationError(
                    f"Release '{release.release_id}' cannot be submitted for review from "
                    f"status '{release.status}'."
                )
            release.status = "PENDING_REVIEW"
            release.reviewer_notes = (reviewer_notes or release.reviewer_notes or "")[:1000] or None
            release.submitted_at = release.submitted_at or _utcnow_iso()

        return {
            **release.public_dict(),
            "approval_required": True,
            "message": (
                "Release submitted for independent review. AI cannot authorize publication; "
                "a human steward must create the hash-bound approval record."
            ),
        }

    # ------------------------------------------------------------------
    # Tool 9: get_approval_status
    # ------------------------------------------------------------------
    def get_approval_status(
        self,
        *,
        organization_id: str,
        release_id: str,
    ) -> Dict[str, Any]:
        release = self._get_release(organization_id, release_id)
        active = self._approvals.find_active_for_release(
            release_id=release.release_id,
            artifact_hash=release.artifact_hash,
            organization_id=organization_id,
        )
        return {
            **release.public_dict(),
            "is_approved": active is not None,
            "approval": self._approvals.describe(active) if active else None,
            "publishable": (
                release.status == "PENDING_REVIEW"
                and release.is_release_eligible
                and active is not None
            ),
        }

    # ------------------------------------------------------------------
    # Tool 10: publish_dataset
    # ------------------------------------------------------------------
    def publish_dataset(
        self,
        *,
        organization_id: str,
        release_id: str,
        approval_id: str,
        expected_artifact_hash: str,
    ) -> Dict[str, Any]:
        release = self._get_release(organization_id, release_id)
        expected_hash = expected_artifact_hash.strip().lower()
        if release.artifact_hash != expected_hash:
            raise ServiceValidationError(
                "Artifact hash mismatch: the supplied hash does not match the release evidence."
            )

        # Hold the lifecycle lock across authorization and the state transition so
        # a concurrent withdrawal cannot land between verification and publication.
        with self._lock:
            if release.status == "PUBLISHED":
                if release.published_hash == expected_hash:
                    return self._published_response(release)
                raise ServiceValidationError(
                    "Release is already published with a different artifact hash."
                )

            if release.status != "PENDING_REVIEW":
                raise ServiceValidationError(
                    "Release must be submitted for review before publication."
                )
            if not release.is_release_eligible:
                raise ServiceValidationError(
                    "Release is blocked by policy and cannot be published."
                )

            approval = self._approvals.verify(
                approval_id=approval_id,
                release_id=release.release_id,
                artifact_hash=release.artifact_hash,
                organization_id=organization_id,
            )

            release.status = "PUBLISHED"
            release.published_at = _utcnow_iso()
            release.published_hash = expected_hash
        response = self._published_response(release)
        response["approval"] = self._approvals.describe(approval)
        return response

    # ------------------------------------------------------------------
    # Tool 11: verify_publication
    # ------------------------------------------------------------------
    def verify_publication(
        self,
        *,
        organization_id: str,
        release_id: str,
        destination_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        release = self._get_release(organization_id, release_id)
        target = destination_target or release.destination_target
        if destination_target is not None and destination_target != release.destination_target:
            raise ServiceValidationError(
                "Destination mismatch: the release was published to a different target."
            )
        is_published = release.status == "PUBLISHED"
        hash_match = bool(
            is_published
            and release.published_hash is not None
            and release.published_hash == release.artifact_hash
        )
        return {
            "release_id": release.release_id,
            "dataset_id": release.dataset_id,
            "version_number": release.version_number,
            "status": release.status,
            "is_published": is_published,
            "destination_target": target,
            "verified_artifact_hash": release.published_hash or release.artifact_hash,
            "integrity_verified": hash_match,
            "verification_timestamp": _utcnow_iso(),
        }

    # ------------------------------------------------------------------
    # Tool 12: withdraw_release
    # ------------------------------------------------------------------
    def withdraw_release(
        self,
        *,
        organization_id: str,
        release_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        release = self._get_release(organization_id, release_id)
        with self._lock:
            prior_status = release.status
            if release.status != "WITHDRAWN":
                release.status = "WITHDRAWN"
                release.withdrawn_at = _utcnow_iso()
                release.withdrawal_reason = reason
        self._approvals.revoke_for_release(
            release_id=release.release_id, organization_id=organization_id
        )
        return {
            "release_id": release.release_id,
            "prior_status": prior_status,
            "current_status": release.status,
            "reason": reason,
            "withdrawn_at": release.withdrawn_at,
        }

    # ------------------------------------------------------------------
    # Resource 1: releasegate://policies/current
    # ------------------------------------------------------------------
    def get_current_policy(self) -> Dict[str, Any]:
        policy = PolicyConfig()
        return {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "policy_name": policy.policy_name,
            "description": policy.description,
            "max_acceptable_score": policy.max_acceptable_score,
            "risk_bands": {
                "LOW": {"range": "0-19.99", "release_eligible": True},
                "MODERATE": {"range": "20-39.99", "release_eligible": True},
                "HIGH": {"range": "40-69.99", "release_eligible": False},
                "CRITICAL": {"range": "70-100", "release_eligible": False},
            },
            "weight_allocations": {
                "sensitive_information": policy.sensitive_info.max_points,
                "data_quality": policy.data_quality.max_points,
                "licensing_provenance": policy.licensing_provenance.max_points,
                "metadata_completeness": policy.metadata_completeness.max_points,
                "policy_violations": policy.policy_violations.max_points,
                "total": 100.0,
            },
            "critical_rules": [
                "Critical PII blocks release regardless of aggregate score",
                "Forbidden or unapproved licenses block release",
                "Critical data quality failures block release",
                "Prohibited deployment domains block release",
            ],
            "human_authorization": {
                "ai_may_authorize_publication": False,
                "approval_binds_to": "sha256_artifact_hash",
            },
        }

    # ------------------------------------------------------------------
    # Resource 2: releasegate://datasets/{id}/profile
    # ------------------------------------------------------------------
    def get_dataset_profile(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        version_number: int = 1,
    ) -> Dict[str, Any]:
        record = self._get_dataset(organization_id, dataset_id, version_number)
        content = self._read_artifact(record)
        try:
            profile = DatasetProfiler.profile(content, record.file_format)
        except Exception as exc:
            raise ServiceValidationError("Dataset profiling failed.") from exc
        return {
            "dataset_id": record.dataset_id,
            "dataset_name": record.name,
            "version_number": record.version_number,
            "content_hash": record.content_hash,
            "file_size": record.file_size,
            "profile": profile.to_dict(),
        }

    # ------------------------------------------------------------------
    # Resource 3: releasegate://releases/{id}/evidence
    # ------------------------------------------------------------------
    def get_release_evidence(
        self,
        *,
        organization_id: str,
        release_id: str,
    ) -> Dict[str, Any]:
        release = self._get_release(organization_id, release_id)
        approvals = self._approvals.list_for_release(
            release_id=release.release_id, organization_id=organization_id
        )
        return {
            "release_id": release.release_id,
            "dataset_id": release.dataset_id,
            "version_number": release.version_number,
            "artifact_hash": release.artifact_hash,
            "status": release.status,
            "destination_target": release.destination_target,
            "risk_assessment": {
                "risk_score": release.risk_score,
                "risk_band": release.risk_band,
                "is_release_eligible": release.is_release_eligible,
                "blocking_reasons": release.blocking_reasons,
            },
            "approval_records": [self._approvals.describe(record) for record in approvals],
            "provenance": {
                "staged_at": release.staged_at,
                "submitted_at": release.submitted_at,
                "published_at": release.published_at,
                "withdrawn_at": release.withdrawn_at,
            },
        }

    # ------------------------------------------------------------------
    # Resource 4: releasegate://system/status
    # ------------------------------------------------------------------
    def get_system_status(self) -> Dict[str, Any]:
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
            "mcp_server": {
                "database_access": "NONE",
                "filesystem_access": "SERVICE_LAYER_ONLY",
                "arbitrary_code_execution": "PROHIBITED",
                "publication_authorization": "HUMAN_ONLY",
                "identity_source": "SERVER_SESSION",
            },
            "engines": {
                "profiler": "1.0.0",
                "pii_detector": "1.0.0 (Presidio Analyzer)",
                "quality_validator": "1.0.0 (Deterministic Rule Engine)",
                "policy_engine": "1.0.0 (100-Point Weighted Risk Evaluator)",
                "transformation_engine": "1.0.0 (Allowlisted Declarative Operations)",
            },
            "timestamp": _utcnow_iso(),
        }

    # ------------------------------------------------------------------
    # Trusted human approval channel (never exposed as an MCP tool)
    # ------------------------------------------------------------------
    def record_human_approval(
        self,
        *,
        organization_id: str,
        release_id: str,
        artifact_hash: str,
        approver_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> HumanApprovalRecord:
        """
        Register a human steward approval for one exact artifact hash.

        Called by the control plane after a human sign-off, never by the model.
        """
        with self._lock:
            release = self._get_release(organization_id, release_id)
            if release.status != "PENDING_REVIEW":
                raise ServiceValidationError(
                    "A release must be submitted for review before a human can approve it."
                )
            if not release.is_release_eligible:
                raise ServiceValidationError("A policy-blocked release cannot be approved.")
            if artifact_hash.strip().lower() != release.artifact_hash:
                raise ServiceValidationError(
                    "Approval hash does not match the staged release artifact."
                )
            return self._approvals.record_human_approval(
                release_id=release.release_id,
                artifact_hash=release.artifact_hash,
                organization_id=organization_id,
                approver_id=approver_id,
                approver_type="HUMAN",
                ttl_seconds=ttl_seconds,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _require_organization(organization_id: str) -> str:
        value = (organization_id or "").strip()
        if not _ORG_PATTERN.fullmatch(value):
            raise ServiceValidationError("A valid organization scope is required.")
        return value

    @staticmethod
    def _parse_dataset_uuid(dataset_id: str) -> UUID:
        try:
            return UUID(str(dataset_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ServiceValidationError("dataset_id must be a valid UUID.") from exc

    def _get_dataset(self, organization_id: str, dataset_id: str, version_number: int) -> DatasetRecord:
        self._require_organization(organization_id)
        dataset_uuid = str(self._parse_dataset_uuid(dataset_id))
        record = self._datasets.get((organization_id, dataset_uuid, int(version_number)))
        if record is None:
            raise ServiceNotFoundError("Dataset version not found for this organization.")
        return record

    def _get_release(self, organization_id: str, release_id: str) -> ReleaseRecord:
        self._require_organization(organization_id)
        release = self._releases.get(release_id)
        if release is None or release.organization_id != organization_id:
            raise ServiceNotFoundError("Release not found for this organization.")
        return release

    def _read_artifact(self, record: DatasetRecord) -> bytes:
        try:
            return self._storage.read_dataset(record.artifact_ref)
        except Exception as exc:
            raise ServiceValidationError(
                "Local dataset artifact is unavailable or failed its integrity check."
            ) from exc

    def _load_dataframe(self, record: DatasetRecord) -> pd.DataFrame:
        content = self._read_artifact(record)
        try:
            return DatasetProfiler.load_dataframe(content, record.file_format)
        except Exception as exc:
            raise ServiceValidationError("Dataset could not be parsed locally.") from exc

    def _pseudonym_salt(self, organization_id: str, dataset_id: str) -> str:
        return hashlib.sha256(
            f"{self._pseudonym_secret}:{organization_id}:{dataset_id}".encode("utf-8")
        ).hexdigest()

    def _build_transformation_spec(
        self,
        *,
        organization_id: str,
        dataset_id: str,
        operations: List[Dict[str, Any]],
        rationale: str,
    ) -> TransformationSpec:
        typed_operations = []
        for operation in operations:
            name = operation.get("operation")
            column = operation.get("column")
            if not isinstance(column, str) or not column:
                raise ServiceValidationError("Every transformation operation needs a column.")

            if name == "remove_column":
                typed_operations.append(RemoveColumnOp(column_name=column))
            elif name == "mask_column":
                try:
                    strategy = MaskingStrategy(str(operation.get("strategy", "full_redaction")).upper())
                except ValueError as exc:
                    raise ServiceValidationError("Unsupported masking strategy.") from exc
                typed_operations.append(
                    MaskColumnOp(
                        column_name=column,
                        strategy=strategy,
                        placeholder=operation.get("placeholder", "[REDACTED]"),
                    )
                )
            elif name == "pseudonymize_column":
                typed_operations.append(
                    PseudonymizeColumnOp(
                        column_name=column,
                        prefix=operation.get("prefix", "PSEUDO_"),
                    )
                )
            elif name == "generalize_column":
                try:
                    strategy = GeneralizationStrategy(
                        str(operation.get("strategy")).upper()
                    )
                except ValueError as exc:
                    raise ServiceValidationError("Unsupported generalization strategy.") from exc
                typed_operations.append(
                    GeneralizeColumnOp(
                        column_name=column,
                        strategy=strategy,
                        bins=operation.get("bins"),
                        bin_labels=operation.get("bin_labels"),
                        date_interval=operation.get("date_interval"),
                        category_mapping=operation.get("category_mapping"),
                    )
                )
            elif name == "filter_rows":
                try:
                    operator = FilterOperator(str(operation.get("operator")).upper())
                except ValueError as exc:
                    raise ServiceValidationError("Unsupported filter operator.") from exc
                typed_operations.append(
                    FilterRowsOp(
                        column_name=column,
                        operator=operator,
                        value=operation.get("value"),
                        values_list=operation.get("values_list"),
                    )
                )
            else:
                raise ServiceValidationError("Prohibited transformation operation.")

        if not typed_operations:
            raise ServiceValidationError("At least one transformation operation is required.")

        return TransformationSpec(
            description=rationale,
            operations=typed_operations,
            global_salt=self._pseudonym_salt(organization_id, dataset_id),
        )

    def _published_response(self, release: ReleaseRecord) -> Dict[str, Any]:
        return {
            "release_id": release.release_id,
            "dataset_id": release.dataset_id,
            "version_number": release.version_number,
            "status": "PUBLISHED",
            "destination_target": release.destination_target,
            "published_artifact_hash": release.published_hash,
            "published_at": release.published_at,
            "message": (
                "Release marked PUBLISHED for the approved destination after verifying "
                "a human authorization bound to the artifact hash. Destination transfer "
                "is performed by the trusted local-worker/control-plane adapter."
            ),
        }


__all__ = [
    "DatasetRecord",
    "DatasetStoragePort",
    "ReleaseGateService",
    "ReleaseRecord",
    "ServiceNotFoundError",
    "ServiceValidationError",
]

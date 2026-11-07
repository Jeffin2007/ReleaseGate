"""
Deterministic Release Policy and Risk Engine.
Evaluates dataset eligibility across five explicit weighted categories (100 points total):
1. Sensitive information (35 points)
2. Data quality (20 points)
3. Licensing & provenance (20 points)
4. Metadata completeness (10 points)
5. Policy violations (15 points)

Enforces hard blocking overrides for critical policy violations regardless of aggregate score.
All calculations are 100% deterministic and reproducible.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid

from .config import PolicyConfig
from .schemas import (
    CategoryScore,
    EvaluationStatus,
    PolicyEvaluationResult,
    RiskBand,
    ScoreBreakdown,
    compute_risk_band,
    generate_policy_evidence_hash,
)


class PolicyEngine:
    """
    Evaluates dataset readiness and risk using versioned, deterministic governance policies.
    """

    def __init__(self, policy_config: Optional[PolicyConfig] = None) -> None:
        self.config = policy_config or PolicyConfig()

    def _eval_sensitive_info(
        self,
        pii_report: Optional[Union[Dict[str, Any], Any]],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> CategoryScore:
        """Category 1: Sensitive Information (35 points max)."""
        max_pts = self.config.sensitive_info.max_points

        if pii_report is None:
            blocking_reasons.append(
                "Missing PII inspection evidence: Dataset has not undergone deterministic privacy scanning."
            )
            return CategoryScore(
                category_name="sensitive_information",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=35.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Missing privacy evaluation evidence (fail-closed security).",
                evidence_references=[],
            )

        # Normalize pii_report to dict
        data = pii_report if isinstance(pii_report, dict) else pii_report.to_cloud_metadata()

        has_critical = data.get("has_critical_pii", False)
        findings_count = data.get("findings_count", 0)
        columns = data.get("columns", [])
        evidence_hashes = []

        # Collect evidence references
        for col in columns:
            for f in col.get("findings", []):
                ev_ref = f.get("evidence_ref", {})
                if "evidence_hash" in ev_ref:
                    evidence_hashes.append(ev_ref["evidence_hash"])

        if has_critical and self.config.sensitive_info.block_on_critical_pii:
            reason = "Dataset contains CRITICAL severity sensitive identifiers (e.g. SSN, credit cards)."
            blocking_reasons.append(reason)
            return CategoryScore(
                category_name="sensitive_information",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=35.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Critical PII detected; immediate release block triggered.",
                evidence_references=evidence_hashes,
            )

        # Count findings by severity
        high_count = 0
        med_count = 0
        low_count = 0

        for col in columns:
            for f in col.get("findings", []):
                sev = f.get("severity", "").upper()
                if sev == "HIGH":
                    high_count += 1
                elif sev == "MEDIUM":
                    med_count += 1
                elif sev in ("LOW", "INFORMATIONAL"):
                    low_count += 1

        score = min(
            max_pts,
            (high_count * self.config.sensitive_info.points_per_high_finding)
            + (med_count * self.config.sensitive_info.points_per_medium_finding)
            + (low_count * self.config.sensitive_info.points_per_low_finding),
        )

        is_critical = False
        if high_count > 0 and self.config.sensitive_info.block_on_high_pii:
            blocking_reasons.append(f"Dataset contains {high_count} HIGH severity PII findings.")
            is_critical = True

        if high_count > 0:
            warnings.append(f"Dataset contains {high_count} HIGH severity sensitive findings.")

        passed = score == 0.0 and not is_critical
        return CategoryScore(
            category_name="sensitive_information",
            max_points=max_pts,
            score=round(score, 2),
            risk_weight_percentage=35.0,
            passed=passed,
            is_critical_violation=is_critical,
            findings_summary=(
                f"{findings_count} PII findings ({high_count} high, {med_count} medium, {low_count} low)."
            ),
            evidence_references=evidence_hashes,
        )

    def _eval_data_quality(
        self,
        quality_report: Optional[Union[Dict[str, Any], Any]],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> CategoryScore:
        """Category 2: Data Quality (20 points max)."""
        max_pts = self.config.data_quality.max_points

        if quality_report is None:
            blocking_reasons.append(
                "Missing data quality evidence: Dataset has not undergone deterministic quality validation."
            )
            return CategoryScore(
                category_name="data_quality",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=20.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Missing data quality validation evidence (fail-closed security).",
                evidence_references=[],
            )

        data = quality_report if isinstance(quality_report, dict) else quality_report.to_cloud_metadata()
        summary = data.get("summary", {})
        issues = data.get("issues", [])

        has_critical = summary.get("has_critical_failures", False)
        quality_score = summary.get("quality_score", 100.0)
        evidence_hashes = [
            i.get("evidence_ref", {}).get("evidence_hash")
            for i in issues
            if "evidence_ref" in i and "evidence_hash" in i["evidence_ref"]
        ]

        if has_critical and self.config.data_quality.block_on_critical_quality_issues:
            reason = "Dataset contains CRITICAL data quality violations (e.g. missing primary schema keys)."
            blocking_reasons.append(reason)
            return CategoryScore(
                category_name="data_quality",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=20.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Critical quality failures detected; immediate release block triggered.",
                evidence_references=evidence_hashes,
            )

        # Calculate score based on issues
        crit_count = sum(1 for i in issues if i.get("severity") == "CRITICAL")
        high_count = sum(1 for i in issues if i.get("severity") == "HIGH")
        med_count = sum(1 for i in issues if i.get("severity") == "MEDIUM")

        penalty = (
            (crit_count * self.config.data_quality.points_per_critical_issue)
            + (high_count * self.config.data_quality.points_per_high_issue)
            + (med_count * self.config.data_quality.points_per_medium_issue)
        )

        # Scale based on minimum acceptable score if quality score fell below threshold
        if quality_score < self.config.data_quality.min_acceptable_quality_score:
            score_deficit = (self.config.data_quality.min_acceptable_quality_score - quality_score) * 0.2
            penalty += score_deficit

        score = min(max_pts, penalty)

        if quality_score < self.config.data_quality.min_acceptable_quality_score:
            warnings.append(
                f"Dataset quality score ({quality_score}%) is below minimum threshold "
                f"({self.config.data_quality.min_acceptable_quality_score}%)."
            )

        passed = score == 0.0
        return CategoryScore(
            category_name="data_quality",
            max_points=max_pts,
            score=round(score, 2),
            risk_weight_percentage=20.0,
            passed=passed,
            is_critical_violation=False,
            findings_summary=(
                f"Quality score: {quality_score}%. {len(issues)} issues ({high_count} high, {med_count} medium)."
            ),
            evidence_references=evidence_hashes,
        )

    def _eval_licensing_provenance(
        self,
        provenance: Optional[Dict[str, Any]],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> CategoryScore:
        """Category 3: Licensing & Provenance (20 points max)."""
        max_pts = self.config.licensing_provenance.max_points

        if not provenance:
            blocking_reasons.append("Missing licensing and source provenance records.")
            return CategoryScore(
                category_name="licensing_provenance",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=20.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Missing dataset provenance and licensing metadata.",
                evidence_references=[],
            )

        license_name = str(provenance.get("license", "UNKNOWN")).strip().upper()
        normalized_allowed = [l.upper() for l in self.config.licensing_provenance.allowed_licenses]
        normalized_forbidden = [l.upper() for l in self.config.licensing_provenance.forbidden_licenses]

        score = 0.0
        is_critical = False

        if license_name in normalized_forbidden:
            reason = f"Prohibited dataset license detected: '{provenance.get('license')}'."
            blocking_reasons.append(reason)
            score = max_pts
            is_critical = True
        elif license_name not in normalized_allowed:
            warnings.append(f"Unapproved or custom dataset license: '{provenance.get('license')}'.")
            score += self.config.licensing_provenance.points_for_unapproved_license

        has_source = bool(provenance.get("source_url") or provenance.get("source_system"))
        if self.config.licensing_provenance.require_provenance_source and not has_source:
            warnings.append("Missing source URL or origin system in dataset provenance.")
            score += self.config.licensing_provenance.points_for_missing_provenance

        score = min(max_pts, score)
        passed = score == 0.0 and not is_critical

        return CategoryScore(
            category_name="licensing_provenance",
            max_points=max_pts,
            score=round(score, 2),
            risk_weight_percentage=20.0,
            passed=passed,
            is_critical_violation=is_critical,
            findings_summary=f"License: '{provenance.get('license')}'. Source verified: {has_source}.",
            evidence_references=[],
        )

    def _eval_metadata_completeness(
        self,
        metadata: Optional[Dict[str, Any]],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> CategoryScore:
        """Category 4: Metadata Completeness (10 points max)."""
        max_pts = self.config.metadata_completeness.max_points

        if not metadata:
            blocking_reasons.append("Dataset metadata dictionary is completely missing.")
            return CategoryScore(
                category_name="metadata_completeness",
                max_points=max_pts,
                score=max_pts,
                risk_weight_percentage=10.0,
                passed=False,
                is_critical_violation=True,
                findings_summary="Missing metadata envelope.",
                evidence_references=[],
            )

        missing_required = [
            f for f in self.config.metadata_completeness.required_fields
            if f not in metadata or metadata[f] is None or metadata[f] == ""
        ]
        missing_recommended = [
            f for f in self.config.metadata_completeness.recommended_fields
            if f not in metadata or metadata[f] is None or metadata[f] == ""
        ]

        score = 0.0
        is_critical = False

        if missing_required:
            score += len(missing_required) * self.config.metadata_completeness.points_per_missing_required
            if self.config.metadata_completeness.block_on_missing_required_fields:
                blocking_reasons.append(f"Missing required metadata fields: {missing_required}.")
                is_critical = True
            else:
                warnings.append(f"Missing required metadata fields: {missing_required}.")

        if missing_recommended:
            score += len(missing_recommended) * self.config.metadata_completeness.points_per_missing_recommended
            warnings.append(f"Missing recommended metadata fields: {missing_recommended}.")

        score = min(max_pts, score)
        passed = score == 0.0 and not is_critical

        return CategoryScore(
            category_name="metadata_completeness",
            max_points=max_pts,
            score=round(score, 2),
            risk_weight_percentage=10.0,
            passed=passed,
            is_critical_violation=is_critical,
            findings_summary=(
                f"Missing required: {len(missing_required)}, missing recommended: {len(missing_recommended)}."
            ),
            evidence_references=[],
        )

    def _eval_policy_violations(
        self,
        context: Optional[Dict[str, Any]],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> CategoryScore:
        """Category 5: Policy Violations & Restricted Domains (15 points max)."""
        max_pts = self.config.policy_violations.max_points

        if not context:
            context = {}

        score = 0.0
        is_critical = False

        # Domain check
        domain = str(context.get("domain", "")).lower().strip()
        prohibited = [d.lower() for d in self.config.policy_violations.prohibited_domains]

        if domain in prohibited:
            reason = f"Dataset belongs to a restricted/prohibited domain: '{domain}'."
            blocking_reasons.append(reason)
            score = max_pts
            is_critical = True

        # Retention policy check
        has_retention = bool(context.get("retention_policy") or context.get("retention_period"))
        if self.config.policy_violations.require_retention_policy and not has_retention:
            warnings.append("No explicit data retention policy is defined for this dataset.")
            score += self.config.policy_violations.points_for_missing_retention

        # Direct explicit policy violations
        explicit_violations = context.get("policy_violations", [])
        if explicit_violations:
            for v in explicit_violations:
                blocking_reasons.append(f"Explicit policy violation: {v}")
            score = max_pts
            is_critical = True

        score = min(max_pts, score)
        passed = score == 0.0 and not is_critical

        return CategoryScore(
            category_name="policy_violations",
            max_points=max_pts,
            score=round(score, 2),
            risk_weight_percentage=15.0,
            passed=passed,
            is_critical_violation=is_critical,
            findings_summary=(
                f"Domain: '{domain or 'unspecified'}'. Prohibited: {domain in prohibited}. "
                f"Retention specified: {has_retention}."
            ),
            evidence_references=[],
        )

    def evaluate(
        self,
        dataset_id: str,
        version_number: int = 1,
        pii_report: Optional[Union[Dict[str, Any], Any]] = None,
        quality_report: Optional[Union[Dict[str, Any], Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        evaluation_id: Optional[str] = None,
    ) -> PolicyEvaluationResult:
        """
        Evaluate dataset against the versioned policy and calculate the frozen weighted risk score.
        Enforces critical overrides: Any critical violation immediately blocks release regardless
        of total aggregate risk score.
        """
        eval_id = evaluation_id or str(uuid.uuid4())
        blocking_reasons: List[str] = []
        warnings: List[str] = []

        cat_sensitive = self._eval_sensitive_info(pii_report, blocking_reasons, warnings)
        cat_quality = self._eval_data_quality(quality_report, blocking_reasons, warnings)
        cat_provenance = self._eval_licensing_provenance(provenance, blocking_reasons, warnings)
        cat_metadata = self._eval_metadata_completeness(metadata, blocking_reasons, warnings)
        cat_policy = self._eval_policy_violations(context, blocking_reasons, warnings)

        total_score = round(
            cat_sensitive.score
            + cat_quality.score
            + cat_provenance.score
            + cat_metadata.score
            + cat_policy.score,
            2,
        )
        total_score = min(100.0, max(0.0, total_score))
        risk_band = compute_risk_band(total_score)

        breakdown = ScoreBreakdown(
            sensitive_information=cat_sensitive,
            data_quality=cat_quality,
            licensing_provenance=cat_provenance,
            metadata_completeness=cat_metadata,
            policy_violations=cat_policy,
            total_risk_score=total_score,
            risk_band=risk_band,
        )

        has_critical_override = any(
            c.is_critical_violation
            for c in [cat_sensitive, cat_quality, cat_provenance, cat_metadata, cat_policy]
        )

        # Decision Logic:
        # 1. Critical policy violation -> Hard BLOCKED regardless of score
        # 2. Score >= 40.0 (High or Critical risk) -> BLOCKED
        # 3. Score >= 20.0 (Moderate risk) -> WARNING (eligible with human signoff)
        # 4. Score < 20.0 (Low risk) -> PASSED (release eligible)
        if has_critical_override:
            is_eligible = False
            status = EvaluationStatus.BLOCKED
            critical_override_applied = True
        elif total_score > self.config.max_acceptable_score:
            is_eligible = False
            status = EvaluationStatus.BLOCKED
            critical_override_applied = False
            blocking_reasons.append(
                f"Aggregate risk score ({total_score:.2f}/100) exceeds maximum acceptable release "
                f"threshold ({self.config.max_acceptable_score:.2f}). Risk band: {risk_band.value}."
            )
        elif total_score >= 20.0:
            is_eligible = True
            status = EvaluationStatus.WARNING
            critical_override_applied = False
        else:
            is_eligible = True
            status = EvaluationStatus.PASSED
            critical_override_applied = False

        # Compile evidence references
        all_evidence = []
        for cat in [cat_sensitive, cat_quality]:
            for ref in cat.evidence_references:
                all_evidence.append({"category": cat.category_name, "evidence_hash": ref})

        return PolicyEvaluationResult(
            dataset_id=dataset_id,
            version_number=version_number,
            policy_name=self.config.policy_name,
            policy_version=self.config.policy_version,
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            evaluation_id=eval_id,
            is_release_eligible=is_eligible,
            status=status,
            score_breakdown=breakdown,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            evidence_references=all_evidence,
            critical_override_applied=critical_override_applied,
        )

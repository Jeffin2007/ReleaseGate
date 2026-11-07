"""
Deterministic Local Privacy and PII Detection Engine.
Integrates Microsoft Presidio Analyzer with local execution guarantees:
- Scans tabular datasets locally inside the Local Processing Plane.
- Explicitly handles missing or unavailable language models with graceful fallbacks.
- Strictly prevents raw dataset bytes and matched sensitive strings from leaking into
  findings, evidence references, or outbound cloud metadata.
- Supports configurable custom deterministic pattern recognizers.
"""

from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
import spacy

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import (
    NlpEngineProvider,
    NoOpNlpEngine,
)

from engines.dataset_profiler import DatasetProfiler, ProfilingError

from .config import CustomPatternRecognizerConfig, PIIDetectorConfig
from .exceptions import (
    InvalidDatasetError,
    LanguageModelUnavailableError,
    PIIDetectionError,
    UnsupportedLanguageError,
)
from .schemas import (
    DEFAULT_SEVERITY_MAPPING,
    ColumnPIISummary,
    EvidenceReference,
    PIIDetectionMetadata,
    PIIDetectionReport,
    PIIFinding,
    PIISeverity,
    generate_evidence_hash,
)

logger = logging.getLogger("releasegate.pii_detector")


class PIIDetector:
    """
    Local deterministic PII detection engine based on Microsoft Presidio.
    Executes strictly within the Local Processing Plane.
    """

    def __init__(self, config: Optional[PIIDetectorConfig] = None) -> None:
        self.config = config or PIIDetectorConfig()
        self.nlp_engine_status: str = "uninitialized"
        self.analyzer = self._initialize_analyzer()
        self._register_custom_recognizers()

    def _initialize_analyzer(self) -> AnalyzerEngine:
        """
        Initialize Presidio AnalyzerEngine with explicit handling for missing language models.
        """
        target_lang = self.config.language.lower()

        # Check language support
        if target_lang != "en":
            if not self.config.allow_nlp_fallback:
                raise UnsupportedLanguageError(
                    f"Unsupported language code '{target_lang}'. Default models only support 'en'."
                )

        spacy_model = self.config.spacy_model_name

        # Verify whether spaCy model is installed locally
        model_available = False
        try:
            spacy.load(spacy_model)
            model_available = True
        except Exception as exc:
            logger.warning(
                "Configured spaCy model '%s' is not installed or could not be loaded: %s",
                spacy_model,
                str(exc),
            )

        if model_available:
            try:
                nlp_configuration = {
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": target_lang, "model_name": spacy_model}],
                }
                provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
                nlp_engine = provider.create_engine()
                self.nlp_engine_status = f"spacy:{spacy_model}"
                logger.info("Initialized Presidio with spaCy model '%s'", spacy_model)
                return AnalyzerEngine(nlp_engine=nlp_engine)
            except Exception as exc:
                if not self.config.allow_nlp_fallback:
                    raise LanguageModelUnavailableError(
                        f"Failed to load spaCy model '{spacy_model}': {str(exc)}"
                    ) from exc
                logger.warning(
                    "Error loading spaCy NLP engine. Falling back to pattern-only scanning: %s",
                    str(exc),
                )

        # Fallback path: When spaCy model is unavailable or disabled
        if not self.config.allow_nlp_fallback:
            raise LanguageModelUnavailableError(
                f"NLP model '{spacy_model}' is unavailable and allow_nlp_fallback is disabled."
            )

        logger.info(
            "Using deterministic pattern-only NoOpNlpEngine fallback (no heavy NLP model required)."
        )
        noop_engine = NoOpNlpEngine(models=[{"lang_code": target_lang, "model_name": ""}])
        self.nlp_engine_status = "pattern_fallback:noop"
        return AnalyzerEngine(nlp_engine=noop_engine)

    def _register_custom_recognizers(self) -> None:
        """
        Register custom pattern recognizers into Presidio's recognizer registry.
        """
        for item in self.config.custom_recognizers:
            patterns = [
                Pattern(
                    name=p.get("name", f"{item.name}_pattern"),
                    regex=p["regex"],
                    score=float(p.get("score", 0.8)),
                )
                for p in item.patterns
            ]
            recognizer = PatternRecognizer(
                supported_entity=item.supported_entity,
                name=item.name,
                patterns=patterns,
                context=item.context,
                supported_language=item.supported_language,
            )
            self.analyzer.registry.add_recognizer(recognizer)
            logger.info(
                "Registered custom PII pattern recognizer: entity='%s', name='%s'",
                item.supported_entity,
                item.name,
            )

    def _get_severity(self, entity_type: str) -> PIISeverity:
        """
        Resolve severity level for an entity type considering configured overrides
        and custom recognizers.
        """
        if entity_type in self.config.severity_overrides:
            return self.config.severity_overrides[entity_type]

        # Check custom recognizers for configured severity
        for custom_rec in self.config.custom_recognizers:
            if custom_rec.supported_entity == entity_type:
                return custom_rec.severity

        return DEFAULT_SEVERITY_MAPPING.get(entity_type, PIISeverity.MEDIUM)

    @staticmethod
    def _categorize_length(length: int) -> str:
        """Buckets token lengths into coarse ranges to prevent raw value leakage."""
        if length < 5:
            return "<5"
        elif length <= 10:
            return "5-10"
        elif length <= 20:
            return "11-20"
        elif length <= 50:
            return "21-50"
        return ">50"

    def scan_dataframe(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        version_number: int = 1,
    ) -> PIIDetectionReport:
        """
        Deterministically scan a Pandas DataFrame column-by-column for sensitive PII entities.
        Ensures raw text is never retained in the output report.
        """
        if df.empty or len(df.columns) == 0:
            raise InvalidDatasetError("Dataset contains no rows or columns to scan.")

        total_rows = len(df)
        total_columns = len(df.columns)
        all_findings: List[PIIFinding] = []
        column_summaries: List[ColumnPIISummary] = []

        for col in df.columns:
            col_name = str(col)
            series = df[col].dropna()

            if len(series) == 0:
                # Column contains only nulls
                column_summaries.append(
                    ColumnPIISummary(
                        column_name=col_name,
                        total_scanned_rows=0,
                        pii_detected=False,
                        findings=[],
                        highest_severity=None,
                    )
                )
                continue

            if self.config.max_rows_to_sample is not None and self.config.max_rows_to_sample > 0:
                series = series.iloc[: self.config.max_rows_to_sample]

            scanned_count = len(series)

            # Detection tracking per entity type:
            # entity_type -> { "scores": [...], "rows": [...], "lengths": defaultdict(int) }
            entity_detections: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"scores": [], "rows": [], "lengths": defaultdict(int)}
            )

            for row_idx, val in series.items():
                val_str = str(val).strip()
                if not val_str:
                    continue

                # Run local deterministic Presidio analysis
                results = self.analyzer.analyze(
                    text=val_str,
                    language=self.config.language,
                    entities=self.config.supported_entities,
                    score_threshold=self.config.confidence_threshold,
                )

                for res in results:
                    entity_type = res.entity_type
                    token_len = res.end - res.start
                    bucket = self._categorize_length(token_len)

                    entity_detections[entity_type]["scores"].append(float(res.score))
                    # Record up to 10 sample row indices for local audit
                    if len(entity_detections[entity_type]["rows"]) < 10:
                        entity_detections[entity_type]["rows"].append(int(row_idx))
                    entity_detections[entity_type]["lengths"][bucket] += 1

            col_findings: List[PIIFinding] = []
            highest_col_severity: Optional[PIISeverity] = None

            for entity_type, data in entity_detections.items():
                scores = data["scores"]
                count = len(scores)
                if count == 0:
                    continue

                min_s = round(min(scores), 4)
                max_s = round(max(scores), 4)
                avg_s = round(sum(scores) / count, 4)
                severity = self._get_severity(entity_type)

                evidence_hash = generate_evidence_hash(
                    dataset_id=dataset_id,
                    version_number=version_number,
                    column_name=col_name,
                    entity_type=entity_type,
                    occurrence_count=count,
                    min_score=min_s,
                    max_score=max_s,
                )

                evidence_ref = EvidenceReference(
                    column_name=col_name,
                    entity_type=entity_type,
                    matched_count=count,
                    min_score=min_s,
                    max_score=max_s,
                    avg_score=avg_s,
                    sample_row_indices=data["rows"],
                    length_distribution=dict(data["lengths"]),
                    evidence_hash=evidence_hash,
                )

                finding = PIIFinding(
                    column_name=col_name,
                    entity_type=entity_type,
                    occurrence_count=count,
                    severity=severity,
                    confidence=max_s,
                    evidence_ref=evidence_ref,
                )
                col_findings.append(finding)
                all_findings.append(finding)

                # Determine highest severity
                if highest_col_severity is None:
                    highest_col_severity = severity
                else:
                    severity_rank = {
                        PIISeverity.CRITICAL: 5,
                        PIISeverity.HIGH: 4,
                        PIISeverity.MEDIUM: 3,
                        PIISeverity.LOW: 2,
                        PIISeverity.INFORMATIONAL: 1,
                    }
                    if severity_rank[severity] > severity_rank[highest_col_severity]:
                        highest_col_severity = severity

            column_summaries.append(
                ColumnPIISummary(
                    column_name=col_name,
                    total_scanned_rows=scanned_count,
                    pii_detected=len(col_findings) > 0,
                    findings=col_findings,
                    highest_severity=highest_col_severity,
                )
            )

        has_critical = any(f.severity == PIISeverity.CRITICAL for f in all_findings)
        has_high = any(f.severity == PIISeverity.HIGH for f in all_findings)

        metadata = PIIDetectionMetadata(
            dataset_id=dataset_id,
            version_number=version_number,
            total_rows_scanned=total_rows,
            total_columns_scanned=total_columns,
            total_findings_count=len(all_findings),
            scanned_at_utc=datetime.now(timezone.utc).isoformat(),
            nlp_engine=self.nlp_engine_status,
            language=self.config.language,
        )

        return PIIDetectionReport(
            dataset_id=dataset_id,
            version_number=version_number,
            summary=metadata,
            columns=column_summaries,
            findings=all_findings,
            has_critical_pii=has_critical,
            has_high_pii=has_high,
        )

    def scan_dataset_bytes(
        self,
        content: bytes,
        file_format: str,
        dataset_id: str,
        version_number: int = 1,
    ) -> PIIDetectionReport:
        """
        Safely profile and scan dataset raw bytes in memory inside the Local Processing Plane.
        """
        try:
            df = DatasetProfiler.load_dataframe(content, file_format)
        except ProfilingError as exc:
            raise InvalidDatasetError(f"Failed to parse dataset bytes for scanning: {str(exc)}") from exc

        return self.scan_dataframe(
            df=df,
            dataset_id=dataset_id,
            version_number=version_number,
        )

    def scan_text(
        self,
        text: str,
        column_name: str = "text_sample",
        dataset_id: str = "ad_hoc_scan",
        version_number: int = 1,
    ) -> List[PIIFinding]:
        """
        Deterministic scan of single text string (e.g. for unit testing or verification).
        Returns structured PIIFindings with zero raw text exposure.
        """
        df = pd.DataFrame({column_name: [text]})
        report = self.scan_dataframe(df=df, dataset_id=dataset_id, version_number=version_number)
        return report.findings

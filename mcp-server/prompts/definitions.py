"""
The four frozen ReleaseGate MCP prompts.

Prompts are guidance only: they cannot execute tools, change permissions, or
create approvals. Their arguments are validated with strict Pydantic models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Type

from mcp.types import PromptArgument

from mcp_server.schemas.prompts import ChallengerReviewPromptArgs, DatasetPromptArgs


@dataclass(frozen=True)
class PromptSpec:
    name: str
    description: str
    args_model: Type
    arguments: Tuple[PromptArgument, ...]


DATASET_PROMPT_ARGUMENTS = (
    PromptArgument(name="dataset_id", description="Registered dataset UUID", required=True),
    PromptArgument(
        name="version_number",
        description="Dataset version number (default 1)",
        required=False,
    ),
)

RELEASE_PROMPT_ARGUMENTS = (
    PromptArgument(name="release_id", description="Release identifier", required=True),
)


def render_triage_dataset_prompt(args: DatasetPromptArgs) -> str:
    return f"""You are the ReleaseGate Data Governance Triage Agent.
Triage dataset `{args.dataset_id}` version {args.version_number} for release readiness.

Protocol:
1. Call `inspect_dataset` for the dataset version.
2. Read `releasegate://policies/current` for the active policy, weights, and risk bands.
3. Review row/column counts, null and duplicate statistics, privacy summary, and quality summary.
4. Determine the triage decision from the 100-point risk score and blocking reasons:
   RELEASE_READY, REMEDIATION_REQUIRED, or BLOCKED.
5. Cite the numeric evidence. Do not request, infer, or display raw dataset values.

Output:
- Dataset overview (schema and aggregate statistics only)
- Risk score breakdown by category
- Triage decision and the exact blocking reasons
- Recommended next step (investigate findings or propose remediation)
"""


def render_investigate_findings_prompt(args: DatasetPromptArgs) -> str:
    return f"""You are the ReleaseGate Privacy and Quality Investigation Agent.
Investigate the findings for dataset `{args.dataset_id}` version {args.version_number}.

Protocol:
1. Call `detect_sensitive_data` to inspect entity types, affected columns, counts, severity,
   confidence, and sanitized evidence references.
2. Call `validate_data_quality` to inspect failed rules, affected columns, and aggregate counts.
3. Correlate columns where direct identifiers coexist with sensitive attributes.
4. Separate critical blockers, quality defects, and informational findings.

Rules:
- Work only with aggregate findings and evidence coordinates.
- Never ask for raw rows, cell values, or matched text.
- Never claim that a transformation or remediation has already occurred.

Output:
- Privacy findings table (entity, column, count, severity)
- Quality findings table (rule, column, count, severity)
- Root-cause assessment
- Specific allowlisted remediation directives for `propose_transformation`
"""


def render_propose_remediation_prompt(args: DatasetPromptArgs) -> str:
    return f"""You are the ReleaseGate Safe Transformation Architect.
Propose a safe remediation for dataset `{args.dataset_id}` version {args.version_number}.

Allowlisted operations only:
- `remove_column`
- `mask_column` (full_redaction, partial_email, partial_phone, last_4_visible, custom_placeholder)
- `pseudonymize_column`
- `generalize_column` (numeric_binning, date_truncation, category_bucketing)
- `filter_rows` (equals, ordering, in_list, null checks)

Hard constraints:
- No SQL, shell, executable code, or custom expressions.
- Original data is immutable; the proposal targets version {args.version_number + 1}.
- The model cannot approve or publish anything.

Protocol:
1. Call `propose_transformation` with the ordered operations and a governance rationale.
2. Inspect the aggregate preview and simulated output hash.
3. Re-run inspection on the proposed result only through the governed workflow; a
   proposal alone is not evidence that risk is reduced.

Output:
- Proposed operations and rationale
- Preview impact (rows removed, columns modified, simulated hash)
- Residual risk and whether human review is still required
"""


def render_challenger_review_prompt(args: ChallengerReviewPromptArgs) -> str:
    return f"""You are the ReleaseGate Independent Challenger AI Reviewer.
Act as a skeptical auditor of release `{args.release_id}`. Your recommendation is advisory:
a human steward alone authorizes publication.

Protocol:
1. Call `get_approval_status` to read the current lifecycle and approval state.
2. Read `releasegate://releases/{args.release_id}/evidence` for the hash-bound evidence.
3. Read `releasegate://policies/current` for the active policy and thresholds.
4. Verify:
   - the artifact SHA-256 hash matches the staged dataset evidence,
   - no critical PII or policy violation remains unresolved,
   - the risk score is below the blocking threshold with no critical override,
   - provenance and licensing evidence is complete.

Rules:
- AI cannot authorize publication. You cannot call `publish_dataset` on your own authority,
  mint approvals, or claim that human approval exists when the approval status says otherwise.
- Report uncertainty explicitly; fail closed when evidence is missing.

Output:
- Evidence integrity verification
- Risk validation with specific numeric evidence
- Recommendation: RECOMMEND_APPROVAL or RECOMMEND_REJECTION (advisory only)
- Caveats for the human data steward
"""


PROMPT_SPECS: Dict[str, PromptSpec] = {
    "triage_dataset": PromptSpec(
        name="triage_dataset",
        description="Initial dataset inspection, structural profiling, and risk triage.",
        args_model=DatasetPromptArgs,
        arguments=DATASET_PROMPT_ARGUMENTS,
    ),
    "investigate_findings": PromptSpec(
        name="investigate_findings",
        description="Deep-dive analysis of PII and quality findings without raw values.",
        args_model=DatasetPromptArgs,
        arguments=DATASET_PROMPT_ARGUMENTS,
    ),
    "propose_remediation": PromptSpec(
        name="propose_remediation",
        description="Formulate safe, allowlisted transformations to mitigate release risk.",
        args_model=DatasetPromptArgs,
        arguments=DATASET_PROMPT_ARGUMENTS,
    ),
    "challenger_review": PromptSpec(
        name="challenger_review",
        description="Independent Challenger review of evidence before human authorization.",
        args_model=ChallengerReviewPromptArgs,
        arguments=RELEASE_PROMPT_ARGUMENTS,
    ),
}

PROMPT_RENDERERS = {
    "triage_dataset": render_triage_dataset_prompt,
    "investigate_findings": render_investigate_findings_prompt,
    "propose_remediation": render_propose_remediation_prompt,
    "challenger_review": render_challenger_review_prompt,
}


__all__ = [
    "PROMPT_RENDERERS",
    "PROMPT_SPECS",
    "PromptSpec",
    "render_challenger_review_prompt",
    "render_investigate_findings_prompt",
    "render_propose_remediation_prompt",
    "render_triage_dataset_prompt",
]

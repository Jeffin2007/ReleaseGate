"""
Human approval authority for hash-bound dataset publication.

Approval records are created ONLY by the human approval channel (the control
plane after a steward signs off, forwarded to the local worker through the
authenticated job channel). They are never created by an MCP tool, and the
approval identifier is never derivable from the release metadata.

A publication therefore requires:
  * a release that was submitted for review and is policy-eligible,
  * a human approval record bound to the exact release, artifact hash, and
    organization,
  * a record that has not expired and has not been revoked.

The ledger is intentionally behind an injectable object so a production
deployment can replace it with a persistent, signed control-plane record store
without changing the MCP layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Callable, Dict, List, Optional

from mcp_server.security.permissions import HumanApprovalRequiredError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HumanApprovalRecord:
    """Immutable human authorization bound to one artifact hash."""

    approval_id: str
    release_id: str
    artifact_hash: str
    organization_id: str
    approver_id: str
    approver_type: str
    approved_at: datetime
    expires_at: datetime
    status: str = "ACTIVE"
    verification_digest: str = ""

    def is_active(self, now: Optional[datetime] = None) -> bool:
        moment = now or _utcnow()
        return self.status == "ACTIVE" and moment < self.expires_at

    def to_safe_dict(self) -> Dict[str, object]:
        """Approval metadata safe to expose to a cloud-facing client (no token/id)."""
        return {
            "status": self.status if self.is_active() else "EXPIRED_OR_REVOKED",
            "approver_id": self.approver_id,
            "approver_type": self.approver_type,
            "approved_at": self.approved_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


class HumanApprovalAuthority:
    """Issues and verifies human approval records."""

    def __init__(
        self,
        ttl_seconds: int = 900,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._secret = secrets.token_bytes(32)
        self._records: Dict[str, HumanApprovalRecord] = {}

    def _digest(self, approval_id: str, release_id: str, artifact_hash: str, organization_id: str) -> str:
        return hmac.new(
            self._secret,
            f"{approval_id}:{release_id}:{artifact_hash}:{organization_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def describe(self, record: HumanApprovalRecord) -> Dict[str, object]:
        """Describe an approval using the authority clock (no identifier or token)."""
        active = record.is_active(self._clock())
        if active:
            status = "ACTIVE"
        elif record.status == "REVOKED":
            status = "REVOKED"
        else:
            status = "EXPIRED"
        return {
            "status": status,
            "approver_id": record.approver_id,
            "approver_type": record.approver_type,
            "approved_at": record.approved_at.isoformat(),
            "expires_at": record.expires_at.isoformat(),
        }

    def record_human_approval(
        self,
        *,
        release_id: str,
        artifact_hash: str,
        organization_id: str,
        approver_id: str,
        approver_type: str = "HUMAN",
        ttl_seconds: Optional[int] = None,
    ) -> HumanApprovalRecord:
        """
        Record a human approval. Not exposed through MCP.

        ``approver_type`` must be HUMAN; this method exists for the trusted
        human/control-plane channel and refuses to represent an AI approver.
        """
        if approver_type != "HUMAN":
            raise HumanApprovalRequiredError(
                "Publication approval must come from a human approver; AI approval is prohibited."
            )
        if not approver_id or not approver_id.strip():
            raise HumanApprovalRequiredError("A human approver identity is required.")
        if not organization_id:
            raise HumanApprovalRequiredError("An organization scope is required for approval.")
        normalized_hash = artifact_hash.strip().lower()
        if len(normalized_hash) != 64 or any(c not in "0123456789abcdef" for c in normalized_hash):
            raise HumanApprovalRequiredError("Approval must bind to a valid SHA-256 artifact hash.")
        if not release_id.startswith("rel_"):
            raise HumanApprovalRequiredError("Approval must bind to a valid release identifier.")

        now = self._clock()
        expires_at = now + (timedelta(seconds=ttl_seconds) if ttl_seconds else self._ttl)
        approval_id = f"apr_{secrets.token_hex(16)}"
        digest = self._digest(approval_id, release_id, normalized_hash, organization_id)

        record = HumanApprovalRecord(
            approval_id=approval_id,
            release_id=release_id,
            artifact_hash=normalized_hash,
            organization_id=organization_id,
            approver_id=approver_id.strip(),
            approver_type=approver_type,
            approved_at=now,
            expires_at=expires_at,
            verification_digest=digest,
        )
        self._records[approval_id] = record
        return record

    def verify(
        self,
        *,
        approval_id: str,
        release_id: str,
        artifact_hash: str,
        organization_id: str,
    ) -> HumanApprovalRecord:
        """
        Verify an approval binding, failing closed with the same generic error
        for missing, cross-tenant, mismatched, expired, or revoked records.
        """
        record = self._records.get(approval_id)
        normalized_hash = artifact_hash.strip().lower()
        if record is None:
            raise HumanApprovalRequiredError(
                "Human authorization required: no valid approval record exists for this release."
            )
        if (
            record.release_id != release_id
            or record.organization_id != organization_id
            or record.artifact_hash != normalized_hash
        ):
            raise HumanApprovalRequiredError(
                "Human authorization required: the approval does not match this release and artifact."
            )
        expected_digest = self._digest(
            record.approval_id, record.release_id, record.artifact_hash, record.organization_id
        )
        if not hmac.compare_digest(record.verification_digest, expected_digest):
            raise HumanApprovalRequiredError(
                "Human authorization required: the approval record failed its integrity check."
            )
        if not record.is_active(self._clock()):
            raise HumanApprovalRequiredError(
                "Human authorization required: the approval has expired or was revoked."
            )
        return record

    def find_active_for_release(
        self,
        *,
        release_id: str,
        artifact_hash: str,
        organization_id: str,
    ) -> Optional[HumanApprovalRecord]:
        """Return the active approval matching a release, if any."""
        normalized_hash = artifact_hash.strip().lower()
        now = self._clock()
        for record in self._records.values():
            if (
                record.release_id == release_id
                and record.organization_id == organization_id
                and record.artifact_hash == normalized_hash
                and record.is_active(now)
            ):
                return record
        return None

    def revoke_for_release(self, *, release_id: str, organization_id: str) -> int:
        """Revoke all approvals for a release within one organization."""
        revoked = 0
        for approval_id, record in list(self._records.items()):
            if (
                record.release_id == release_id
                and record.organization_id == organization_id
                and record.status == "ACTIVE"
            ):
                self._records[approval_id] = HumanApprovalRecord(
                    approval_id=record.approval_id,
                    release_id=record.release_id,
                    artifact_hash=record.artifact_hash,
                    organization_id=record.organization_id,
                    approver_id=record.approver_id,
                    approver_type=record.approver_type,
                    approved_at=record.approved_at,
                    expires_at=record.expires_at,
                    status="REVOKED",
                    verification_digest=record.verification_digest,
                )
                revoked += 1
        return revoked

    def list_for_release(
        self, *, release_id: str, organization_id: str
    ) -> List[HumanApprovalRecord]:
        """Return approvals for a release within one organization."""
        return [
            record
            for record in self._records.values()
            if record.release_id == release_id and record.organization_id == organization_id
        ]


__all__ = ["HumanApprovalAuthority", "HumanApprovalRecord"]

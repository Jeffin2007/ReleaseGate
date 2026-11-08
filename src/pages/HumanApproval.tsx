import { useState, useMemo } from "react";
import {
  Clock,
  CheckCircle,
  XCircle,
  ChevronRight,
  Loader2,
  Hash,
  Shield,
  AlertTriangle,
  Eye,
  FileText,
  Confirm,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getRiskColor, getStatusColor, getSeverityColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_INSPECTIONS, DEMO_DATASETS, DEMO_FINDINGS, DEMO_APPROVAL_STATUS } from "@/lib/api/mockData";

interface ApprovalRequest {
  id: string;
  release_id: string;
  dataset_id: string;
  version_number: number;
  content_hash: string;
  risk_score: number;
  risk_band: string;
  status: string;
  is_release_eligible: boolean;
  approver_id: string;
  approver_name: string;
  approver_type: "HUMAN" | "AI";
  created_at: string;
  expires_at: string;
  decision: "PENDING" | "APPROVED" | "REJECTED" | null;
}

const DEMO_APPROVALS: ApprovalRequest[] = [
  {
    id: "apr_abc123def4567890abcdef1234567890",
    release_id: "rel_0123456789ab",
    dataset_id: "ds-pii-002",
    version_number: 1,
    content_hash: "d2a8f5c3b91e7d4f2a6c8e3b5d9f1a4c7e2b8d3f6a0c5e9b2d8f4a1c7e3b5d9f",
    risk_score: 58.0,
    risk_band: "HIGH",
    status: "PENDING_REVIEW",
    is_release_eligible: false,
    approver_id: "user-stewart",
    approver_name: "Dr. Marcus Webb",
    approver_type: "HUMAN",
    created_at: "2026-10-20T16:00:00Z",
    expires_at: "2026-10-20T16:15:00Z",
    decision: "PENDING",
  },
  {
    id: "apr_def456abc78901234567890abcdef12",
    release_id: "rel_023456789abc",
    dataset_id: "ds-clean-001",
    version_number: 1,
    content_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    risk_score: 12.5,
    risk_band: "LOW",
    status: "PUBLISHED",
    is_release_eligible: true,
    approver_id: "user-admin",
    approver_name: "Sarah Chen",
    approver_type: "HUMAN",
    created_at: "2026-10-15T10:00:00Z",
    expires_at: "2026-10-15T10:15:00Z",
    decision: "APPROVED",
  },
  {
    id: "apr_ghi789jkl01234567890abcdef1234",
    release_id: "rel_03456789abcd",
    dataset_id: "ds-ehr-003",
    version_number: 1,
    content_hash: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
    risk_score: 22.0,
    risk_band: "MODERATE",
    status: "PENDING_REVIEW",
    is_release_eligible: true,
    approver_id: "pending",
    approver_name: "Pending reviewer",
    approver_type: "HUMAN",
    created_at: "2026-10-25T12:00:00Z",
    expires_at: "2026-10-25T12:15:00Z",
    decision: "PENDING",
  },
];

export function HumanApproval({ approvalId }: { approvalId?: string }) {
  const { isAuthenticated, user } = useAuth();
  const [approvals, setApprovals] = useState<ApprovalRequest[]>(DEMO_APPROVALS);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(
    approvalId ? DEMO_APPROVALS.find((a) => a.id === approvalId) || null : null
  );
  const [isActing, setIsActing] = useState(false);
  const [actionResult, setActionResult] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingAction, setPendingAction] = useState<"approve" | "reject" | null>(null);
  const [useDemoData, setUseDemoData] = useState(true);

  const pendingApprovals = useMemo(() => approvals.filter((a) => a.decision === "PENDING"), [approvals]);
  const approvedApprovals = useMemo(() => approvals.filter((a) => a.decision === "APPROVED"), [approvals]);

  const handleSelectApproval = (approval: ApprovalRequest) => {
    setSelectedApproval(approval);
    setShowConfirmDialog(false);
    setPendingAction(null);
    setActionResult(null);
  };

  const handleApprove = () => {
    if (!selectedApproval) return;
    setPendingAction("approve");
    setShowConfirmDialog(true);
  };

  const handleReject = () => {
    if (!selectedApproval) return;
    setPendingAction("reject");
    setShowConfirmDialog(true);
  };

  const confirmAction = async () => {
    if (!selectedApproval || !pendingAction) return;
    setIsActing(true);
    await new Promise((r) => setTimeout(r, 1500));
    setIsActing(false);
    setShowConfirmDialog(false);

    const updated = { ...selectedApproval, decision: pendingAction === "approve" ? "APPROVED" : "REJECTED" };
    setApprovals((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    setSelectedApproval(updated);
    setPendingAction(null);
    setActionResult({
      type: "success",
      message: pendingAction === "approve"
        ? "Release approved. The artifact hash has been signed and the release is ready for publication."
        : "Release rejected. The approval record has been voided and the release is returned to the pending queue.",
    });
    setUseDemoData(true);
  };

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <Clock className="h-5 w-5 text-rg-primary" />
            Human Approval Queue
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            {isAuthenticated && user?.role === "ADMIN" ? "Admin-level approval queue — you can approve and reject releases." : "Human steward approval queue — authorize or reject release requests."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge className={cn(
            pendingApprovals.length > 0 ? "bg-amber-100 text-amber-700 border-amber-200" : "bg-green-100 text-green-700 border-green-200"
          )}>
            {pendingApprovals.length} pending
          </Badge>
          <Badge className="bg-green-100 text-green-700 border-green-200">
            {approvedApprovals.length} approved
          </Badge>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Approval list */}
        <div className="lg:col-span-2 space-y-4">
          {approvals.map((approval, idx) => (
            <Card
              key={approval.id}
              className={cn(
                "transition-all duration-200 animate-fade-in cursor-pointer hover:shadow-md hover:border-rg-primary-light/50",
                selectedApproval?.id === approval.id && "border-rg-primary ring-2 ring-rg-primary/20"
              )}
              style={{ animationDelay: `${idx * 50}ms` }}
              onClick={() => handleSelectApproval(approval)}
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                    approval.decision === "APPROVED" ? "bg-green-100 text-green-600" :
                    approval.decision === "REJECTED" ? "bg-red-100 text-red-600" :
                    "bg-amber-100 text-amber-600"
                  )}>
                    {approval.decision === "APPROVED" ? (
                      <CheckCircle className="h-5 w-5" />
                    ) : approval.decision === "REJECTED" ? (
                      <XCircle className="h-5 w-5" />
                    ) : (
                      <Clock className="h-5 w-5" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-rg-text truncate">
                        {DEMO_DATASETS.find((d) => d.id === approval.dataset_id)?.name || "Unknown dataset"}
                      </h3>
                      <Badge variant="outline" className={cn(getStatusColor(approval.status))} className="text-[10px]">
                        {approval.status}
                      </Badge>
                      <Badge className={cn(getRiskBadgeClass(approval.risk_band))}>
                        {approval.risk_band}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-rg-text-muted mb-2">
                      <span>v{approval.version_number}</span>
                      <span className="font-mono">{truncateHash(approval.content_hash, 8, 8)}</span>
                      <span>{formatDate(approval.created_at)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-rg-text-muted">
                        Requested by: <span className="text-rg-text font-medium">{approval.approver_name}</span>
                      </span>
                      {approval.decision === "PENDING" && (
                        <Badge variant="warning" className="text-[10px]">
                          Awaiting decision
                        </Badge>
                      )}
                      {approval.decision === "APPROVED" && (
                        <Badge variant="success" className="text-[10px]">
                          Approved
                        </Badge>
                      )}
                      {approval.decision === "REJECTED" && (
                        <Badge variant="error" className="text-[10px]">
                          Rejected
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {approvals.length === 0 && (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">All caught up</h3>
                <p className="text-sm text-rg-text-muted">No approval requests waiting for your review.</p>
              </div>
            </Card>
          )}
        </div>

        {/* Detail panel */}
        <div className="space-y-4">
          {selectedApproval ? (
            <>
              {/* Approval detail */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Hash className="h-4 w-4 text-rg-text-muted" />
                    Approval Details
                  </CardTitle>
                  <CardDescription>
                    {selectedApproval.decision === "PENDING" ? "Awaiting your decision" :
                     selectedApproval.decision === "APPROVED" ? "Approved" :
                     "Rejected"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Release ID</p>
                      <p className="font-mono text-rg-text">{selectedApproval.release_id}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Dataset</p>
                      <p className="text-rg-text truncate ml-2 max-w-[120px]">
                        {DEMO_DATASETS.find((d) => d.id === selectedApproval.dataset_id)?.name}
                      </p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Version</p>
                      <p className="text-rg-text">v{selectedApproval.version_number}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Risk Score</p>
                      <p className="text-rg-text font-medium">{selectedApproval.risk_score.toFixed(1)}</p>
                    </div>
                  </div>

                  {/* Artifact hash (prominent) */}
                  <div className="p-3 bg-rg-primary/5 border border-rg-primary/20 rounded-lg">
                    <p className="text-xs text-rg-text-muted mb-1">Artifact Hash (SHA-256)</p>
                    <div className="flex items-center gap-1">
                      <code className="flex-1 font-mono text-sm bg-rg-surface rounded px-2 py-1.5 border border-rg-border text-rg-text break-all">
                        {selectedApproval.content_hash}
                      </code>
                      <button
                        onClick={() => navigator.clipboard.writeText(selectedApproval.content_hash)}
                        className="p-1.5 text-rg-text-muted hover:text-rg-primary hover:bg-rg-surface-alt rounded transition-colors shrink-0"
                        title="Copy hash"
                      >
                        <Hash className="h-4 w-4" />
                      </button>
                    </div>
                    <p className="text-[10px] text-rg-text-muted mt-1.5">
                      Approval is bound to this exact hash. Any modification invalidates the approval.
                    </p>
                  </div>

                  {/* Approver info */}
                  <div className="flex items-center gap-3 p-3 bg-rg-surface-alt rounded-lg">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-rg-primary/10 text-rg-primary text-xs font-semibold">
                      {selectedApproval.approver_name.split(" ").map(n => n[0]).join("")}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-rg-text">{selectedApproval.approver_name}</p>
                      <p className="text-xs text-rg-text-muted">Human approver • {selectedApproval.approver_type}</p>
                    </div>
                  </div>

                  {/* Timing */}
                  <div className="pt-3 border-t border-rg-border/50 space-y-1 text-xs text-rg-text-muted">
                    <div className="flex justify-between">
                      <span>Created</span>
                      <span>{formatDate(selectedApproval.created_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Expires</span>
                      <span>{formatDate(selectedApproval.expires_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Decision</span>
                      <span className={cn(
                        selectedApproval.decision === "APPROVED" ? "text-green-600 font-medium" :
                        selectedApproval.decision === "REJECTED" ? "text-red-600 font-medium" :
                        "text-amber-600 font-medium"
                      )}>
                        {selectedApproval.decision === "PENDING" ? "Pending" :
                         selectedApproval.decision === "APPROVED" ? "Approved" : "Rejected"}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Action buttons */}
              <Card className={cn(
                selectedApproval.decision === "APPROVED" ? "border-green-200 bg-green-50/50" :
                selectedApproval.decision === "REJECTED" ? "border-red-200 bg-red-50/50" :
                "border-rg-border"
              )}>
                <CardContent className="p-4">
                  {selectedApproval.decision === "PENDING" ? (
                    <>
                      <div className="flex items-center gap-2 mb-4 text-xs text-rg-text-muted">
                        <AlertTriangle className="h-4 w-4" />
                        <span>Review the exact artifact hash before approving. This action binds your authorization to this specific version.</span>
                      </div>
                      <div className="flex gap-3">
                        <Button
                          variant="danger"
                          className="flex-1"
                          disabled={isActing}
                          onClick={handleReject}
                        >
                          <XCircle className="h-4 w-4" />
                          Reject
                        </Button>
                        <Button
                          className="flex-1"
                          disabled={isActing}
                          onClick={handleApprove}
                        >
                          <CheckCircle className="h-4 w-4" />
                          Approve Release
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className={cn(
                      selectedApproval.decision === "APPROVED" ?
                        "flex items-center gap-3 p-4 bg-green-50 rounded-lg border border-green-200" :
                        "flex items-center gap-3 p-4 bg-red-50 rounded-lg border border-red-200"
                    )}>
                      {selectedApproval.decision === "APPROVED" ? (
                        <>
                          <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-green-800">Approved</p>
                            <p className="text-xs text-green-600">This release has been authorized for publication.</p>
                          </div>
                        </>
                      ) : (
                        <>
                          <XCircle className="h-5 w-5 text-red-600 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-red-800">Rejected</p>
                            <p className="text-xs text-red-600">This release has been rejected and cannot be published.</p>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Confirmation dialog */}
              {showConfirmDialog && pendingAction && (
                <Card className="border-rg-primary/50 bg-rg-primary/5 p-4">
                  <CardContent className="p-4">
                    <div className="flex items-start gap-3">
                      <Confirm className="h-5 w-5 text-rg-primary shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-rg-text mb-1">
                          {pendingAction === "approve" ? "Approve this release?" : "Reject this release?"}
                        </p>
                        <p className="text-xs text-rg-text-muted">
                          {pendingAction === "approve"
                            ? "You are authorizing publication of the exact dataset version with SHA-256 hash shown above. This action is irreversible and auditable."
                            : "Rejecting this release will void the approval record and return the release to the pending queue for further review."}
                        </p>
                        <div className="flex items-center gap-2 mt-3">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => { setShowConfirmDialog(false); setPendingAction(null); }}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            onClick={confirmAction}
                            disabled={isActing}
                            loading={isActing}
                            className={pendingAction === "approve" ? "" : "bg-red-600 hover:bg-red-700"}
                          >
                            {isActing ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : pendingAction === "approve" ? (
                              <>
                                <CheckCircle className="h-4 w-4" />
                                Confirm Approval
                              </>
                            ) : (
                              <>
                                <XCircle className="h-4 w-4" />
                                Confirm Rejection
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Action result */}
              {actionResult && (
                <Card className={cn(
                  actionResult.type === "success" ? "border-green-200 bg-green-50/50" : "border-red-200 bg-red-50/50"
                )}>
                  <CardContent className="p-4 flex items-center gap-3">
                    {actionResult.type === "success" ? (
                      <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-600 shrink-0" />
                    )}
                    <div>
                      <p className={cn(
                        "text-sm font-medium",
                        actionResult.type === "success" ? "text-green-800" : "text-red-800"
                      )}>
                        {actionResult.message}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Clock className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">Select an approval request</h3>
                <p className="text-sm text-rg-text-muted">Choose an approval from the queue to review details and act.</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

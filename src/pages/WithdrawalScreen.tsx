import { useState, useMemo } from "react";
import {
  AlertTriangle,
  XCircle,
  CheckCircle,
  Loader2,
  Hash,
  Shield,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TextareaInput } from "@/components/ui/Textarea";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getStatusColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_DATASETS } from "@/lib/api/mockData";

interface WithdrawalRequest {
  id: string;
  release_id: string;
  dataset_id: string;
  version_number: number;
  content_hash: string;
  status: "PENDING_REVIEW" | "PUBLISHED" | "WITHDRAWN";
  risk_score: number;
  risk_band: string;
  withdrawal_reason: string | null;
  withdrawn_by: string | null;
  withdrawn_at: string | null;
  prior_status: string;
}

const DEMO_WITHDRAWALS: WithdrawalRequest[] = [
  {
    id: "wd-001",
    release_id: "rel_0123456789ab",
    dataset_id: "ds-pii-002",
    version_number: 1,
    content_hash: "d2a8f5c3b91e7d4f2a6c8e3b5d9f1a4c7e2b8d3f6a0c5e9b2d8f4a1c7e3b5d9f",
    status: "PENDING_REVIEW",
    risk_score: 58.0,
    risk_band: "HIGH",
    withdrawal_reason: null,
    withdrawn_by: null,
    withdrawn_at: null,
    prior_status: "STAGED",
  },
  {
    id: "wd-002",
    release_id: "rel_023456789abc",
    dataset_id: "ds-ehr-003",
    version_number: 1,
    content_hash: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
    status: "WITHDRAWN",
    risk_score: 22.0,
    risk_band: "MODERATE",
    withdrawal_reason: "Steward identified unresolved quality issues.",
    withdrawn_by: "Dr. Marcus Webb",
    withdrawn_at: "2026-10-25T14:00:00Z",
    prior_status: "PENDING_REVIEW",
  },
];

export function WithdrawalScreen({ releaseId }: { releaseId?: string }) {
  const { isAuthenticated, user } = useAuth();
  const [withdrawals, setWithdrawals] = useState<WithdrawalRequest[]>(DEMO_WITHDRAWALS);
  const [selectedWithdrawal, setSelectedWithdrawal] = useState<WithdrawalRequest | null>(
    releaseId ? DEMO_WITHDRAWALS.find((w) => w.id === releaseId) || null : null
  );
  const [withdrawalReason, setWithdrawalReason] = useState("");
  const [isWithdrawing, setIsWithdrawing] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [useDemoData, setUseDemoData] = useState(false);
  const [withdrawalResult, setWithdrawalResult] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const pendingWithdrawals = useMemo(() => withdrawals.filter((w) => w.status !== "WITHDRAWN"), [withdrawals]);
  const withdrawnWithdrawals = useMemo(() => withdrawals.filter((w) => w.status === "WITHDRAWN"), [withdrawals]);

  const handleSelect = (w: WithdrawalRequest) => setSelectedWithdrawal(w);

  const handleWithdraw = async () => {
    if (!selectedWithdrawal || !withdrawalReason.trim()) return;
    setIsWithdrawing(true);
    await new Promise((r) => setTimeout(r, 2000));
    setIsWithdrawing(false);
    const updated = {
      ...selectedWithdrawal,
      status: "WITHDRAWN" as const,
      withdrawal_reason: withdrawalReason,
      withdrawn_by: user?.full_name || "Admin",
      withdrawn_at: new Date().toISOString(),
    };
    setWithdrawals((prev) => prev.map((w) => (w.id === updated.id ? updated : w)));
    setSelectedWithdrawal(updated);
    setShowConfirmDialog(false);
    setWithdrawalReason("");
    setWithdrawalResult({ type: "success", message: "Release withdrawn. Approvals revoked." });
    setUseDemoData(true);
  };

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  const renderWithdrawalResult = () => {
    if (!withdrawalResult) return null;
    return (
      <Card className={cn(withdrawalResult.type === "success" ? "border-green-200 bg-green-50/50" : "border-red-200 bg-red-50/50")}>
        <CardContent className="p-4 flex items-center gap-3">
          {withdrawalResult.type === "success" ? <CheckCircle className="h-5 w-5 text-green-600 shrink-0" /> : <XCircle className="h-5 w-5 text-red-600 shrink-0" />}
          <div>
            <p className={cn("text-sm font-medium", withdrawalResult.type === "success" ? "text-green-800" : "text-red-800")}>{withdrawalResult.message}</p>
          </div>
        </CardContent>
      </Card>
    );
  };

  const renderConfirmDialog = () => {
    if (!showConfirmDialog) return null;
    return (
      <Card className="border-red-200 bg-red-50/50 p-4">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-red-800 mb-1">Confirm Withdrawal</p>
              <p className="text-xs text-red-600">This action is irreversible and will be recorded in the audit log.</p>
              <div className="flex items-center gap-2 mt-3">
                <Button variant="ghost" size="sm" onClick={() => { setShowConfirmDialog(false); }}>Cancel</Button>
                <Button size="sm" variant="danger" onClick={handleWithdraw} disabled={isWithdrawing || withdrawalReason.trim().length < 10} loading={isWithdrawing}>
                  <XCircle className="h-4 w-4" />
                  {isWithdrawing ? "Withdrawing..." : "Confirm Withdrawal"}
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-500" />
            Release Withdrawal
            {useDemoData && <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">Withdraw a release with mandatory justification.</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge className={cn(withdrawals.filter((w) => w.status !== "WITHDRAWN").length > 0 ? "bg-amber-100 text-amber-700 border-amber-200" : "bg-green-100 text-green-700 border-green-200")}>
            {withdrawals.filter((w) => w.status !== "WITHDRAWN").length} active
          </Badge>
          <Badge className="bg-slate-100 text-slate-700 border-slate-200">{withdrawnWithdrawals.length} withdrawn</Badge>
        </div>
      </div>

      <Card className="border-red-200 bg-red-50/50">
        <CardContent className="p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-red-800">Withdrawal is irreversible</p>
            <p className="text-xs text-red-600 mt-0.5">Withdrawing a release revokes all approvals and prevents publication.</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {withdrawals.map((w) => (
            <Card
              key={w.id}
              className={cn("transition-all duration-200 animate-fade-in cursor-pointer hover:shadow-md hover:border-rg-primary-light/50", selectedWithdrawal?.id === w.id && "border-rg-primary ring-2 ring-rg-primary/20")}
              style={{ animationDelay: `${(w.id.charCodeAt(0) % 10) * 50}ms` }}
              onClick={() => handleSelect(w)}
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg", w.status === "WITHDRAWN" ? "bg-slate-100 text-slate-600" : "bg-amber-100 text-amber-600")}>
                    {w.status === "WITHDRAWN" ? <XCircle className="h-5 w-5" /> : <Clock className="h-5 w-5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-rg-text truncate">{DEMO_DATASETS.find((d) => d.id === w.dataset_id)?.name || "Unknown"}</h3>
                      <Badge variant="outline" className={cn(getStatusColor(w.status), "text-[10px]")}>{w.status}</Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-rg-text-muted mb-2">
                      <span className="font-mono">{truncateHash(w.content_hash, 8, 8)}</span>
                      <span>v{w.version_number}</span>
                      {w.withdrawn_by && <span className="flex items-center gap-1"><Shield className="h-3 w-3" />{w.withdrawn_by}</span>}
                    </div>
                    {w.withdrawal_reason && <p className="text-xs text-rg-text-muted line-clamp-1">{w.withdrawal_reason}</p>}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {withdrawals.length === 0 && (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">No releases to withdraw</h3>
                <p className="text-sm text-rg-text-muted">All releases have been processed.</p>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {selectedWithdrawal ? (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2"><Hash className="h-4 w-4 text-rg-text-muted" />Release Details</CardTitle>
                  <CardDescription>{selectedWithdrawal.status === "WITHDRAWN" ? "Withdrawn" : "Awaiting withdrawal"}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Release ID</p><p className="font-mono text-rg-text">{selectedWithdrawal.release_id}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Dataset</p><p className="text-rg-text truncate ml-2 max-w-[120px]">{DEMO_DATASETS.find((d) => d.id === selectedWithdrawal.dataset_id)?.name}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Version</p><p className="text-rg-text">v{selectedWithdrawal.version_number}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Prior Status</p><Badge variant="outline" className={cn(getStatusColor(selectedWithdrawal.prior_status), "text-[10px]")}>{selectedWithdrawal.prior_status}</Badge></div>
                  </div>

                  <div className="p-3 bg-rg-surface-alt rounded-lg">
                    <p className="text-xs text-rg-text-muted mb-1">Content Hash (SHA-256)</p>
                    <code className="block font-mono text-sm text-rg-text break-all bg-white rounded px-2 py-1.5 border border-rg-border">{selectedWithdrawal.content_hash}</code>
                  </div>

                  {selectedWithdrawal.status === "WITHDRAWN" && (
                    <div className="pt-3 border-t border-rg-border/50 space-y-1 text-xs">
                      <div className="flex justify-between"><span className="text-rg-text-muted">Withdrawn By</span><span className="text-rg-text font-medium">{selectedWithdrawal.withdrawn_by}</span></div>
                      <div className="flex justify-between"><span className="text-rg-text-muted">Withdrawn At</span><span className="text-rg-text">{formatDate(selectedWithdrawal.withdrawn_at)}</span></div>
                      <div className="pt-2 border-t border-rg-border/50"><p className="text-rg-text-muted mb-0.5">Reason</p><p className="text-rg-text bg-rg-surface rounded px-2 py-1.5 text-xs">{selectedWithdrawal.withdrawal_reason}</p></div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {selectedWithdrawal.status !== "WITHDRAWN" && (
                <Card className="border-rg-border">
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2"><XCircle className="h-4 w-4 text-red-500" />Request Withdrawal</CardTitle>
                    <CardDescription>Provide a mandatory governance justification.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <label className="text-xs text-rg-text-muted mb-1.5 block">Withdrawal Justification <span className="text-red-500">*</span></label>
                      <TextareaInput
                        value={withdrawalReason}
                        onChange={(e) => setWithdrawalReason(e.target.value)}
                        placeholder="Explain the governance reason (min 10 characters, max 500)"
                        className="w-full resize-none rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text placeholder:text-rg-text-muted focus:border-red-400 focus:ring-2 focus:ring-red-200"
                        rows={4}
                      />
                      <div className="flex justify-between mt-1">
                        <p className="text-xs text-rg-text-muted">This will be recorded in the audit log.</p>
                        <span className={cn("text-xs", withdrawalReason.length > 500 ? "text-red-500" : "text-rg-text-muted")}>{withdrawalReason.length}/500</span>
                      </div>
                    </div>

                    <Button className="w-full" disabled={isWithdrawing || withdrawalReason.trim().length < 10} onClick={handleWithdraw} loading={isWithdrawing} variant="danger">
                      <AlertTriangle className="h-4 w-4" />
                      {isWithdrawing ? "Processing..." : "Withdraw Release"}
                    </Button>

                    <p className="text-xs text-rg-text-muted flex items-start gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      <span>Withdrawing will revoke approvals, void the record, and create an audit entry.</span>
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="border-green-200 bg-green-50/50">
                  <CardContent className="p-4 flex items-center gap-3">
                    <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-green-800">Release Withdrawn</p>
                      <p className="text-xs text-green-600">Approvals have been revoked and the release cannot be published.</p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {renderWithdrawalResult()}
              {renderConfirmDialog()}
            </>
          ) : (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <XCircle className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">Select a release</h3>
                <p className="text-sm text-rg-text-muted">Choose a release to review and withdraw if necessary.</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

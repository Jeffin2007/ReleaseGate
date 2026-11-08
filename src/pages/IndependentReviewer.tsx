import { useState, useMemo } from "react";
import {
  Shield,
  CheckCircle,
  XCircle,
  Clock,
  ChevronRight,
  Loader2,
  ThumbUp,
  ThumbDown,
  HelpCircle,
  AlertTriangle,
  GitBranch,
  FileText,
  Brain,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getStatusColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_INSPECTIONS, DEMO_DATASETS, DEMO_FINDINGS } from "@/lib/api/mockData";

interface ReviewDecision {
  id: string;
  review_id: string;
  inspection_id: string;
  reviewer_type: "CHALLENGER";
  decision: "ACCEPT" | "REJECT" | "HOLD";
  reason: string;
  challenged_evidence: string[];
  confidence: number;
  created_at: string;
}

const DEMO_DECISIONS: ReviewDecision[] = [
  {
    id: "rew-001",
    review_id: "review-challenger-001",
    inspection_id: "insp-002",
    reviewer_type: "CHALLENGER",
    decision: "REJECT",
    reason: "Critical PII exposure (EMAIL_ADDRESS and PHONE_NUMBER) detected in 3,124 and 2,891 occurrences respectively. Dataset requires mandatory PII masking before any release can proceed. The Investigator's recommendation to release with documentation is not acceptable given the scale of PII exposure.",
    challenged_evidence: ["find-001", "find-002"],
    confidence: 0.94,
    created_at: "2026-10-20T15:00:00Z",
  },
  {
    id: "rew-002",
    review_id: "review-challenger-002",
    inspection_id: "insp-003",
    reviewer_type: "CHALLENGER",
    decision: "HOLD",
    reason: "Moderate risk score of 22.0 with one LOCATION PII finding and quality issues in length_of_stay column. Recommend holding for remediation of the quality issues and documentation of geographic data handling policy before proceeding. The dataset can be released after remediation with documented risk acceptance.",
    challenged_evidence: ["find-003"],
    confidence: 0.87,
    created_at: "2026-10-25T12:00:00Z",
  },
];

export function IndependentReviewer({ reviewId }: { reviewId?: string }) {
  const { isAuthenticated, user } = useAuth();
  const [selectedInspection, setSelectedInspection] = useState(DEMO_INSPECTIONS[0] || null);
  const [decisions, setDecisions] = useState<ReviewDecision[]>(DEMO_DECISIONS);
  const [isReviewing, setIsReviewing] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<"ACCEPT" | "REJECT" | "HOLD" | null>(null);
  const [reviewReason, setReviewReason] = useState("");
  const [useDemoData, setUseDemoData] = useState(false);

  const findings = useMemo(() => {
    if (!selectedInspection) return [];
    return DEMO_FINDINGS.filter((f) => f.inspection_run_id === selectedInspection.id);
  }, [selectedInspection]);

  const dataset = useMemo(() => {
    if (!selectedInspection) return null;
    return DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === selectedInspection.dataset_version_id));
  }, [selectedInspection]);

  const handleSubmitReview = async (decision: "ACCEPT" | "REJECT" | "HOLD") => {
    if (!selectedInspection || !reviewReason.trim()) return;
    setIsReviewing(true);
    await new Promise((r) => setTimeout(r, 1200));
    const newDecision: ReviewDecision = {
      id: `rew-${Date.now().toString(36)}`,
      review_id: `review-challenger-${Date.now().toString(36).slice(0, 8)}`,
      inspection_id: selectedInspection.id,
      reviewer_type: "CHALLENGER",
      decision,
      reason: reviewReason,
      challenged_evidence: findings.filter((f) => f.severity === "HIGH" || f.severity === "CRITICAL").map((f) => f.id),
      confidence: 0.9,
      created_at: new Date().toISOString(),
    };
    setDecisions((prev) => [newDecision, ...prev]);
    setReviewDecision(decision);
    setIsReviewing(false);
    setUseDemoData(true);
  };

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  const reviewing = reviewDecision === null && selectedInspection;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <Shield className="h-5 w-5 text-rg-primary" />
            Independent Reviewer
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            Challenge the primary agent&apos;s findings and recommendations.
          </p>
        </div>
      </div>

      {/* Reviewer Identity */}
      <Card className="bg-rg-primary/5 border-rg-primary/20">
        <CardContent className="p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-rg-primary text-white">
            <Brain className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-rg-text">Independent Challenger AI Reviewer</p>
            <p className="text-xs text-rg-text-muted">
              Isolated model session evaluating primary agent findings with fresh context
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-rg-text-muted">
            <CheckCircle className="h-3.5 w-3.5 text-green-500" />
            <span>Isolated context active</span>
          </div>
        </CardContent>
      </Card>

      {/* Inspection selector */}
      <Card>
        <CardContent className="p-4">
          <label className="text-xs text-rg-text-muted mb-2 block">Select Investigation to Review</label>
          <select
            value={selectedInspection?.id || ""}
            onChange={(e) => {
              const found = DEMO_INSPECTIONS.find((i) => i.id === e.target.value);
              setSelectedInspection(found || null);
              setReviewDecision(null);
              setReviewReason("");
            }}
            className="w-full h-10 rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20"
          >
            {DEMO_INSPECTIONS.map((insp) => (
              <option key={insp.id} value={insp.id}>
                {insp.inspection_type.replace(/_/g, " ")} — {insp.risk_score?.toFixed(1)} — {insp.risk_band}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-4">
          {selectedInspection ? (
            <>
              {/* Evidence summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileText className="h-4 w-4 text-rg-text-muted" />
                    Evidence Under Review
                  </CardTitle>
                  <CardDescription>
                    Primary agent findings for independent evaluation
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {findings.map((finding) => (
                    <div
                      key={finding.id}
                      className="flex items-start gap-2 p-2.5 bg-rg-surface rounded-lg border border-rg-border hover:border-rg-primary-light/30 transition-colors"
                    >
                      <Badge className={cn(
                        finding.severity === "CRITICAL" ? "bg-red-100 text-red-700 border-red-200" :
                        finding.severity === "HIGH" ? "bg-orange-100 text-orange-700 border-orange-200" :
                        finding.severity === "MEDIUM" ? "bg-amber-100 text-amber-700 border-amber-200" :
                        "bg-slate-100 text-slate-700 border-slate-200",
                        "text-[10px] shrink-0"
                      )}>
                        {finding.severity}
                      </Badge>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-rg-text">
                          {finding.category}
                          {finding.column_name && (
                            <span className="text-xs text-rg-text-muted font-mono ml-1">
                              ({finding.column_name})
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-rg-text-muted mt-0.5">{finding.message}</p>
                        <div className="flex items-center gap-2 mt-1 text-xs text-rg-text-muted">
                          <span>{finding.occurrence_count} occurrences</span>
                          <span>Evidence: {truncateHash(finding.evidence_ref.evidence_hash, 6, 4)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Reviewer Decision Form */}
              <Card className={cn(reviewing ? "" : "border-rg-primary/30 bg-rg-primary/5")}>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Shield className="h-4 w-4 text-rg-text-muted" />
                    Your Review Decision
                  </CardTitle>
                  <CardDescription>
                    As the Independent Challenger, you must challenge or accept the primary agent&apos;s findings.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {reviewing ? (
                    <>
                      <div className="grid grid-cols-3 gap-3">
                        <DecisionButton
                          icon={ThumbUp}
                          label="ACCEPT"
                          description="Findings are accurate and acceptable"
                          onClick={() => handleSubmitReview("ACCEPT")}
                          disabled={!reviewReason.trim()}
                          className="border-green-200 hover:bg-green-50 hover:border-green-300"
                        />
                        <DecisionButton
                          icon={ThumbDown}
                          label="REJECT"
                          description="Findings require significant changes"
                          onClick={() => handleSubmitReview("REJECT")}
                          disabled={!reviewReason.trim()}
                          className="border-red-200 hover:bg-red-50 hover:border-red-300"
                        />
                        <DecisionButton
                          icon={HelpCircle}
                          label="HOLD"
                          description="Hold for further remediation"
                          onClick={() => handleSubmitReview("HOLD")}
                          disabled={!reviewReason.trim()}
                          className="border-amber-200 hover:bg-amber-50 hover:border-amber-300"
                        />
                      </div>

                      <div>
                        <label className="text-xs text-rg-text-muted mb-1.5 block">
                          Review Justification <span className="text-red-500">*</span>
                        </label>
                        <textarea
                          value={reviewReason}
                          onChange={(e) => setReviewReason(e.target.value)}
                          placeholder="Explain your decision with reference to evidence..."
                          className="w-full resize-none rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text placeholder:text-rg-text-muted focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20"
                          rows={4}
                        />
                        <div className="flex justify-between mt-1">
                          <p className="text-xs text-rg-text-muted">
                            Reference specific findings and evidence to support your decision.
                          </p>
                          <span className={cn("text-xs", reviewReason.length > 1000 ? "text-red-500" : "text-rg-text-muted")}>
                            {reviewReason.length}/1000
                          </span>
                        </div>
                      </div>

                      <Button
                        className="w-full"
                        disabled={!reviewReason.trim()}
                        onClick={() => handleSubmitReview(reviewDecision!)}
                        loading={isReviewing}
                      >
                        <Shield className="h-4 w-4" />
                        Submit Challenger Review
                      </Button>
                    </>
                  ) : (
                    <div className="flex items-center gap-3 p-4 bg-rg-surface rounded-lg border border-rg-border">
                      <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-rg-text">Review submitted</p>
                        <p className="text-xs text-rg-text-muted">
                          Decision: <span className="text-rg-text font-semibold capitalize">{reviewDecision}</span>
                          {" • "}
                          {formatDate(new Date().toISOString())}
                        </p>
                      </div>
                      <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setReviewDecision(null)}>
                        Submit another
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Past Reviews */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Clock className="h-4 w-4 text-rg-text-muted" />
                    Review History
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {decisions
                    .filter((d) => d.inspection_id === selectedInspection.id || !reviewId)
                    .slice(0, 3)
                    .map((decision) => (
                      <div
                        key={decision.id}
                        className="p-3 bg-rg-surface rounded-lg border border-rg-border"
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <Badge className={cn(
                            decision.decision === "ACCEPT" ? "bg-green-100 text-green-700 border-green-200" :
                            decision.decision === "REJECT" ? "bg-red-100 text-red-700 border-red-200" :
                            "bg-amber-100 text-amber-700 border-amber-200",
                            "text-xs font-medium"
                          )}>
                            {decision.decision}
                          </Badge>
                          <span className="text-xs text-rg-text-muted">
                            {decision.reviewer_type} • {formatDate(decision.created_at)}
                          </span>
                        </div>
                        <p className="text-xs text-rg-text-muted line-clamp-2">{decision.reason}</p>
                        {decision.challenged_evidence.length > 0 && (
                          <div className="flex items-center gap-1 mt-1.5">
                            <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
                            <span className="text-xs text-amber-600">
                              Challenged {decision.challenged_evidence.length} evidence{" "}
                              {decision.challenged_evidence.length === 1 ? "item" : "items"}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  {decisions.filter((d) => d.inspection_id === selectedInspection.id).length === 0 && (
                    <p className="text-sm text-rg-text-muted text-center py-4">
                      No reviews for this investigation yet.
                    </p>
                  )}
                </CardContent>
              </Card>
            </>
          ) : (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Shield className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">No investigation selected</h3>
                <p className="text-sm text-rg-text-muted">Select an investigation to review.</p>
              </div>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Review Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="h-4 w-4 text-rg-text-muted" />
                Review Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {selectedInspection && (
                <>
                  <div className="flex justify-between">
                    <span className="text-rg-text-muted">Dataset</span>
                    <span className="text-rg-text truncate ml-2 max-w-[120px]">{dataset?.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-rg-text-muted">Risk Score</span>
                    <span className="text-rg-text font-medium">{selectedInspection.risk_score?.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-rg-text-muted">Risk Band</span>
                    <Badge className={cn(getRiskBadgeClass(selectedInspection.risk_band))}>
                      {selectedInspection.risk_band}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-rg-text-muted">Findings</span>
                    <span className="text-rg-text">{findings.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-rg-text-muted">High/Critical</span>
                    <span className="text-rg-text font-medium">
                      {findings.filter((f) => f.severity === "HIGH" || f.severity === "CRITICAL").length}
                    </span>
                  </div>
                  <div className="flex justify-between pt-2 border-t border-rg-border/50">
                    <span className="text-rg-text-muted">Reviewer Type</span>
                    <span className="text-rg-text font-medium">Independent Challenger</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Decision Guidelines */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <HelpCircle className="h-4 w-4 text-rg-text-muted" />
                Decision Guidelines
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-rg-text-muted">
              <p><strong className="text-rg-text">ACCEPT:</strong> Findings are accurate and the primary agent&apos;s recommendation is sound.</p>
              <p><strong className="text-rg-text">REJECT:</strong> Findings have errors, omissions, or the recommendation is unsafe.</p>
              <p><strong className="text-rg-text">HOLD:</strong> More information or remediation is needed before a decision.</p>
              <div className="pt-2 border-t border-rg-border/50">
                <p className="text-rg-text-muted">The Challenger reviews with an isolated context and must cite specific evidence.</p>
              </div>
            </CardContent>
          </Card>

          {/* Reviewer identity info */}
          <Card className="bg-rg-primary/5 border-rg-primary/20">
            <CardContent className="p-4 text-xs text-rg-text-muted space-y-1">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                <span>Independent Challenger AI Reviewer session</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                <span>Isolated model context — no shared state with primary agent</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                <span>Review comments require specific evidence citations</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                <span>Decisions recorded in audit log with timestamp</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DecisionButton({
  icon: Icon,
  label,
  description,
  onClick,
  disabled,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  description: string;
  onClick: () => void;
  disabled: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex flex-col items-center gap-1 p-3 rounded-lg border-2 transition-all duration-150",
        disabled
          ? "border-rg-border bg-rg-surface-alt text-rg-text-muted cursor-not-allowed opacity-60"
          : className,
        "hover:shadow-sm"
      )}
    >
      <Icon className={cn("h-5 w-5", disabled ? "text-rg-text-muted" : "text-rg-text")} />
      <span className={cn("text-xs font-semibold", disabled ? "text-rg-text-muted" : "text-rg-text")}>
        {label}
      </span>
      <span className="text-[10px] text-rg-text-muted">{description}</span>
    </button>
  );
}

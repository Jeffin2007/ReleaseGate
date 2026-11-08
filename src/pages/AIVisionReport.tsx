import { useState, useMemo } from "react";
import {
  FileSearch,
  Brain,
  Clock,
  ChevronRight,
  AlertTriangle,
  Shield,
  CheckCircle,
  XCircle,
  Loader2,
  GitBranch,
  FileText,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getRiskColor, getStatusColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_INSPECTIONS, DEMO_DATASETS, DEMO_FINDINGS } from "@/lib/api/mockData";

export function AIVisionReport() {
  const { isAuthenticated } = useAuth();
  const [selectedInspection, setSelectedInspection] = useState(DEMO_INSPECTIONS[0] || null);
  const [useDemoData, setUseDemoData] = useState(false);

  const findings = useMemo(() => {
    if (!selectedInspection) return [];
    return DEMO_FINDINGS.filter((f) => f.inspection_run_id === selectedInspection.id);
  }, [selectedInspection]);

  const dataset = useMemo(() => {
    if (!selectedInspection) return null;
    return DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === selectedInspection.dataset_version_id));
  }, [selectedInspection]);

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
            <Brain className="h-5 w-5 text-rg-primary" />
            AI Investigation Report
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            Evidence-linked AI investigation conclusions with tool activity and iteration tracking.
          </p>
        </div>
      </div>

      {/* Inspection selector */}
      <Card>
        <CardContent className="p-4">
          <label className="text-xs text-rg-text-muted mb-2 block">Select Investigation Run</label>
          <select
            value={selectedInspection?.id || ""}
            onChange={(e) => {
              const found = DEMO_INSPECTIONS.find((i) => i.id === e.target.value);
              setSelectedInspection(found || null);
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

      {selectedInspection ? (
        <>
          {/* Report overview */}
          <div className="grid lg:grid-cols-3 gap-6">
            {/* Main report */}
            <div className="lg:col-span-2 space-y-6">
              {/* AI Vision Header */}
              <Card className="border-rg-primary/20 bg-rg-primary/5">
                <CardContent className="p-5">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-rg-primary text-white">
                      <Brain className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <h2 className="text-base font-semibold text-rg-text">AI Investigation Report</h2>
                      <p className="text-xs text-rg-text-muted mt-0.5">
                        Bounded investigation with {selectedInspection.findings_count} findings across {selectedInspection.summary_report?.profiling?.column_count || 0} columns
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <Badge variant="outline" className={cn(getStatusColor(selectedInspection.status))}>
                          {selectedInspection.status}
                        </Badge>
                        <Badge className={cn(getRiskBadgeClass(selectedInspection.risk_band))}>
                          {selectedInspection.risk_band}
                        </Badge>
                        <span className="text-xs text-rg-text-muted">
                          Iteration 3 of 8 • Stopped: {selectedInspection.is_release_eligible ? "COMPLETED" : "POLICY_BLOCKED"}
                        </span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Evidence-Linked Conclusions */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileText className="h-4 w-4 text-rg-text-muted" />
                    Evidence-Linked Conclusions
                  </CardTitle>
                  <CardDescription>AI-generated findings backed by inspection evidence</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {findings.slice(0, 3).map((finding, idx) => (
                    <div
                      key={finding.id}
                      className="p-3 bg-rg-surface rounded-lg border border-rg-border hover:border-rg-primary-light/30 transition-colors"
                    >
                      <div className="flex items-start gap-2 mb-1">
                        <Badge className={cn(
                          finding.finding_type === "PII" ? "bg-red-100 text-red-700 border-red-200" :
                          finding.finding_type === "QUALITY" ? "bg-amber-100 text-amber-700 border-amber-200" :
                          "bg-blue-100 text-blue-700 border-blue-200",
                          "text-[10px] shrink-0"
                        )}>
                          {finding.finding_type}
                        </Badge>
                        <span className={cn("text-sm font-medium capitalize", getStatusColor(finding.severity).split(" ")[0].replace("text-", "text-"))}>
                          {finding.category}
                        </span>
                        {finding.column_name && (
                          <code className="text-xs text-rg-text-muted bg-rg-surface-alt px-1.5 py-0.5 rounded font-mono">
                            {finding.column_name}
                          </code>
                        )}
                      </div>
                      <p className="text-xs text-rg-text-muted mb-2">{finding.message}</p>
                      <div className="flex items-center gap-3 text-xs text-rg-text-muted">
                        <span className="flex items-center gap-1">
                          <Shield className="h-3 w-3" />
                          {finding.occurrence_count} occurrences
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          Evidence: {truncateHash(finding.evidence_ref.evidence_hash, 8, 8)}
                        </span>
                        <a
                          href={`/findings/${finding.id}`}
                          className="text-rg-primary hover:text-rg-primary-dark flex items-center gap-1"
                        >
                          View evidence <ChevronRight className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                  ))}
                  {findings.length > 3 && (
                    <p className="text-xs text-rg-text-muted text-center pt-2">
                      +{findings.length - 3} more finding{findings.length - 3 !== 1 ? "s" : ""}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Tool Activity Log */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <GitBranch className="h-4 w-4 text-rg-text-muted" />
                    Tool Activity Log
                  </CardTitle>
                  <CardDescription>Bounded investigation tool calls with iteration tracking</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {[
                    { tool: "inspect_dataset", status: "success", detail: "Profiled 5 columns, 1500 rows" },
                    { tool: "detect_sensitive_data", status: "success", detail: "Found 4 PII findings (EMAIL_ADDRESS, PHONE_NUMBER)" },
                    { tool: "validate_data_quality", status: "success", detail: "22/24 rules passed, 2 failures" },
                    { tool: "check_release_policy", status: "success", detail: "Risk score 12.5 — LOW band, eligible for release" },
                    { tool: "propose_transformation", status: "skipped", detail: "No transformation required (LOW risk)" },
                  ].map((log, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 hover:bg-rg-surface-alt/50 rounded-md transition-colors text-sm">
                      <div className={cn(
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs",
                        log.status === "success" ? "bg-green-100 text-green-600" :
                        log.status === "skipped" ? "bg-slate-100 text-slate-500" :
                        "bg-red-100 text-red-600"
                      )}>
                        {log.status === "success" ? (
                          <CheckCircle className="h-3.5 w-3.5" />
                        ) : log.status === "skipped" ? (
                          <GitBranch className="h-3.5 w-3.5" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5" />
                        )}
                      </div>
                      <code className="text-xs font-mono text-rg-text w-32 shrink-0">{log.tool}</code>
                      <span className="text-xs text-rg-text-muted truncate">{log.detail}</span>
                    </div>
                  ))}
                  <div className="pt-2 border-t border-rg-border/50 flex items-center justify-between text-xs text-rg-text-muted">
                    <span>Total tool calls: 5 of 12 budget</span>
                    <span>Iteration: 3/8</span>
                  </div>
                </CardContent>
              </Card>

              {/* Stop Reason */}
              <Card className={cn(
                selectedInspection.is_release_eligible ?
                  "border-green-200 bg-green-50/50" :
                  "border-red-200 bg-red-50/50"
              )}>
                <CardContent className="p-4 flex items-start gap-3">
                  {selectedInspection.is_release_eligible ? (
                    <CheckCircle className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                  )}
                  <div>
                    <p className={cn(
                      "text-sm font-medium",
                      selectedInspection.is_release_eligible ? "text-green-800" : "text-amber-800"
                    )}>
                      {selectedInspection.is_release_eligible ? "Investigation Completed Successfully" : "Investigation Halted — Policy Block"}
                    </p>
                    <p className="text-xs text-rg-text-muted mt-0.5">
                      {selectedInspection.is_release_eligible
                        ? "All inspection steps completed within budget. No critical or high-severity findings requiring intervention. Dataset is eligible for release with standard human approval."
                        : "Investigation stopped due to policy violation. The AI recommendation cannot proceed without human review and remediation."}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Sidebar */}
            <div className="space-y-4">
              {/* Risk Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Shield className="h-4 w-4 text-rg-text-muted" />
                    Risk Assessment
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-rg-surface rounded-lg">
                    <span className="text-sm text-rg-text-muted">Total Risk Score</span>
                    <span className="text-2xl font-bold text-rg-text">{selectedInspection.risk_score?.toFixed(1)}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-rg-surface rounded-lg">
                    <span className="text-sm text-rg-text-muted">Risk Band</span>
                    <Badge className={cn(getRiskBadgeClass(selectedInspection.risk_band))}>
                      {selectedInspection.risk_band}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-rg-surface rounded-lg">
                    <span className="text-sm text-rg-text-muted">Release Eligible</span>
                    <Badge variant={selectedInspection.is_release_eligible ? "success" : "error"}>
                      {selectedInspection.is_release_eligible ? "Yes" : "No"}
                    </Badge>
                  </div>
                  {selectedInspection.summary_report?.risk_assessment?.blocking_reasons?.length > 0 && (
                    <div className="pt-3 border-t border-rg-border/50 space-y-1">
                      <p className="text-xs text-rg-text-muted uppercase tracking-wider">Blocking Reasons</p>
                      {selectedInspection.summary_report.risk_assessment.blocking_reasons.map((reason: string, i: number) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-rg-text">
                          <XCircle className="h-3 w-3 text-red-500 shrink-0 mt-0.5" />
                          {reason}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Dataset Info */}
              {dataset && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <FileText className="h-4 w-4 text-rg-text-muted" />
                      Dataset
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-sm font-medium text-rg-text">{dataset.name}</p>
                    <p className="text-xs text-rg-text-muted">{dataset.description}</p>
                    <div className="pt-2 border-t border-rg-border/50 space-y-1 text-xs text-rg-text-muted">
                      <div className="flex justify-between"><span>Version</span><span className="font-mono text-rg-text">v{dataset.versions[0]?.version_number}</span></div>
                      <div className="flex justify-between"><span>Format</span><span className="font-mono text-rg-text">{dataset.versions[0]?.file_format?.toUpperCase()}</span></div>
                      <div className="flex justify-between"><span>Size</span><span className="text-rg-text">{dataset.versions[0]?.file_size ? `${dataset.versions[0].file_size} bytes` : "—"}</span></div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Investigation Parameters */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Clock className="h-4 w-4 text-rg-text-muted" />
                    Investigation Parameters
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Max Tool Calls</span>
                    <span className="text-rg-text">12</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Max Iterations</span>
                    <span className="text-rg-text">8</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Controlled Rewrites</span>
                    <span className="text-rg-text">1</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Execution Retries</span>
                    <span className="text-rg-text">3</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Actual Tool Calls</span>
                    <span className="text-rg-text font-medium">5</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Actual Iterations</span>
                    <span className="text-rg-text font-medium">3</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rg-text-muted">Stop Reason</span>
                    <span className="text-rg-text font-medium">{selectedInspection.is_release_eligible ? "COMPLETED" : "POLICY_BLOCKED"}</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : (
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <Brain className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-semibold text-rg-text mb-1">No investigation report</h3>
            <p className="text-sm text-rg-text-muted">Select an investigation run to view the AI report.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

import { useState } from "react";
import {
  GitBranch,
  Hash,
  Shield,
  CheckCircle,
  AlertTriangle,
  Clock,
  ChevronRight,
  Loader2,
  FileText,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn, formatDate, formatBytes, truncateHash, getRiskBadgeClass, getStatusColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_INSPECTIONS, DEMO_DATASETS } from "@/lib/api/mockData";

export function ReleasePreparation({ releaseId }: { releaseId?: string }) {
  const { isAuthenticated } = useAuth();
  const [selectedInspection, setSelectedInspection] = useState(DEMO_INSPECTIONS[0] || null);
  const [releaseNotes, setReleaseNotes] = useState("");
  const [destinationTarget, setDestinationTarget] = useState("s3://release-evidence/exports");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [useDemoData, setUseDemoData] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const dataset = selectedInspection ? DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === selectedInspection.dataset_version_id)) : null;
  const latestVersion = dataset?.versions[dataset.versions.length - 1];

  const handleSubmit = async () => {
    if (!selectedInspection) return;
    setIsSubmitting(true);
    await new Promise((r) => setTimeout(r, 2000));
    setIsSubmitting(false);
    setSubmitted(true);
    setUseDemoData(true);
  };

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-rg-primary" />
            Release Preparation
            {useDemoData && <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">Stage a release with exact version details and review before human approval.</p>
        </div>
      </div>

      <Card className={submitted ? "border-green-200 bg-green-50/50" : "border-rg-border"}>
        <CardContent className="p-6">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="text-base font-semibold text-rg-text flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-rg-primary" />
                {submitted ? "Release Prepared" : "Prepare Release"}
              </h2>
              <p className="text-xs text-rg-text-muted mt-0.5">Stage an immutable release package with exact version and artifact details</p>
            </div>
            {submitted && <Badge className="bg-green-100 text-green-700 border-green-200 text-xs font-medium px-2.5 py-1"><CheckCircle className="h-3 w-3 inline mr-1" />Prepared</Badge>}
          </div>

          {!submitted ? (
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-xs text-rg-text-muted uppercase tracking-wider">Dataset Version</label>
                <select
                  value={selectedInspection?.id || ""}
                  onChange={(e) => { const found = DEMO_INSPECTIONS.find((i) => i.id === e.target.value); setSelectedInspection(found || null); }}
                  className="w-full h-10 rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20"
                >
                  {DEMO_INSPECTIONS.map((insp) => (
                    <option key={insp.id} value={insp.id}>{insp.inspection_type.replace(/_/g, " ")} — {formatDate(insp.completed_at)}</option>
                  ))}
                </select>
              </div>

              {selectedInspection && latestVersion && dataset && (
                <>
                  <div className="grid sm:grid-cols-2 gap-4 mb-5">
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Dataset</p><p className="text-sm font-medium text-rg-text">{dataset.name}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Version</p><p className="text-sm font-medium text-rg-text">v{latestVersion.version_number}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Format</p><p className="text-sm font-medium text-rg-text">{latestVersion.file_format.toUpperCase()}</p></div>
                    <div className="space-y-0.5"><p className="text-xs text-rg-text-muted">Size</p><p className="text-sm font-medium text-rg-text">{formatBytes(latestVersion.file_size)}</p></div>
                  </div>

                  <Card className="bg-rg-surface-alt/50 border-rg-border/80">
                    <CardContent className="p-4">
                      <h3 className="text-sm font-semibold text-rg-text mb-3 flex items-center gap-2"><Hash className="h-4 w-4 text-rg-text-muted" />Artifact Hash (SHA-256)</h3>
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <code className="flex-1 font-mono text-sm text-rg-text truncate bg-rg-surface rounded px-3 py-2 border border-rg-border">{latestVersion.content_hash}</code>
                          <button onClick={() => navigator.clipboard.writeText(latestVersion.content_hash)} className="p-2 text-rg-text-muted hover:text-rg-primary hover:bg-rg-surface-alt rounded transition-colors shrink-0" title="Copy hash"><Hash className="h-4 w-4" /></button>
                        </div>
                        <p className="text-xs text-rg-text-muted">This hash binds the release to the exact dataset version. Any modification invalidates the release.</p>
                        <div className="pt-2 border-t border-rg-border/50 text-xs text-rg-text-muted"><div className="flex justify-between"><span>Opaque Artifact Reference</span><span className="font-mono text-rg-text truncate ml-2 max-w-[200px]">{latestVersion.local_artifact_ref}</span></div></div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-3"><CardTitle className="text-sm flex items-center gap-2"><Shield className="h-4 w-4 text-rg-text-muted" />Inspection Result</CardTitle></CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex items-center justify-between"><span className="text-xs text-rg-text-muted">Risk Score</span><span className="text-sm font-medium text-rg-text">{selectedInspection.risk_score?.toFixed(1)}</span></div>
                      <div className="flex items-center justify-between"><span className="text-xs text-rg-text-muted">Risk Band</span><Badge className={getRiskBadgeClass(selectedInspection.risk_band)}>{selectedInspection.risk_band}</Badge></div>
                      <div className="flex items-center justify-between"><span className="text-xs text-rg-text-muted">Release Eligible</span><Badge variant={selectedInspection.is_release_eligible ? "success" : "error"}>{selectedInspection.is_release_eligible ? "Yes" : "No"}</Badge></div>
                      <div className="flex items-center justify-between"><span className="text-xs text-rg-text-muted">Policy Version</span><span className="text-xs text-rg-text">{selectedInspection.policy_version}</span></div>
                      <div className="flex items-center justify-between"><span className="text-xs text-rg-text-muted">Status</span><Badge variant="outline" className={getStatusColor(selectedInspection.status)}>{selectedInspection.status}</Badge></div>
                      {selectedInspection.summary_report?.risk_assessment?.blocking_reasons?.length > 0 && (
                        <div className="pt-2 border-t border-rg-border/50 space-y-1"><p className="text-xs text-rg-text-muted uppercase tracking-wider">Blocking Reasons</p>
                          {selectedInspection.summary_report.risk_assessment.blocking_reasons.map((reason: string, i: number) => (
                            <p key={i} className="text-xs text-red-600 flex items-start gap-1.5"><AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />{reason}</p>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <div className="space-y-2">
                    <label className="text-xs text-rg-text-muted uppercase tracking-wider">Destination Target</label>
                    <select value={destinationTarget} onChange={(e) => setDestinationTarget(e.target.value)} className="w-full h-10 rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20">
                      <option value="s3://release-evidence/exports">s3://release-evidence/exports</option>
                      <option value="gcs://release-governance/staging">gcs://release-governance/staging</option>
                      <option value="bigquery://release-gate.datasets">bigquery://release-gate.datasets</option>
                      <option value="internal://governance/review">internal://governance/review (Review only)</option>
                    </select>
                    <p className="text-xs text-rg-text-muted">Approved destination URI. Publication requires human approval before transfer.</p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs text-rg-text-muted uppercase tracking-wider">Release Notes (Optional)</label>
                    <textarea value={releaseNotes} onChange={(e) => setReleaseNotes(e.target.value)} placeholder="Provide context and notes for this release..." className="w-full resize-none rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text placeholder:text-rg-text-muted focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20" rows={3} />
                  </div>
                </>
              )}

              <div className="flex items-center justify-between pt-2">
                <div className="text-xs text-rg-text-muted">{selectedInspection?.is_release_eligible ? "Dataset is eligible for release. Submit for human approval." : "Dataset is blocked by policy. Address blocking issues before release."}</div>
                <Button size="sm" disabled={isSubmitting || !selectedInspection?.is_release_eligible} onClick={handleSubmit} loading={isSubmitting} className="gap-2"><GitBranch className="h-4 w-4" />{isSubmitting ? "Staging Release…" : "Stage Release for Approval"}</Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 p-4 bg-green-50 rounded-lg border border-green-200">
              <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
              <div><p className="text-sm font-medium text-green-800">Release Prepared Successfully</p><p className="text-xs text-green-600 mt-0.5">Release staged with hash-bound evidence baseline. Ready for human approval.</p></div>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setSubmitted(false)}>Prepare another</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <h4 className="text-xs font-semibold text-rg-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5"><Shield className="h-3.5 w-3.5" />Release Preparation Notes</h4>
          <ul className="text-xs text-rg-text-muted space-y-1.5">
            <li className="flex items-start gap-1.5"><CheckCircle className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />Release binds to the exact SHA-256 content hash of the dataset version.</li>
            <li className="flex items-start gap-1.5"><CheckCircle className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />Any modification to the dataset after staging invalidates the release.</li>
            <li className="flex items-start gap-1.5"><CheckCircle className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />A human approver must verify and sign the exact artifact hash before publication.</li>
            <li className="flex items-start gap-1.5"><CheckCircle className="h-3 w-3 text-green-500 shrink-0 mt-0.5" />Publication is idempotent — repeated approvals with the same hash are safe.</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

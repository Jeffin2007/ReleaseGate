import { useEffect, useState } from "react";
import {
  ArrowLeft,
  AlertTriangle,
  Shield,
  Clock,
  Hash,
  ChevronRight,
  Loader2,
  Eye,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn, formatDate, truncateHash, getSeverityColor, getRiskBadgeClass } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_FINDINGS, DEMO_INSPECTIONS, DEMO_DATASETS } from "@/lib/api/mockData";

interface FindingDetailProps {
  findingId: string;
}

export function FindingDetail({ findingId }: FindingDetailProps) {
  const { isAuthenticated } = useAuth();
  const [finding, setFinding] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [useDemoData, setUseDemoData] = useState(false);

  useEffect(() => {
    const found = DEMO_FINDINGS.find((f) => f.id === findingId);
    if (found) {
      setFinding(found);
      setUseDemoData(true);
    }
    setIsLoading(false);
  }, [findingId]);

  const inspection = finding ? DEMO_INSPECTIONS.find((i) => i.id === finding.inspection_run_id) : null;
  const dataset = inspection ? DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === inspection.dataset_version_id)) : null;

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 text-rg-primary animate-spin" />
      </div>
    );
  }

  if (!finding) {
    return (
      <div className="space-y-6 animate-fade-in">
        <a href="/inspections" className="inline-flex items-center gap-1.5 text-sm text-rg-text-muted hover:text-rg-text transition-colors">
          <ArrowLeft className="h-4 w-4" />
          Back to Inspections
        </a>
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <AlertTriangle className="h-12 w-12 text-red-400 mb-4" />
            <h3 className="text-lg font-semibold text-rg-text mb-1">Finding not found</h3>
            <p className="text-sm text-rg-text-muted mb-4">
              The finding you&apos;re looking for doesn&apos;t exist.
            </p>
            <Button asChild>
              <a href="/inspections">Return to inspections</a>
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Back button */}
      <a
        href="/inspections"
        className="inline-flex items-center gap-1.5 text-sm text-rg-text-muted hover:text-rg-text transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Inspections
      </a>

      {/* Header */}
      <div className="flex items-start gap-4">
        <div className={cn("flex h-14 w-14 shrink-0 items-center justify-center rounded-xl", getSeverityColor(finding.severity).split(" ")[1])}>
          <AlertTriangle className="h-7 w-7 text-white" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold text-rg-text">{finding.category}</h1>
            <Badge className={cn(getSeverityColor(finding.severity).split(" ")[1], "font-medium")}>
              {finding.severity}
            </Badge>
            <Badge className={cn("text-[10px]", finding.finding_type === "PII" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700")}>
              {finding.finding_type}
            </Badge>
          </div>
          <p className="text-sm text-rg-text-muted">{finding.message}</p>
        </div>
      </div>

      {/* Metadata cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <InfoCard label="Finding Type" value={finding.finding_type} icon={Shield} />
        <InfoCard label="Severity" value={finding.severity} icon={AlertTriangle} color={getSeverityColor(finding.severity).split(" ")[1] || undefined} />
        <InfoCard label="Occurrences" value={finding.occurrence_count} icon={Hash} />
        <InfoCard label="Confidence" value={finding.confidence_score?.toFixed(4) || "—"} icon={Shield} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Affected column */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Hash className="h-4 w-4 text-rg-text-muted" />
                Affected Column
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rg-surface-alt text-rg-text-muted font-mono text-sm">
                  {finding.column_name || "—"}
                </div>
                <div className="text-sm text-rg-text-muted">
                  Column in {dataset?.name || "dataset"}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Evidence reference */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Eye className="h-4 w-4 text-rg-text-muted" />
                Evidence Reference
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {finding.evidence_ref && (
                <dl className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <dt className="text-xs text-rg-text-muted">Evidence Hash (SHA-256)</dt>
                    <dd className="text-sm font-mono text-rg-text break-all">
                      {finding.evidence_ref.evidence_hash}
                      <button
                        onClick={() => navigator.clipboard.writeText(finding.evidence_ref.evidence_hash)}
                        className="ml-2 text-rg-primary hover:text-rg-primary-dark"
                        title="Copy hash"
                      >
                        <Hash className="h-3.5 w-3.5 inline" />
                      </button>
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-rg-text-muted">Matched Count</dt>
                    <dd className="text-sm font-medium text-rg-text">{finding.evidence_ref.matched_count}</dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-rg-text-muted">Sample Row Indices</dt>
                    <dd className="text-sm text-rg-text font-mono">
                      {finding.evidence_ref.sample_row_indices?.join(", ") || "—"}
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-rg-text-muted">Length Distribution</dt>
                    <dd className="text-sm text-rg-text-muted">
                      {finding.evidence_ref.length_distribution ? (
                        Object.entries(finding.evidence_ref.length_distribution)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(", ")
                      ) : "—"}
                    </dd>
                  </div>
                </dl>
              )}
              <div className="pt-3 border-t border-rg-border/50 flex items-center justify-between text-xs">
                <span className="text-rg-text-muted">Created at</span>
                <span className="text-rg-text">{formatDate(finding.created_at)}</span>
              </div>
            </CardContent>
          </Card>

          {/* Dataset & inspection context */}
          {dataset && inspection && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Clock className="h-4 w-4 text-rg-text-muted" />
                  Context
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-3 p-3 bg-rg-surface-alt rounded-lg">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-rg-primary/10 text-rg-primary">
                    <Shield className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-rg-text">{dataset.name}</p>
                    <p className="text-xs text-rg-text-muted">
                      Version {inspection.dataset_version_id?.slice(0, 8)} • {formatDate(inspection.completed_at)}
                    </p>
                  </div>
                  <Badge className={cn("ml-auto", getRiskBadgeClass(inspection.risk_band))}>
                    {inspection.risk_score?.toFixed(1)} — {inspection.risk_band}
                  </Badge>
                </div>
                <div className="text-xs text-rg-text-muted space-y-1">
                  <div className="flex justify-between">
                    <span>Inspection ID</span>
                    <span className="font-mono text-rg-text">{inspection.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Dataset Version ID</span>
                    <span className="font-mono text-rg-text">{inspection.dataset_version_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Finding ID</span>
                    <span className="font-mono text-rg-text">{finding.id}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Remediation recommendation */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="h-4 w-4 text-rg-primary" />
                Remediation Recommendation
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="p-3 bg-rg-primary/5 border border-rg-primary/20 rounded-lg">
                <p className="text-sm text-rg-text">
                  {finding.finding_type === "PII" ? (
                    <>
                      Apply PII masking or pseudonymization to the <strong>{finding.column_name}</strong> column before release.
                      {" "}Use{" "}
                      <code className="px-1.5 py-0.5 bg-rg-surface-alt rounded text-xs font-mono">partial_email</code>{" "}
                      or <code className="px-1.5 py-0.5 bg-rg-surface-alt rounded text-xs font-mono">pseudonymize_column</code>{" "}
                      transformation operations.
                    </>
                  ) : finding.finding_type === "QUALITY" ? (
                    <>
                      Review data quality issues in the <strong>{finding.column_name}</strong> column.
                      {" "}Consider imputation, validation rules, or data cleansing before release.
                    </>
                  ) : (
                    <>
                      Review the policy concern regarding <strong>{finding.category}</strong>.
                      {" "}Document risk acceptance or apply appropriate remediation.
                    </>
                  )}
                </p>
              </div>
              <Button variant="secondary" className="w-full" size="sm" asChild>
                <a href="/transformations" className="flex items-center justify-center gap-2">
                  <ChevronRight className="h-4 w-4" />
                  Apply Transformation
                </a>
              </Button>
            </CardContent>
          </Card>

          {/* Severity indicator */}
          <Card className={cn(getSeverityColor(finding.severity).split(" ")[1] ? `border-l-4 ${getSeverityColor(finding.severity).split(" ")[1].replace("text-", "border-")} border-rg-border bg-white` : "border-rg-border")}>
            <CardContent className="p-4 text-center">
              <div className={cn("inline-flex h-12 w-12 items-center justify-center rounded-full mb-2", getSeverityColor(finding.severity).split(" ")[1])}>
                <AlertTriangle className="h-6 w-6 text-white" />
              </div>
              <p className="text-xs text-rg-text-muted">
                This finding has <span className={cn("font-semibold", getSeverityColor(finding.severity).split(" ")[0].replace("text-", ""))}>{finding.severity}</span> severity
              </p>
              <p className="text-xs text-rg-text-muted mt-1">
                {finding.severity === "CRITICAL" && "Immediate remediation required before any release."}
                {finding.severity === "HIGH" && "Remediation strongly recommended before release."}
                {finding.severity === "MEDIUM" && "Remediation recommended with documented justification."}
                {finding.severity === "LOW" && "Low priority; document and monitor."}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function InfoCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: React.ComponentType<{ className?: string }>; color?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Icon className={cn("h-4 w-4", color ? color : "text-rg-text-muted")} />
          <span className="text-xs text-rg-text-muted uppercase tracking-wider">{label}</span>
        </div>
        <p className="text-sm font-medium text-rg-text">{value as string}</p>
      </CardContent>
    </Card>
  );
}

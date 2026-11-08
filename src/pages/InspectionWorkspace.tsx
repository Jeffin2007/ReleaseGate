import { useEffect, useState, useMemo } from "react";
import {
  FileSearch,
  AlertTriangle,
  CheckCircle,
  Shield,
  Clock,
  BarChart3,
  Filter,
  ChevronDown,
  Eye,
  Loader2,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getRiskColor, getStatusColor, getSeverityColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import type { InspectionRun, Finding } from "@/lib/api";
import { DEMO_INSPECTIONS, DEMO_FINDINGS, DEMO_DATASETS } from "@/lib/api/mockData";

interface InspectionWorkspaceProps {
  inspectionId?: string;
}

const FINDING_TYPE_COLORS: Record<string, string> = {
  PII: "bg-red-100 text-red-700 border-red-200",
  QUALITY: "bg-amber-100 text-amber-700 border-amber-200",
  POLICY: "bg-orange-100 text-orange-700 border-orange-200",
  PROVENANCE: "bg-blue-100 text-blue-700 border-blue-200",
};

export function InspectionWorkspace({ inspectionId }: InspectionWorkspaceProps) {
  const { isAuthenticated } = useAuth();
  const [inspections, setInspections] = useState<InspectionRun[]>([]);
  const [selectedInspection, setSelectedInspection] = useState<InspectionRun | null>(null);
  const [selectedFindings, setSelectedFindings] = useState<Finding[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [useDemoData, setUseDemoData] = useState(false);
  const [filterType, setFilterType] = useState<string>("ALL");
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");

  useEffect(() => {
    const fetchInspections = async () => {
      setIsLoading(true);
      try {
        // Try to fetch real inspections
        const mockResult = DEMO_INSPECTIONS;
        if (mockResult.length > 0) {
          setInspections(mockResult);
          setUseDemoData(true);
          if (inspectionId) {
            const found = mockResult.find((i) => i.id === inspectionId);
            if (found) {
              setSelectedInspection(found);
              setSelectedFindings(DEMO_FINDINGS.filter((f) => f.inspection_run_id === inspectionId));
            }
          } else {
            setSelectedInspection(mockResult[0] || null);
            if (mockResult[0]) {
              setSelectedFindings(DEMO_FINDINGS.filter((f) => f.inspection_run_id === mockResult[0].id));
            }
          }
        }
      } catch {
        setInspections([]);
      } finally {
        setIsLoading(false);
      }
    };
    fetchInspections();
  }, [inspectionId]);

  const filteredFindings = useMemo(() => {
    let findings = selectedInspection ? DEMO_FINDINGS.filter((f) => f.inspection_run_id === selectedInspection.id) : [];
    if (filterType !== "ALL") {
      findings = findings.filter((f) => f.finding_type === filterType);
    }
    if (filterSeverity !== "ALL") {
      findings = findings.filter((f) => f.severity === filterSeverity);
    }
    return findings;
  }, [selectedInspection, filterType, filterSeverity]);

  const riskDistribution = useMemo(() => {
    const dist: Record<string, number> = { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 };
    inspections.forEach((i) => {
      if (dist[i.risk_band || "LOW"] !== undefined) dist[i.risk_band || "LOW"]++;
    });
    return dist;
  }, [inspections]);

  const totalFindings = useMemo(() => {
    return inspections.reduce((sum, i) => sum + i.findings_count, 0);
  }, [inspections]);

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  const riskColors = {
    LOW: "#22c55e",
    MODERATE: "#f59e0b",
    HIGH: "#f97316",
    CRITICAL: "#ef4444",
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-rg-primary" />
            Inspection Workspace
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            {useDemoData ? "Demonstration inspection data" : `${inspections.length} inspection run${inspections.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" disabled>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="p-5">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-8 w-8 rounded-lg skeleton" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-1/3 rounded skeleton" />
                      <div className="h-3 w-1/2 rounded skeleton" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardContent className="p-5">
              <div className="space-y-3">
                <div className="h-4 w-20 rounded skeleton" />
                <div className="space-y-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="h-2 w-16 rounded-full skeleton" />
                      <div className="h-3 w-12 rounded skeleton" />
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : inspections.length > 0 ? (
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Inspection list */}
          <div className="lg:col-span-2 space-y-4">
            {inspections.map((insp, idx) => (
              <Card
                key={insp.id}
                className={cn(
                  "transition-all duration-200 animate-fade-in cursor-pointer hover:shadow-md hover:border-rg-primary-light/50",
                  selectedInspection?.id === insp.id && "border-rg-primary ring-2 ring-rg-primary/20"
                )}
                style={{ animationDelay: `${idx * 50}ms` }}
                onClick={() => {
                  setSelectedInspection(insp);
                  setSelectedFindings(DEMO_FINDINGS.filter((f) => f.inspection_run_id === insp.id));
                }}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <div className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                      getRiskColor(insp.risk_band)
                    )}>
                      <FileSearch className="h-5 w-5 text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-semibold text-rg-text truncate">
                          {insp.inspection_type.replace(/_/g, " ")}
                        </h3>
                        <Badge variant="outline" className={cn(getStatusColor(insp.status), "text-[10px]")}>
                          {insp.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-rg-text-muted mb-1.5">
                        {DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === insp.dataset_version_id))?.name || "Dataset"}
                        {" • "}
                        v{DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === insp.dataset_version_id))?.versions[0]?.version_number || "?"}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-rg-text-muted">
                        <span>{insp.findings_count} findings</span>
                        <span className="flex items-center gap-1">
                          <BarChart3 className="h-3 w-3" />
                          {insp.risk_score?.toFixed(1)} — {insp.risk_band}
                        </span>
                        <span>{formatDate(insp.completed_at)}</span>
                      </div>
                    </div>
                    {selectedInspection?.id === insp.id && (
                      <ChevronDown className="h-4 w-4 text-rg-text-muted shrink-0 mt-1" />
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Sidebar - Risk summary */}
          <div className="space-y-4">
            <Card>
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold text-rg-text mb-4 flex items-center gap-2">
                  <Shield className="h-4 w-4 text-rg-text-muted" />
                  Risk Breakdown
                </h3>
                <div className="space-y-3">
                  {Object.entries(riskDistribution).map(([band, count]) => {
                    const total = inspections.length || 1;
                    const pct = Math.round((count / total) * 100);
                    return (
                      <div key={band} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-rg-text-muted capitalize">{band}</span>
                          <span className="font-medium text-rg-text">{count} ({pct}%)</span>
                        </div>
                        <div className="h-2 bg-rg-surface-alt rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${pct}%`,
                              backgroundColor: riskColors[band],
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                  <div className="pt-3 border-t border-rg-border/50 flex items-center justify-between text-xs">
                    <span className="text-rg-text-muted">Total findings</span>
                    <span className="font-semibold text-rg-text">{totalFindings}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold text-rg-text mb-3 flex items-center gap-2">
                  <Clock className="h-4 w-4 text-rg-text-muted" />
                  Summary
                </h3>
                {selectedInspection && (
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-rg-text-muted">Risk Score</span>
                      <span className="font-semibold text-rg-text font-mono">{selectedInspection.risk_score?.toFixed(1)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-rg-text-muted">Risk Band</span>
                      <span className={cn("font-semibold capitalize", getRiskColor(selectedInspection.risk_band))}>
                        {selectedInspection.risk_band}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-rg-text-muted">Release Eligible</span>
                      <span className={cn(
                        "font-semibold",
                        selectedInspection.is_release_eligible ? "text-green-600" : "text-red-600"
                      )}>
                        {selectedInspection.is_release_eligible ? "Yes" : "No"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-rg-text-muted">Policy Version</span>
                      <span className="text-rg-text font-mono text-xs">{selectedInspection.policy_version || "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-rg-text-muted">Completed</span>
                      <span className="text-rg-text text-xs">{formatDate(selectedInspection.completed_at)}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Findings detail */}
          {selectedInspection && (
            <Card className="lg:col-span-3">
              <CardContent className="p-5">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-base font-semibold text-rg-text flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                      Findings — {selectedInspection.inspection_type.replace(/_/g, " ")}
                    </h3>
                    <p className="text-xs text-rg-text-muted">
                      {filteredFindings.length} of {DEMO_FINDINGS.filter((f) => f.inspection_run_id === selectedInspection.id).length} findings
                    </p>
                  </div>
                  {/* Filters */}
                  <div className="flex items-center gap-2">
                    <Select
                      options={[
                        { value: "ALL", label: "All Types" },
                        { value: "PII", label: "PII" },
                        { value: "QUALITY", label: "Quality" },
                        { value: "POLICY", label: "Policy" },
                      ]}
                      value={filterType}
                      onChange={(e) => setFilterType(e.target.value)}
                      className="w-32"
                    />
                    <Select
                      options={[
                        { value: "ALL", label: "All Severities" },
                        { value: "CRITICAL", label: "Critical" },
                        { value: "HIGH", label: "High" },
                        { value: "MEDIUM", label: "Medium" },
                        { value: "LOW", label: "Low" },
                      ]}
                      value={filterSeverity}
                      onChange={(e) => setFilterSeverity(e.target.value)}
                      className="w-36"
                    />
                  </div>
                </div>

                {filteredFindings.length > 0 ? (
                  <div className="space-y-2">
                    {filteredFindings.map((finding, idx) => (
                      <a
                        key={finding.id}
                        href={`/findings/${finding.id}`}
                        className={cn(
                          "flex items-start gap-3 p-3 rounded-lg border border-rg-border bg-white hover:border-rg-primary-light/50 hover:bg-rg-surface-alt/30 transition-all duration-150 animate-fade-in",
                          idx === 0 && "border-l-4 border-l-amber-500"
                        )}
                        style={{ animationDelay: `${idx * 30}ms` }}
                      >
                        <Badge className={cn(FINDING_TYPE_COLORS[finding.finding_type] || FINDING_TYPE_COLORS.PII, "text-[10px] shrink-0")}>
                          {finding.finding_type}
                        </Badge>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className={cn("text-sm font-medium capitalize", getSeverityColor(finding.severity).split(" ")[0].replace("text-", "text-"))}>
                              {finding.category}
                            </span>
                            <Badge variant="outline" className={cn(getSeverityColor(finding.severity), "text-[10px]")}>
                              {finding.severity}
                            </Badge>
                            {finding.column_name && (
                              <span className="text-xs text-rg-text-muted font-mono">
                                {finding.column_name}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-rg-text-muted mt-0.5">{finding.message}</p>
                          <div className="flex items-center gap-3 mt-1.5 text-xs text-rg-text-muted">
                            <span>{finding.occurrence_count} occurrence{finding.occurrence_count !== 1 ? "s" : ""}</span>
                            {finding.confidence_score && (
                              <span className="flex items-center gap-1">
                                <Shield className="h-3 w-3" />
                                {finding.confidence_score.toFixed(2)} confidence
                              </span>
                            )}
                            <span>{formatDate(finding.created_at)}</span>
                          </div>
                        </div>
                        <Eye className="h-4 w-4 text-rg-text-muted shrink-0" />
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                    <CheckCircle className="h-10 w-10 mb-3 text-green-500" />
                    <p className="text-sm font-medium text-green-600">No findings match the current filters</p>
                    <p className="text-xs mt-1">Try adjusting your filter criteria</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <FileSearch className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-semibold text-rg-text mb-1">No inspections yet</h3>
            <p className="text-sm text-rg-text-muted max-w-sm">
              Run an inspection on a dataset to view detailed findings, risk scores, and policy compliance.
            </p>
            <Button variant="secondary" className="mt-4" asChild>
              <a href="/datasets">Browse datasets</a>
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

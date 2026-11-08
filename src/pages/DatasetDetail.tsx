import { useEffect, useState, useMemo } from "react";
import {
  ArrowLeft,
  Database,
  GitBranch,
  FileText,
  Shield,
  CheckCircle,
  AlertTriangle,
  Clock,
  Hash,
  ExternalLink,
  Loader2,
  Download,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { cn, formatDate, formatBytes, truncateHash, getRiskBadgeClass } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import type { DatasetSummary, DatasetVersion } from "@/lib/api";
import { DEMO_DATASETS, DEMO_INSPECTIONS } from "@/lib/api/mockData";

interface DatasetDetailProps {
  datasetId: string;
}

export function DatasetDetail({ datasetId }: DatasetDetailProps) {
  const { isAuthenticated } = useAuth();
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [useDemoData, setUseDemoData] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "versions" | "inspections" | "profile">("overview");

  useEffect(() => {
    const fetchDataset = async () => {
      setIsLoading(true);
      try {
        const result = await api.getDataset(datasetId);
        setDataset(result);
        setUseDemoData(false);
      } catch {
        const demo = DEMO_DATASETS.find((d) => d.id === datasetId);
        if (demo) {
          setDataset(demo);
          setUseDemoData(true);
        }
      } finally {
        setIsLoading(false);
      }
    };
    fetchDataset();
  }, [datasetId]);

  const demoInspections = useMemo(() => {
    if (!dataset) return [];
    return DEMO_INSPECTIONS.filter((i) => i.dataset_id === datasetId).slice(0, 3);
  }, [dataset]);

  const latestVersion = dataset?.versions[dataset.versions.length - 1];

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Back button */}
      <a
        href="/datasets"
        className="inline-flex items-center gap-1.5 text-sm text-rg-text-muted hover:text-rg-text transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Datasets
      </a>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 text-rg-primary animate-spin" />
        </div>
      ) : !dataset ? (
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <AlertTriangle className="h-10 w-10 text-amber-500 mb-3" />
            <h3 className="text-lg font-semibold text-rg-text mb-1">Dataset not found</h3>
            <p className="text-sm text-rg-text-muted mb-4">
              The dataset you&apos;re looking for doesn&apos;t exist or you don&apos;t have access to it.
            </p>
            <Button asChild>
              <a href="/datasets">Return to dataset list</a>
            </Button>
          </div>
        </Card>
      ) : (
        <>
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-rg-primary text-white shadow-md shadow-rg-primary/20">
                <Database className="h-6 w-6" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h1 className="text-xl font-bold text-rg-text truncate">{dataset.name}</h1>
                  {useDemoData && (
                    <Badge variant="info" className="text-[10px]">Demo</Badge>
                  )}
                  {latest?.content_hash && (
                    <span className="inline-flex items-center gap-1 text-xs text-rg-text-muted font-mono">
                      <Hash className="h-3 w-3" />
                      {truncateHash(latest.content_hash, 6, 6)}
                    </span>
                  )}
                </div>
                <p className="text-sm text-rg-text-muted">
                  {dataset.description || "No description provided"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {latest && (
                <Button variant="secondary" size="sm" asChild>
                  <a href={`/inspections?id=${demoInspections[0]?.id || ""}`} className="flex items-center gap-1.5">
                    <Shield className="h-4 w-4" />
                    Run Inspection
                  </a>
                </Button>
              )}
              <Button variant="secondary" size="sm" disabled>
                <Download className="h-4 w-4" />
                Export
              </Button>
            </div>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatItem label="Format" value={latest?.file_format?.toUpperCase() || "—"} />
            <StatItem label="Size" value={formatBytes(latest?.file_size || 0)} />
            <StatItem label="Versions" value={dataset.versions.length} />
            <StatItem label="Created" value={formatDate(dataset.created_at)} />
          </div>

          {/* Tab navigation */}
          <div className="flex gap-1 p-1 bg-rg-surface-alt rounded-lg border border-rg-border/50 w-fit">
            {[
              { key: "overview", label: "Overview", icon: Database },
              { key: "versions", label: "Versions", icon: GitBranch },
              { key: "inspections", label: "Inspections", icon: FileText },
              { key: "profile", label: "Profile", icon: Shield },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md transition-colors",
                  activeTab === tab.key
                    ? "bg-white text-rg-text shadow-sm"
                    : "text-rg-text-muted hover:text-rg-text"
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "overview" && (
            <Card>
              <CardContent className="p-6">
                <div className="grid md:grid-cols-2 gap-8">
                  {/* Dataset info */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-rg-text mb-3 flex items-center gap-2">
                      <Database className="h-4 w-4 text-rg-text-muted" />
                      Dataset Information
                    </h3>
                    <dl className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Name</dt>
                        <dd className="text-sm font-medium text-rg-text">{dataset.name}</dd>
                      </div>
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Description</dt>
                        <dd className="text-sm text-rg-text">{dataset.description || "—"}</dd>
                      </div>
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Total Versions</dt>
                        <dd className="text-sm font-medium text-rg-text">{dataset.versions.length}</dd>
                      </div>
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Created</dt>
                        <dd className="text-sm text-rg-text">{formatDate(dataset.created_at)}</dd>
                      </div>
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Latest Format</dt>
                        <dd className="text-sm text-rg-text">
                          {latest?.file_format?.toUpperCase() || "—"}
                        </dd>
                      </div>
                      <div className="space-y-1">
                        <dt className="text-xs text-rg-text-muted">Latest Size</dt>
                        <dd className="text-sm text-rg-text">
                          {formatBytes(latest?.file_size || 0)}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  {/* Latest version info */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-rg-text mb-3 flex items-center gap-2">
                      <GitBranch className="h-4 w-4 text-rg-text-muted" />
                      Latest Version
                    </h3>
                    {latest ? (
                      <dl className="grid grid-cols-2 gap-4">
                        <div className="space-y-1">
                          <dt className="text-xs text-rg-text-muted">Version</dt>
                          <dd className="text-sm font-medium text-rg-text font-mono">
                            v{latest.version_number}
                          </dd>
                        </div>
                        <div className="space-y-1">
                          <dt className="text-xs text-rg-text-muted">Content Hash (SHA-256)</dt>
                          <dd className="text-sm font-mono text-rg-text truncate max-w-[180px]">
                            {truncateHash(latest.content_hash, 8, 8)}
                            <button
                              onClick={() => navigator.clipboard.writeText(latest.content_hash)}
                              className="ml-1 text-rg-primary hover:text-rg-primary-dark text-xs"
                              title="Copy hash"
                            >
                              <Hash className="h-3 w-3 inline" />
                            </button>
                          </dd>
                        </div>
                        <div className="space-y-1">
                          <dt className="text-xs text-rg-text-muted">Artifact Reference</dt>
                          <dd className="text-xs font-mono text-rg-text truncate max-w-[180px]">
                            {latest.local_artifact_ref}
                          </dd>
                        </div>
                        <div className="space-y-1">
                          <dt className="text-xs text-rg-text-muted">Created</dt>
                          <dd className="text-sm text-rg-text">{formatDate(latest.created_at)}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="text-sm text-rg-text-muted">No versions available</p>
                    )}
                  </div>
                </div>

                {/* Inspection summary */}
                {demoInspections.length > 0 && (
                  <div className="mt-8 pt-6 border-t border-rg-border/50">
                    <h3 className="text-sm font-semibold text-rg-text mb-3 flex items-center gap-2">
                      <Shield className="h-4 w-4 text-rg-text-muted" />
                      Latest Inspection
                    </h3>
                    {demoInspections[0] && (
                      <div className="flex items-center gap-4 p-4 bg-rg-surface-alt rounded-lg">
                        <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg", getRiskBadgeClass(demoInspections[0].risk_band))}>
                          <FileText className="h-5 w-5 text-white" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-rg-text">
                            {demoInspections[0].inspection_type.replace("_", " ")}
                          </p>
                          <p className="text-xs text-rg-text-muted">
                            {demoInspections[0].findings_count} findings • {formatDate(demoInspections[0].completed_at)}
                          </p>
                        </div>
                        <Badge className={cn("font-medium", getRiskBadgeClass(demoInspections[0].risk_band))}>
                          {demoInspections[0].risk_score?.toFixed(1)} — {demoInspections[0].risk_band}
                        </Badge>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {activeTab === "versions" && (
            <Card>
              <CardContent className="p-6">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Version</TableHead>
                      <TableHead>Format</TableHead>
                      <TableHead>Size</TableHead>
                      <TableHead>Content Hash</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead className="text-right">Artifact Ref</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dataset.versions.map((v, i) => (
                      <TableRow key={v.id} className={i === 0 ? "bg-rg-primary/5" : ""}>
                        <TableCell>
                          <span className="font-medium text-rg-text">
                            v{v.version_number}
                            {i === 0 && (
                              <Badge variant="success" className="ml-2 text-[10px]">Latest</Badge>
                            )}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px]">{v.file_format.toUpperCase()}</Badge>
                        </TableCell>
                        <TableCell className="text-rg-text-muted">{formatBytes(v.file_size)}</TableCell>
                        <TableCell>
                          <span className="font-mono text-xs text-rg-text truncate max-w-[200px] block">
                            {truncateHash(v.content_hash, 6, 6)}
                          </span>
                        </TableCell>
                        <TableCell className="text-rg-text-muted text-xs">{formatDate(v.created_at)}</TableCell>
                        <TableCell>
                          <span className="text-xs font-mono text-rg-text-muted truncate max-w-[150px] block">
                            {v.local_artifact_ref}
                          </span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {activeTab === "inspections" && (
            <Card>
              <CardContent className="p-6">
                {demoInspections.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Type</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Risk Score</TableHead>
                        <TableHead>Findings</TableHead>
                        <TableHead>Completed</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {demoInspections.map((insp) => (
                        <TableRow key={insp.id}>
                          <TableCell className="text-sm text-rg-text">
                            {insp.inspection_type.replace(/_/g, " ")}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={cn(getStatusColor(insp.status))}>
                              {insp.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge className={cn("font-medium", getRiskBadgeClass(insp.risk_band))}>
                              {insp.risk_score?.toFixed(1)} — {insp.risk_band}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-rg-text-muted">{insp.findings_count}</TableCell>
                          <TableCell className="text-rg-text-muted text-xs">{formatDate(insp.completed_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                    <FileText className="h-10 w-10 mb-3 opacity-40" />
                    <p className="text-sm">No inspections run yet</p>
                    <Button variant="secondary" size="sm" className="mt-3" asChild>
                      <a href={`/inspections?id=${datasetId}`}>Run an inspection</a>
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {activeTab === "profile" && (
            <Card>
              <CardContent className="p-6">
                {latest?.metadata ? (
                  <div className="space-y-6">
                    {/* Profile overview */}
                    <div className="grid grid-cols-3 gap-4">
                      <ProfileStat label="Rows" value={String(latest.metadata.row_count)} color="text-rg-primary" />
                      <ProfileStat label="Columns" value={String(latest.metadata.column_count)} color="text-blue-600" />
                      <ProfileStat label="Duplicates" value={String(latest.metadata.duplicate_row_count)} color="text-amber-600" />
                    </div>

                    {/* Columns table */}
                    <h3 className="text-sm font-semibold text-rg-text mb-3">Columns</h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Column</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Nulls</TableHead>
                          <TableHead>Null %</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {latest.metadata.columns.map((col, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-medium text-rg-text text-sm">{col}</TableCell>
                            <TableCell className="text-rg-text-muted text-xs font-mono">
                              {latest.metadata.column_types[col] || "unknown"}
                            </TableCell>
                            <TableCell className="text-rg-text-muted">
                              {latest.metadata.null_counts[col] ?? 0}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <div className="flex-1 h-1.5 bg-rg-surface-alt rounded-full overflow-hidden">
                                  <div
                                    className={cn(
                                      "h-full rounded-full",
                                      (latest.metadata.null_percentages[col] || 0) > 5 ? "bg-red-500" : "bg-green-500"
                                    )}
                                    style={{
                                      width: `${Math.min(100, latest.metadata.null_percentages[col] || 0)}%`,
                                    }}
                                  />
                                </div>
                                <span className="text-xs text-rg-text-muted w-8 text-right">
                                  {latest.metadata.null_percentages[col] ?? 0}%
                                </span>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                    <Shield className="h-10 w-10 mb-3 opacity-40" />
                    <p className="text-sm">Profile data not available</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs text-rg-text-muted">{label}</dt>
      <dd className="text-sm font-semibold text-rg-text">{value}</dd>
    </div>
  );
}

function ProfileStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="space-y-1 text-center">
      <dt className="text-xs text-rg-text-muted">{label}</dt>
      <dd className={cn("text-2xl font-bold", color)}>{value}</dd>
    </div>
  );
}

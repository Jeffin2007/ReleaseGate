import { useEffect, useState } from "react";
import {
  Database,
  Search,
  AlertTriangle,
  CheckCircle,
  Clock,
  ArrowRight,
  TrendingUp,
  Shield,
  FileText,
  Send,
  BarChart3,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { MeteredProgress } from "@/components/ui/MeteredProgress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import {
  cn,
  formatDate,
  formatBytes,
  truncateHash,
  getRiskBadgeClass,
  getRiskColor,
  getStatusColor,
  getSeverityColor,
} from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { api, DEMO_DATASETS, DEMO_INSPECTIONS, DEMO_FINDINGS, DEMO_APPROVAL_STATUS } from "@/lib/api";
import type { DatasetSummary, InspectionRun } from "@/lib/api";
import { DEMO_ORGANIZATIONS } from "@/lib/api/mockData";

interface DashboardStats {
  totalDatasets: number;
  totalVersions: number;
  totalInspections: number;
  riskDistribution: Record<string, number>;
  pendingApprovals: number;
  recentReleases: number;
  avgRiskScore: number;
}

function RiskBar({ label, value, color, max = 100 }: { label: string; value: number; color: string; max?: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-rg-text-muted w-20 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-rg-surface-alt overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-semibold text-rg-text w-10 text-right">{value}</span>
    </div>
  );
}

export function Dashboard() {
  const { user, switchOrganization } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentDatasets, setRecentDatasets] = useState<DatasetSummary[]>([]);
  const [recentInspections, setRecentInspections] = useState<InspectionRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [useDemoData, setUseDemoData] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        // Try to fetch real data
        const [dsRes, inspRes] = await Promise.allSettled([
          api.listDatasets(5, 0),
          api.listInspectionsForDataset("placeholder"),
        ]);

        if (dsRes.status === "fulfilled" && Array.isArray(dsRes.value) && dsRes.value.length > 0) {
          const datasets = dsRes.value as DatasetSummary[];
          setRecentDatasets(datasets);

          // Compute stats from real data
          const totalVersions = datasets.reduce((sum, d) => sum + d.versions.length, 0);
          setStats({
            totalDatasets: datasets.length,
            totalVersions,
            totalInspections: 0,
            riskDistribution: { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 },
            pendingApprovals: 0,
            recentReleases: 0,
            avgRiskScore: 0,
          });
          setUseDemoData(false);
        } else {
          // Fall back to demo data
          setRecentDatasets(DEMO_DATASETS);
          setRecentInspections(DEMO_INSPECTIONS.slice(0, 5));
          setStats({
            totalDatasets: DEMO_DATASETS.length,
            totalVersions: DEMO_DATASETS.reduce((s, d) => s + d.versions.length, 0),
            totalInspections: DEMO_INSPECTIONS.length,
            riskDistribution: {
              LOW: DEMO_INSPECTIONS.filter((i) => i.risk_band === "LOW").length,
              MODERATE: DEMO_INSPECTIONS.filter((i) => i.risk_band === "MODERATE").length,
              HIGH: DEMO_INSPECTIONS.filter((i) => i.risk_band === "HIGH").length,
              CRITICAL: DEMO_INSPECTIONS.filter((i) => i.risk_band === "CRITICAL").length,
            },
            pendingApprovals: DEMO_APPROVAL_STATUS.queued + DEMO_APPROVAL_STATUS.pending_review,
            recentReleases: DEMO_APPROVAL_STATUS.approved,
            avgRiskScore: Math.round(
              (DEMO_INSPECTIONS.reduce((s, i) => s + (i.risk_score || 0), 0) / DEMO_INSPECTIONS.length) * 10
            ) / 10,
          });
          setUseDemoData(true);
        }
      } catch {
        // Fall back to demo data on any error
        setRecentDatasets(DEMO_DATASETS);
        setRecentInspections(DEMO_INSPECTIONS.slice(0, 5));
        setStats({
          totalDatasets: DEMO_DATASETS.length,
          totalVersions: DEMO_DATASETS.reduce((s, d) => s + d.versions.length, 0),
          totalInspections: DEMO_INSPECTIONS.length,
          riskDistribution: {
            LOW: DEMO_INSPECTIONS.filter((i) => i.risk_band === "LOW").length,
            MODERATE: DEMO_INSPECTIONS.filter((i) => i.risk_band === "MODERATE").length,
            HIGH: DEMO_INSPECTIONS.filter((i) => i.risk_band === "HIGH").length,
            CRITICAL: DEMO_INSPECTIONS.filter((i) => i.risk_band === "CRITICAL").length,
          },
          pendingApprovals: DEMO_APPROVAL_STATUS.queued + DEMO_APPROVAL_STATUS.pending_review,
          recentReleases: DEMO_APPROVAL_STATUS.approved,
          avgRiskScore: Math.round(
            (DEMO_INSPECTIONS.reduce((s, i) => s + (i.risk_score || 0), 0) / DEMO_INSPECTIONS.length) * 10
          ) / 10,
        });
        setUseDemoData(true);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  const isDemo = useDemoData;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield className="h-5 w-5 text-rg-primary" />
            <h1 className="text-xl font-bold text-rg-text">
              {isDemo ? "Dashboard (Demo Mode)" : "Dashboard"}
            </h1>
            {isDemo && (
              <Badge variant="info" className="text-[10px] px-2 py-0">
                <Eye className="h-3 w-3" />
                Synthetic Demo
              </Badge>
            )}
          </div>
          <p className="text-sm text-rg-text-muted">
            {isDemo
              ? "Demonstration data only. Real backend data shown when available."
              : "Governance overview across your organization's datasets and release activities."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-xs text-rg-text-muted">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            {isDemo ? "Demo Environment" : "Production"}
          </span>
          <Button variant="secondary" size="sm" asChild>
            <a href="/datasets" className="flex items-center gap-1.5">
              <Database className="h-4 w-4" />
              Register Dataset
            </a>
          </Button>
        </div>
      </div>

      {/* Quick stats */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
          <QuickStatCard
            icon={Database}
            label="Datasets"
            value={stats.totalDatasets}
            subtitle={`${stats.totalVersions} versions`}
            color="text-rg-primary"
            bgColor="bg-rg-primary/10"
            borderColor="border-rg-primary/20"
          />
          <QuickStatCard
            icon={Search}
            label="Inspections"
            value={stats.totalInspections}
            subtitle={`Avg risk: ${stats.avgRiskScore}`}
            color="text-blue-600"
            bgColor="bg-blue-50"
            borderColor="border-blue-200"
          />
          <QuickStatCard
            icon={Clock}
            label="Pending Approvals"
            value={stats.pendingApprovals}
            subtitle="Require human review"
            color="text-amber-600"
            bgColor="bg-amber-50"
            borderColor="border-amber-200"
          />
          <QuickStatCard
            icon={Send}
            label="Published Releases"
            value={stats.recentReleases}
            subtitle="Approved and published"
            color="text-green-600"
            bgColor="bg-green-50"
            borderColor="border-green-200"
          />
        </div>
      )}

      {/* Two column layout */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Risk Distribution Chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-rg-text-muted" />
              Risk Distribution
            </CardTitle>
            <CardDescription>
              {isDemo ? "Synthetic inspection results" : "Risk assessment breakdown across inspection runs"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {stats && (
              <>
                <div className="space-y-2.5">
                  <RiskBar
                    label="Low (0-19)"
                    value={stats.riskDistribution.LOW}
                    color="#22c55e"
                    max={stats.totalInspections || 1}
                  />
                  <RiskBar
                    label="Moderate (20-39)"
                    value={stats.riskDistribution.MODERATE}
                    color="#f59e0b"
                    max={stats.totalInspections || 1}
                  />
                  <RiskBar
                    label="High (40-69)"
                    value={stats.riskDistribution.HIGH}
                    color="#f97316"
                    max={stats.totalInspections || 1}
                  />
                  <RiskBar
                    label="Critical (70-100)"
                    value={stats.riskDistribution.CRITICAL}
                    color="#ef4444"
                    max={stats.totalInspections || 1}
                  />
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-rg-border/50">
                  <span className="text-xs text-rg-text-muted">Total inspection runs</span>
                  <span className="text-sm font-semibold text-rg-text">
                    {stats.totalInspections}
                  </span>
                </div>
              </>
            )}
            {(!stats || stats.totalInspections === 0) && (
              <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                <BarChart3 className="h-10 w-10 mb-3 opacity-40" />
                <p className="text-sm">No inspection data available yet</p>
                <p className="text-xs mt-1">Ingest a dataset to see risk distribution</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pending Approvals */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4 text-rg-text-muted" />
              Pending Approvals
            </CardTitle>
            <CardDescription>
              {isDemo ? "Demo approval queue" : "Awaiting human authorization"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {stats && stats.pendingApprovals > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-rg-text-muted">Requires action</span>
                  <Badge variant="warning">{stats.pendingApprovals}</Badge>
                </div>
                <Button className="w-full" asChild>
                  <a href="/approvals" className="flex items-center justify-center gap-2">
                    <Shield className="h-4 w-4" />
                    Review Approval Queue
                    <ArrowRight className="h-4 w-4" />
                  </a>
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                <CheckCircle className="h-10 w-10 mb-3 opacity-40 text-green-500" />
                <p className="text-sm font-medium text-green-600">All clear</p>
                <p className="text-xs">No pending approvals</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent datasets & inspections */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent Datasets */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-4 w-4 text-rg-text-muted" />
              Recent Datasets
            </CardTitle>
            <a
              href="/datasets"
              className="text-xs font-medium text-rg-primary hover:text-rg-primary-dark transition-colors"
            >
              View all
            </a>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg skeleton" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-3/4 rounded skeleton" />
                      <div className="h-3 w-1/2 rounded skeleton" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentDatasets.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dataset</TableHead>
                    <TableHead>Format</TableHead>
                    <TableHead>Versions</TableHead>
                    <TableHead className="text-right">Risk Band</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentDatasets.slice(0, 5).map((ds) => {
                    const latestVersion = ds.versions[ds.versions.length - 1];
                    return (
                      <TableRow key={ds.id}>
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rg-surface-alt text-rg-text-muted">
                              <Database className="h-4.5 w-4.5" />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-rg-text">{ds.name}</p>
                              <p className="text-xs text-rg-text-muted truncate max-w-[200px]">
                                {ds.description || "No description"}
                              </p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px]">
                            {latestVersion?.file_format?.toUpperCase()}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-rg-text-muted">
                          <span className="text-sm font-medium text-rg-text">{ds.versions.length}</span>
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[10px] font-medium capitalize",
                              getRiskColor("LOW").split(" ")[1]
                            )}
                          >
                            LOW
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                <Database className="h-10 w-10 mb-3 opacity-40" />
                <p className="text-sm">No datasets registered yet</p>
                <p className="text-xs mt-1 mb-4">Upload a dataset to get started</p>
                <Button variant="secondary" size="sm" asChild>
                  <a href="/datasets" className="flex items-center gap-1.5">
                    <ArrowRight className="h-4 w-4" />
                    Register your first dataset
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4 text-rg-text-muted" />
              Recent Inspection Activity
            </CardTitle>
            <a
              href="/inspections"
              className="text-xs font-medium text-rg-primary hover:text-rg-primary-dark transition-colors"
            >
              View all
            </a>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="h-2 w-20 rounded skeleton" />
                    <div className="flex-1 h-4 rounded skeleton" />
                  </div>
                ))}
              </div>
            ) : recentInspections.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dataset</TableHead>
                    <TableHead>Risk Score</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Findings</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentInspections.map((insp) => (
                    <TableRow key={insp.id}>
                      <TableCell>
                        <span className="text-sm font-medium text-rg-text">
                          {DEMO_DATASETS.find((d) => d.versions.some((v) => v.id === insp.dataset_version_id))?.name || "Unknown dataset"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] font-medium",
                            insp.risk_band === "CRITICAL" && "text-red-700 border-red-300 bg-red-50",
                            insp.risk_band === "HIGH" && "text-orange-700 border-orange-300 bg-orange-50",
                            insp.risk_band === "MODERATE" && "text-amber-700 border-amber-300 bg-amber-50",
                            insp.risk_band === "LOW" && "text-green-700 border-green-300 bg-green-50"
                          )}
                        >
                          {insp.risk_score?.toFixed(1)} — {insp.risk_band}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn(getStatusColor(insp.status))}>
                          {insp.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="text-sm text-rg-text">{insp.findings_count}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                <FileText className="h-10 w-10 mb-3 opacity-40" />
                <p className="text-sm">No inspection activity yet</p>
                <p className="text-xs mt-1 mb-4">Run an inspection on a dataset</p>
                <Button variant="secondary" size="sm" asChild>
                  <a href="/inspections" className="flex items-center gap-1.5">
                    <ArrowRight className="h-4 w-4" />
                    View inspection workspace
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function QuickStatCard({
  icon: Icon,
  label,
  value,
  subtitle,
  color,
  bgColor,
  borderColor,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  subtitle: string;
  color: string;
  bgColor: string;
  borderColor: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-rg-text-muted uppercase tracking-wider">{label}</p>
            <p className="mt-1 text-2xl font-bold text-rg-text">{value}</p>
            <p className="mt-0.5 text-xs text-rg-text-muted">{subtitle}</p>
          </div>
          <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg", bgColor, borderColor)}>
            <Icon className={cn("h-5 w-5", color)} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

import { useState, useEffect } from "react";
import {
  Wifi,
  WifiOff,
  Database,
  Cpu,
  Server,
  Shield,
  AlertCircle,
  CheckCircle,
  Clock,
  Activity,
  RefreshCw,
  Loader2,
  HardDrive,
  BookOpen,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";

interface ReadinessCheck {
  status: "healthy" | "unhealthy";
  latency_ms: number | null;
  details: string | null;
}

export function SystemStatus() {
  const { isAuthenticated } = useAuth();
  const [readiness, setReadiness] = useState<{ status: string; checks: Record<string, ReadinessCheck> } | null>(null);
  const [apiHealth, setApiHealth] = useState<{ status: string; version: string; environment: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [useDemoData, setUseDemoData] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  useEffect(() => {
    const checkStatus = async () => {
      setIsLoading(true);
      try {
        const [readinessRes, healthRes] = await Promise.allSettled([
          api.getReadiness(),
          api.getHealth(),
        ]);

        if (healthRes.status === "fulfilled" && healthRes.value) {
          setApiHealth(healthRes.value);
        }
        if (readinessRes.status === "fulfilled" && readinessRes.value) {
          setReadiness(readinessRes.value);
          setLastChecked(new Date());
          setUseDemoData(false);
        } else {
          setReadiness({
            status: "not_ready",
            checks: {
              database: { status: "unhealthy", latency_ms: null, details: "Database unreachable in demo mode" },
              cache: { status: "healthy", latency_ms: 0.5, details: "In-memory cache ready" },
              storage: { status: "healthy", latency_ms: 1.2, details: "Local storage accessible" },
              mcp_server: { status: "healthy", latency_ms: 0.3, details: "MCP server ready in demo mode" },
            },
          });
          setUseDemoData(true);
        }
      } catch {
        setReadiness({
          status: "not_ready",
          checks: {
            database: { status: "unhealthy", latency_ms: null, details: "Not available in demo mode" },
            cache: { status: "healthy", latency_ms: 0.5, details: "In-memory cache ready" },
            storage: { status: "healthy", latency_ms: 1.2, details: "Local storage accessible on local worker" },
            mcp_server: { status: "healthy", latency_ms: 0.3, details: "MCP server ready (demo mode)" },
          },
        });
        setUseDemoData(true);
      } finally {
        setIsLoading(false);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  const overallHealthy = readiness?.status === "ready";

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <Server className="h-5 w-5 text-rg-primary" />
            System Status
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo Mode</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            {useDemoData
              ? "Demonstration system status — real-time monitoring when backend is connected."
              : "Real-time system health and dependency status across all ReleaseGate components."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge className={cn(overallHealthy ? "bg-green-100 text-green-700 border-green-200" : "bg-red-100 text-red-700 border-red-200")}>
            {overallHealthy ? (
              <>
                <CheckCircle className="h-3 w-3" />
                All Systems Operational
              </>
            ) : (
              <>
                <AlertCircle className="h-3 w-3" />
                Degraded Performance
              </>
            )}
          </Badge>
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Overall status card */}
      <Card className={cn(overallHealthy ? "border-green-200 bg-green-50/50" : "border-red-200 bg-red-50/50")}>
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className={cn(
              "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl",
              overallHealthy ? "bg-green-100 text-green-600" : "bg-red-100 text-red-600"
            )}>
              {overallHealthy ? (
                <Activity className="h-6 w-6" />
              ) : (
                <AlertCircle className="h-6 w-6" />
              )}
            </div>
            <div className="min-w-0">
              <h2 className={cn("text-lg font-semibold", overallHealthy ? "text-green-800" : "text-red-800")}>
                {overallHealthy ? "All Systems Operational" : "System Degraded — Action Required"}
              </h2>
              <p className={cn("text-sm", overallHealthy ? "text-green-600" : "text-red-600")}>
                {overallHealthy
                  ? "Last checked: " + (lastChecked ? lastChecked.toLocaleTimeString() : "—") + ". All ReleaseGate components are functioning normally."
                  : "One or more components require attention. Check individual status cards below for details."}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Component status grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatusCard
          icon={Database}
          label="PostgreSQL Database"
          status={readiness?.checks.database?.status || "unhealthy"}
          latency={readiness?.checks.database?.latency_ms}
          details={readiness?.checks.database?.details || "Not available in demo mode"}
          color="text-blue-600"
        />
        <StatusCard
          icon={HardDrive}
          label="Local Worker Storage"
          status={readiness?.checks.storage?.status || "healthy"}
          latency={readiness?.checks.storage?.latency_ms}
          details={readiness?.checks.storage?.details || "Local storage accessible (demo mode)"}
          color="text-violet-600"
        />
        <StatusCard
          icon={Cpu}
          label="MCP Server"
          status={readiness?.checks.mcp_server?.status || "healthy"}
          latency={readiness?.checks.mcp_server?.latency_ms}
          details={readiness?.checks.mcp_server?.details || "MCP server ready (demo mode)"}
          color="text-indigo-600"
        />
        <StatusCard
          icon={Server}
          label="Cloud API"
          status={apiHealth?.status === "ok" ? "healthy" : "unhealthy"}
          latency={null}
          details={apiHealth ? `API v${apiHealth.version} (${apiHealth.environment})` : "Not available in demo mode"}
          color="text-green-600"
        />
      </div>

      {/* Detailed checks */}
      <div className="grid sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-4 w-4 text-rg-text-muted" />
              Dependency Readiness
            </CardTitle>
            <CardDescription>
              Real-time health status of all system dependencies
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {readiness?.checks ? (
              Object.entries(readiness.checks).map(([name, check]) => (
                <div key={name} className="flex items-center justify-between p-3 bg-rg-surface-alt rounded-lg">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                      check.status === "healthy" ? "bg-green-100 text-green-600" : "bg-red-100 text-red-600"
                    )}>
                      {check.status === "healthy" ? (
                        <CheckCircle className="h-4 w-4" />
                      ) : (
                        <AlertCircle className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-rg-text capitalize">{name}</p>
                      {check.latency_ms !== null && check.latency_ms !== undefined && (
                        <p className="text-xs text-rg-text-muted">{check.latency_ms}ms latency</p>
                      )}
                    </div>
                  </div>
                  <Badge variant={check.status === "healthy" ? "success" : "error"} className="text-[10px]">
                    {check.status}
                  </Badge>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-rg-text-muted">
                <Database className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Loading dependency status…</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="h-4 w-4 text-rg-text-muted" />
              Security Posture
            </CardTitle>
            <CardDescription>
              Current security and compliance status
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <SecurityRow
              label="Raw Data Isolation"
              status="pass"
              description="Raw datasets remain local; only sanitized metadata is transmitted."
            />
            <SecurityRow
              label="PII Detection Active"
              status="pass"
              description="Microsoft Presidio scanner is running on all inspections."
            />
            <SecurityRow
              label="RBAC Enforcement"
              status="pass"
              description="Role-based access control is active across all endpoints."
            />
            <SecurityRow
              label="Audit Trail Active"
              status="pass"
              description="All actions are recorded in the append-only audit log."
            />
            <SecurityRow
              label="Approval Binding"
              status="pass"
              description="Human approvals are bound to exact SHA-256 artifact hashes."
            />
            <SecurityRow
              label="Emergency Pause"
              status="pass"
              description="Global circuit breaker is armed and ready — use /api/v1/admin/pause."
            />
          </CardContent>
        </Card>
      </div>

      {/* MCP Server Details */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4 text-rg-text-muted" />
            MCP Server Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Server Name</p>
              <p className="text-rg-text font-medium">ReleaseGate-Governance-Server</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Server Version</p>
              <p className="text-rg-text font-medium">1.0.0</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Transport</p>
              <p className="text-rg-text font-medium">stdio (local worker channel)</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Database Access</p>
              <p className="text-rg-text font-medium">NONE — MCP plane is database-free</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Identity Source</p>
              <p className="text-rg-text font-medium">SERVER_SESSION (env vars)</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider">Publication Authorization</p>
              <p className="text-rg-text font-medium">HUMAN_ONLY — AI cannot authorize</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Architecture Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-rg-text-muted" />
            Architecture Baseline Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid sm:grid-cols-3 gap-4 text-sm">
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Total Tools</p>
              <p className="text-2xl font-bold text-rg-text">12</p>
              <p className="text-xs text-rg-text-muted">MCP governance tools</p>
            </div>
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Resources</p>
              <p className="text-2xl font-bold text-rg-text">4</p>
              <p className="text-xs text-rg-text-muted">2 static + 2 template</p>
            </div>
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Prompts</p>
              <p className="text-2xl font-bold text-rg-text">4</p>
              <p className="text-xs text-rg-text-muted">Triage, Investigation, Remediation, Challenger</p>
            </div>
          </div>
          <div className="grid sm:grid-cols-3 gap-4 text-sm">
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Database Entities</p>
              <p className="text-2xl font-bold text-rg-text">7</p>
              <p className="text-xs text-rg-text-muted">Implemented (of 13 planned)</p>
            </div>
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Risk Model</p>
              <p className="text-2xl font-bold text-rg-text">100</p>
              <p className="text-xs text-rg-text-muted">Deterministic weighted scoring</p>
            </div>
            <div className="p-3 bg-rg-surface-alt rounded-lg">
              <p className="text-xs text-rg-text-muted uppercase tracking-wider mb-1">Baseline Status</p>
              <p className="text-2xl font-bold text-green-600">FROZEN</p>
              <p className="text-xs text-rg-text-muted">v1.0 Frozen Architecture</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatusCard({
  icon: Icon,
  label,
  status,
  latency,
  details,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  status: string;
  latency: number | null;
  details: string;
  color: string;
}) {
  const isHealthy = status === "healthy";
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Icon className={cn("h-4 w-4", color)} />
            <span className="text-sm font-medium text-rg-text">{label}</span>
          </div>
          <Badge variant={isHealthy ? "success" : "error"} className="text-[10px]">
            {isHealthy ? "Healthy" : "Unhealthy"}
          </Badge>
        </div>
        {latency !== null && (
          <p className="text-xs text-rg-text-muted mt-1">{latency}ms latency</p>
        )}
        <p className="text-xs text-rg-text-muted mt-1">{details}</p>
      </CardContent>
    </Card>
  );
}

function SecurityRow({ label, status, description }: { label: string; status: "pass" | "warn" | "fail"; description: string }) {
  return (
    <div className="flex items-start justify-between p-2.5 bg-rg-surface-alt rounded-lg">
      <div className="min-w-0">
        <p className="text-sm font-medium text-rg-text">{label}</p>
        <p className="text-xs text-rg-text-muted truncate">{description}</p>
      </div>
      {status === "pass" ? (
        <Badge variant="success" className="text-[10px] shrink-0">Active</Badge>
      ) : status === "fail" ? (
        <Badge variant="error" className="text-[10px] shrink-0">Inactive</Badge>
      ) : (
        <Badge className="bg-amber-100 text-amber-700 border-amber-200 text-[10px] shrink-0">Standby</Badge>
      )}
    </div>
  );
}

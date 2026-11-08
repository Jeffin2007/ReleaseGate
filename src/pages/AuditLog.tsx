import { useState, useMemo } from "react";
import {
  BarChart3,
  Search,
  Filter,
  ChevronDown,
  Clock,
  Shield,
  ChevronRight,
  Eye,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { cn, formatDate, truncateHash } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import type { AuditEvent } from "@/lib/audit";
import { getAuditActionColor } from "@/lib/audit";
import { DEMO_ORGANIZATIONS } from "@/lib/api/mockData";

// Synthetic audit events for demo
const DEMO_AUDIT_EVENTS: AuditEvent[] = [
  {
    id: "evt-001",
    organization_id: "org-acme",
    actor_id: "user-admin",
    actor_email: "admin@acme.gov",
    action: "USER_LOGIN",
    target_type: "user",
    target_id: "user-admin",
    outcome: "SUCCESS",
    details: { ip: "192.168.1.100", user_agent: "Mozilla/5.0" },
    created_at: "2026-11-08T08:00:00Z",
  },
  {
    id: "evt-002",
    organization_id: "org-acme",
    actor_id: "user-admin",
    actor_email: "admin@acme.gov",
    action: "DATASET_REGISTER",
    target_type: "dataset",
    target_id: "ds-clean-001",
    outcome: "SUCCESS",
    details: { dataset_name: "Quarterly Revenue Summary", version: 1 },
    created_at: "2026-11-08T08:15:00Z",
  },
  {
    id: "evt-003",
    organization_id: "org-acme",
    actor_id: "user-steward",
    actor_email: "steward@healthcare.ai",
    action: "INSPECTION_RUN",
    target_type: "inspection_run",
    target_id: "insp-001",
    outcome: "SUCCESS",
    details: { risk_score: 12.5, risk_band: "LOW", findings_count: 0 },
    created_at: "2026-11-08T08:30:00Z",
  },
  {
    id: "evt-004",
    organization_id: "org-health",
    actor_id: "user-steward",
    actor_email: "steward@healthcare.ai",
    action: "APPROVAL_APPROVE",
    target_type: "approval",
    target_id: "apr_abc123",
    outcome: "SUCCESS",
    details: { release_id: "rel_0123456789ab", artifact_hash: "d2a8f5c3...", approver: "Dr. Marcus Webb" },
    created_at: "2026-11-08T09:00:00Z",
  },
  {
    id: "evt-005",
    organization_id: "org-finance",
    actor_id: "user-auditor",
    actor_email: "auditor@finance.ai",
    action: "PUBLICATION_VERIFY",
    target_type: "publication",
    target_id: "pub-001",
    outcome: "SUCCESS",
    details: { integrity_verified: true, destination: "s3://release-evidence/exports", receipt_id: "receipt-abc123" },
    created_at: "2026-11-08T09:30:00Z",
  },
  {
    id: "evt-006",
    organization_id: "org-health",
    actor_id: "user-steward",
    actor_email: "steward@healthcare.ai",
    action: "RELEASE_WITHDRAW",
    target_type: "release",
    target_id: "rel_023456789abc",
    outcome: "SUCCESS",
    details: { reason: "Unresolved quality issues", withdrawn_by: "Dr. Marcus Webb" },
    created_at: "2026-11-08T10:00:00Z",
  },
  {
    id: "evt-007",
    organization_id: "org-acme",
    actor_id: "user-admin",
    actor_email: "admin@acme.gov",
    action: "USER_LOGIN",
    target_type: "user",
    target_id: "user-admin",
    outcome: "SUCCESS",
    details: { ip: "192.168.1.100", user_agent: "Mozilla/5.0" },
    created_at: "2026-11-08T10:30:00Z",
  },
  {
    id: "evt-008",
    organization_id: "org-finance",
    actor_id: "user-auditor",
    actor_email: "auditor@finance.ai",
    action: "APPROVAL_REJECT",
    target_type: "approval",
    target_id: "apr_def456",
    outcome: "SUCCESS",
    details: { release_id: "rel_023456789abc", reason: "Insufficient evidence for publication" },
    created_at: "2026-11-08T11:00:00Z",
  },
];

export function AuditLogPage() {
  const { isAuthenticated } = useAuth();
  const [events] = useState<AuditEvent[]>(DEMO_AUDIT_EVENTS);
  const [searchQuery, setSearchQuery] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [useDemoData, setUseDemoData] = useState(true);

  const filteredEvents = useMemo(() => {
    let result = events;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (e) =>
          e.action.toLowerCase().includes(q) ||
          e.actor_email.toLowerCase().includes(q) ||
          e.target_type.toLowerCase().includes(q) ||
          e.target_id.toLowerCase().includes(q) ||
          JSON.stringify(e.details).toLowerCase().includes(q)
      );
    }

    if (actionFilter) {
      result = result.filter((e) => e.action === actionFilter);
    }

    if (outcomeFilter) {
      result = result.filter((e) => e.outcome === outcomeFilter);
    }

    return result;
  }, [events, searchQuery, actionFilter, outcomeFilter]);

  const actionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    events.forEach((e) => {
      counts[e.action] = (counts[e.action] || 0) + 1;
    });
    return counts;
  }, [events]);

  const uniqueActions = useMemo(() => {
    const actions = [...new Set(events.map((e) => e.action))].sort();
    return actions;
  }, [events]);

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
            <BarChart3 className="h-5 w-5 text-rg-primary" />
            Audit Log
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            {useDemoData ? "Synthetic audit events for demonstration" : `${events.length} audit events recorded`}
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card className="overflow-hidden">
        <CardContent className="p-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <div className="flex-1 w-full">
            <Input
              placeholder="Search by action, actor, target, or details…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-rg-surface-alt border-rg-border/50"
            />
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Select
              options={[
                { value: "", label: "All Actions" },
                ...uniqueActions.map((a) => ({ value: a, label: a.replace(/_/g, " ") })),
              ]}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="w-full sm:w-40"
            />
            <Select
              options={[
                { value: "", label: "All Outcomes" },
                { value: "SUCCESS", label: "Success" },
                { value: "FAILURE", label: "Failure" },
              ]}
              value={outcomeFilter}
              onChange={(e) => setOutcomeFilter(e.target.value)}
              className="w-full sm:w-32"
            />
          </div>
        </CardContent>
      </Card>

      {/* Event list */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Event list */}
        <div className="lg:col-span-2 space-y-2">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-full skeleton" />
                      <div className="flex-1 space-y-1.5">
                        <div className="h-4 w-1/3 rounded skeleton" />
                        <div className="h-3 w-2/3 rounded skeleton" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : filteredEvents.length > 0 ? (
            <div className="space-y-2">
              {filteredEvents.map((event, idx) => (
                <Card
                  key={event.id}
                  className={cn(
                    "transition-all duration-150 cursor-pointer hover:shadow-md hover:border-rg-primary-light/50",
                    selectedEvent?.id === event.id && "border-rg-primary ring-2 ring-rg-primary/20"
                  )}
                  onClick={() => setSelectedEvent(event === selectedEvent ? null : event)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start gap-3">
                      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", getAuditActionColor(event.action))}>
                        {event.action.includes("LOGIN") ? (
                          <Shield className="h-4 w-4 text-white" />
                        ) : event.action.includes("REGISTER") ? (
                          <Clock className="h-4 w-4 text-white" />
                        ) : event.action.includes("INSPECTION") ? (
                          <BarChart3 className="h-4 w-4 text-white" />
                        ) : event.action.includes("APPROVE") ? (
                          <CheckCircle className="h-4 w-4 text-white" />
                        ) : event.action.includes("REJECT") ? (
                          <XCircle className="h-4 w-4 text-white" />
                        ) : event.action.includes("WITHDRAW") ? (
                          <XCircle className="h-4 w-4 text-white" />
                        ) : (
                          <Shield className="h-4 w-4 text-white" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <Badge className={cn(getAuditActionColor(event.action).split(" ")[1], "text-[10px] font-medium")}>
                            {event.action.replace(/_/g, " ")}
                          </Badge>
                          <Badge variant="outline" className={cn(
                            event.outcome === "SUCCESS" ? "bg-green-100 text-green-700 border-green-200" : "bg-red-100 text-red-700 border-red-200",
                            "text-[10px]"
                          )}>
                            {event.outcome}
                          </Badge>
                          <span className="text-xs text-rg-text-muted font-mono">{event.id}</span>
                        </div>
                        <p className="text-sm text-rg-text">
                          <span className="font-medium">{event.actor_email}</span>
                          {" "}
                          performed{" "}
                          <span className="font-medium text-rg-primary">{event.action.replace(/_/g, " ")}</span>
                          {" "}
                          on{" "}
                          <span className="font-medium text-rg-text">
                            {event.target_type}/{event.target_id.slice(0, 8)}
                          </span>
                        </p>
                        <p className="text-xs text-rg-text-muted mt-0.5">
                          {formatDate(event.created_at)}
                          {" • "}
                          Organization: {DEMO_ORGANIZATIONS.find((o) => o.id === event.organization_id)?.name || event.organization_id}
                        </p>
                      </div>
                      {selectedEvent?.id === event.id && (
                        <ChevronRight className="h-4 w-4 text-rg-text-muted shrink-0 mt-1" />
                      )}
                    </div>

                    {selectedEvent?.id === event.id && (
                      <div className="mt-3 pt-3 border-t border-rg-border/50 space-y-2">
                        <h4 className="text-xs font-semibold text-rg-text-muted uppercase tracking-wider">Details</h4>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div className="space-y-0.5">
                            <p className="text-rg-text-muted">Actor ID</p>
                            <p className="text-rg-text font-mono">{event.actor_id}</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="text-rg-text-muted">Actor Email</p>
                            <p className="text-rg-text">{event.actor_email}</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="text-rg-text-muted">Target Type</p>
                            <p className="text-rg-text capitalize">{event.target_type}</p>
                          </div>
                          <div className="space-y-0.5">
                            <p className="text-rg-text-muted">Target ID</p>
                            <p className="text-rg-text font-mono truncate">{event.target_id}</p>
                          </div>
                        </div>
                        {Object.entries(event.details).length > 0 && (
                          <div className="pt-2 border-t border-rg-border/50">
                            <p className="text-xs font-semibold text-rg-text-muted uppercase tracking-wider mb-1.5">Details</p>
                            <pre className="text-xs text-rg-text font-mono bg-rg-surface rounded p-2 overflow-x-auto border border-rg-border">
                              {JSON.stringify(event.details, null, 2)}
                            </pre>
                          </div>
                        )}
                        <div className="pt-2 border-t border-rg-border/50 flex items-center justify-between text-xs">
                          <span className="text-rg-text-muted">Timestamp (UTC)</span>
                          <span className="text-rg-text font-mono">{formatDate(event.created_at)}</span>
                        </div>
                        <div className="pt-1 flex justify-end">
                          <span className="text-xs text-rg-primary hover:text-rg-primary-dark transition-colors">
                            View full records <ChevronRight className="h-3 w-3 inline" />
                          </span>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <BarChart3 className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">No audit events found</h3>
                <p className="text-sm text-rg-text-muted">
                  {searchQuery ? `No events match "${searchQuery}". Try a different search.` : "Audit log is empty. Events will appear as actions are performed."}
                </p>
              </div>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-rg-text-muted" />
                Event Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm font-semibold text-rg-text mb-2">{events.length} Total Events</div>
              <div className="space-y-1.5">
                {Object.entries(actionCounts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([action, count]) => (
                    <div key={action} className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted truncate mr-2 max-w-[100px]">{action.replace(/_/g, " ")}</span>
                      <span className="text-rg-text font-medium w-6 text-right">{count}</span>
                    </div>
                  ))}
              </div>
              <div className="pt-3 border-t border-rg-border/50 space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-rg-text-muted">Success Rate</span>
                  <span className="text-rg-text font-medium">
                    {events.filter((e) => e.outcome === "SUCCESS").length}/{events.length} ({(events.filter((e) => e.outcome === "SUCCESS").length / events.length * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-rg-text-muted">Date Range</span>
                  <span className="text-rg-text">
                    {formatDate(events[events.length - 1]?.created_at)} — {formatDate(events[0]?.created_at)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {selectedEvent && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Eye className="h-4 w-4 text-rg-text-muted" />
                  Event Details
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="space-y-1.5 p-3 bg-rg-surface rounded-lg">
                  <p className="text-xs text-rg-text-muted mb-2">Event Payload</p>
                  <pre className="text-xs text-rg-text font-mono bg-rg-surface-alt rounded p-2 overflow-x-auto border border-rg-border">
                    {JSON.stringify(selectedEvent, null, 2)}
                  </pre>
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="h-4 w-4 text-rg-text-muted" />
                Audit Log Properties
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-rg-text-muted">
              <p>• Append-only event ledger — records cannot be modified or deleted.</p>
              <p>• Every event contains a unique event hash and timestamp.</p>
              <p>• Events are strictly scoped to the actor&apos;s organization.</p>
              <p>• Failed events are recorded with failure reason for forensic analysis.</p>
              <p className="pt-1">• Real-time event streaming available via WebSocket subscription.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

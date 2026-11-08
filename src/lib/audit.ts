// Placeholder for audit log types - to be expanded when backend endpoint exists
export interface AuditEvent {
  id: string;
  organization_id: string;
  actor_id: string;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: string;
  outcome: string;
  details: Record<string, any>;
  created_at: string;
}

export function getAuditActionColor(action: string): string {
  const actionUpper = action.toUpperCase();
  if (actionUpper.includes("LOGIN") || actionUpper.includes("AUTH")) return "bg-blue-100 text-blue-800";
  if (actionUpper.includes("INGEST") || actionUpper.includes("REGISTER")) return "bg-violet-100 text-violet-800";
  if (actionUpper.includes("INSPECT")) return "bg-cyan-100 text-cyan-800";
  if (actionUpper.includes("APPROVE")) return "bg-emerald-100 text-emerald-800";
  if (actionUpper.includes("PUBLISH")) return "bg-indigo-100 text-indigo-800";
  if (actionUpper.includes("WITHDRAW")) return "bg-rose-100 text-rose-800";
  if (actionUpper.includes("REJECT") || actionUpper.includes("BLOCK")) return "bg-red-100 text-red-800";
  return "bg-slate-100 text-slate-800";
}

import { type ClassValue, clsx } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function truncateHash(hash: string, start = 8, end = 8): string {
  if (!hash || hash.length < start + end + 3) return hash || "—";
  return `${hash.slice(0, start)}…${hash.slice(-end)}`;
}

export function getRiskColor(band: string | null | undefined): string {
  switch ((band || "").toUpperCase()) {
    case "CRITICAL":
      return "bg-red-100 text-red-800 border-red-200";
    case "HIGH":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "MODERATE":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "LOW":
      return "bg-green-100 text-green-800 border-green-200";
    default:
      return "bg-slate-100 text-slate-600 border-slate-200";
  }
}

export function getRiskBadgeClass(band: string | null | undefined): string {
  switch ((band || "").toUpperCase()) {
    case "CRITICAL":
      return "bg-red-600 text-white";
    case "HIGH":
      return "bg-orange-600 text-white";
    case "MODERATE":
      return "bg-amber-500 text-white";
    case "LOW":
      return "bg-green-600 text-white";
    default:
      return "bg-slate-400 text-white";
  }
}

export function getSeverityColor(severity: string | null | undefined): string {
  switch ((severity || "").toUpperCase()) {
    case "CRITICAL":
      return "text-red-700 bg-red-50 border-red-200";
    case "HIGH":
      return "text-orange-700 bg-orange-50 border-orange-200";
    case "MEDIUM":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "LOW":
      return "text-yellow-700 bg-yellow-50 border-yellow-200";
    case "INFORMATIONAL":
      return "text-blue-700 bg-blue-50 border-blue-200";
    default:
      return "text-slate-600 bg-slate-50 border-slate-200";
  }
}

export function getStatusColor(status: string | null | undefined): string {
  switch ((status || "").toUpperCase()) {
    case "COMPLETED":
      return "bg-green-100 text-green-800 border-green-200";
    case "PENDING":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "RUNNING":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "FAILED":
      return "bg-red-100 text-red-800 border-red-200";
    case "PUBLISHED":
      return "bg-emerald-100 text-emerald-800 border-emerald-200";
    case "STAGED":
      return "bg-violet-100 text-violet-800 border-violet-200";
    case "PENDING_REVIEW":
      return "bg-indigo-100 text-indigo-800 border-indigo-200";
    case "WITHDRAWN":
      return "bg-slate-100 text-slate-800 border-slate-200";
    default:
      return "bg-slate-100 text-slate-600 border-slate-200";
  }
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export const RISK_BANDS = ["LOW", "MODERATE", "HIGH", "CRITICAL"] as const;
export type RiskBand = (typeof RISK_BANDS)[number];

/**
 * ReleaseGate API Client
 * Type-safe, centralized HTTP client for the Cloud Control Plane API.
 */
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TIMEOUT_MS = 30000;

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = typeof window !== "undefined" ? localStorage.getItem("rg_token") : null;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const orgId = typeof window !== "undefined" ? localStorage.getItem("rg_org_id") : null;
  if (orgId) {
    headers["X-Organization-ID"] = orgId;
  }
  return headers;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  orgId?: string
): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
    ...(options.headers as Record<string, string> || {}),
  };
  if (orgId) {
    headers["X-Organization-ID"] = orgId;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (res.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("rg_token");
        localStorage.removeItem("rg_org_id");
        localStorage.removeItem("rg_user");
        window.location.href = "/login";
      }
      throw new ApiError("Unauthorized", 401);
    }

    if (res.status === 403) {
      throw new ApiError("Permission denied", 403);
    }

    if (res.status === 404) {
      throw new ApiError("Resource not found", 404);
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        (body as any).detail || `Request failed: ${res.status}`,
        res.status
      );
    }

    if (res.headers.get("content-type")?.includes("application/json")) {
      return (await res.json()) as T;
    }
    return (await res.text()) as any as T;
  } finally {
    clearTimeout(timer);
  }
}

// --- Types ---

export interface DatasetSummary {
  id: string;
  name: string;
  description: string | null;
  current_version_id: string | null;
  created_at: string;
  versions: Array<{
    id: string;
    version_number: number;
    content_hash: string;
    file_format: string;
    file_size: number;
    local_artifact_ref: string;
    created_at: string;
  }>;
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  content_hash: string;
  file_format: string;
  file_size: number;
  local_artifact_ref: string;
  metadata: {
    row_count: number;
    column_count: number;
    columns: string[];
    column_types: Record<string, string>;
    null_counts: Record<string, number>;
    null_percentages: Record<string, number>;
    duplicate_row_count: number;
    file_format: string;
  };
  created_at: string;
}

export interface InspectionRun {
  id: string;
  organization_id: string;
  dataset_id: string;
  dataset_version_id: string;
  inspection_type: string;
  status: string;
  risk_score: number | null;
  risk_band: string | null;
  policy_version: string | null;
  is_release_eligible: boolean | null;
  summary_report: Record<string, any>;
  started_at: string;
  completed_at: string | null;
  findings_count: number;
  findings: Finding[];
}

export interface Finding {
  id: string;
  organization_id: string;
  inspection_run_id: string;
  dataset_version_id: string;
  finding_type: string;
  category: string;
  column_name: string | null;
  severity: string;
  occurrence_count: number;
  confidence_score: number | null;
  message: string;
  evidence_ref: Record<string, any>;
  created_at: string;
}

export interface UserInfo {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

export interface SessionUser {
  user: UserInfo;
  organization_id: string;
  role: string;
}

// --- Error ---

export class ApiError extends Error {
  constructor(public message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

// --- API Methods ---

export const api = {
  // Auth
  async login(email: string, password: string): Promise<{ user: UserInfo; organization_id: string; role: string }> {
    return request("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async registerUser(data: { email: string; password: string; full_name?: string }): Promise<UserInfo> {
    return request("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async me(): Promise<UserInfo> {
    return request("/api/v1/auth/me");
  },

  async logout(): Promise<void> {
    if (typeof window !== "undefined") {
      localStorage.removeItem("rg_token");
      localStorage.removeItem("rg_org_id");
      localStorage.removeItem("rg_user");
    }
  },

  // Datasets
  async listDatasets(limit = 100, skip = 0): Promise<DatasetSummary[]> {
    return request(`/api/v1/datasets?limit=${limit}&skip=${skip}`);
  },

  async getDataset(id: string): Promise<DatasetSummary> {
    return request(`/api/v1/datasets/${id}`);
  },

  async getDatasetVersion(datasetId: string, versionNumber: number): Promise<DatasetVersion> {
    return request(`/api/v1/datasets/${datasetId}/versions/${versionNumber}`);
  },

  async registerMetadata(data: any): Promise<any> {
    return request("/api/v1/datasets/register-metadata", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  // Inspections
  async getInspectionRun(id: string): Promise<InspectionRun> {
    const orgId = localStorage.getItem("rg_org_id");
    const params = orgId ? `?organization_id=${orgId}` : "";
    return request(`/api/v1/inspections/${id}${params}`);
  },

  async listInspectionsForDataset(datasetId: string, versionId?: string): Promise<InspectionRun[]> {
    const orgId = localStorage.getItem("rg_org_id");
    const params = new URLSearchParams();
    if (orgId) params.set("organization_id", orgId);
    if (versionId) params.set("version_id", versionId);
    return request(`/api/v1/inspections/dataset/${datasetId}?${params}`);
  },

  async listFindingsForVersion(versionId: string, filters?: { severity?: string; finding_type?: string }): Promise<Finding[]> {
    const orgId = localStorage.getItem("rg_org_id");
    const params = new URLSearchParams();
    if (orgId) params.set("organization_id", orgId);
    if (filters?.severity) params.set("severity", filters.severity);
    if (filters?.finding_type) params.set("finding_type", filters.finding_type);
    return request(`/api/v1/inspections/versions/${versionId}/findings?${params}`);
  },

  // Health
  async getHealth(): Promise<any> {
    return request("/api/v1/health");
  },

  async getReadiness(): Promise<any> {
    return request("/ready");
  },
};

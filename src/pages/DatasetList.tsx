import { useEffect, useState, useMemo } from "react";
import {
  Database,
  Search,
  Plus,
  Filter,
  ChevronDown,
  MoreVertical,
  Eye,
  GitBranch,
  FileText,
  Upload,
  Loader2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { cn, formatDate, formatBytes, truncateHash, getRiskBadgeClass } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import type { DatasetSummary } from "@/lib/api";
import { DEMO_DATASETS, DEMO_ORGANIZATIONS } from "@/lib/api/mockData";

export function DatasetList() {
  const { isAuthenticated } = useAuth();
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [formatFilter, setFormatFilter] = useState("");
  const [sortBy, setSortBy] = useState("recent");
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [useDemoData, setUseDemoData] = useState(false);

  useEffect(() => {
    const fetchDatasets = async () => {
      setIsLoading(true);
      try {
        const result = await api.listDatasets(100, 0);
        if (Array.isArray(result) && result.length > 0) {
          setDatasets(result);
          setUseDemoData(false);
        } else {
          setDatasets(DEMO_DATASETS);
          setUseDemoData(true);
        }
      } catch {
        setDatasets(DEMO_DATASETS);
        setUseDemoData(true);
      } finally {
        setIsLoading(false);
      }
    };
    fetchDatasets();
  }, []);

  const filteredDatasets = useMemo(() => {
    let result = datasets;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (ds) =>
          ds.name.toLowerCase().includes(q) ||
          ds.description?.toLowerCase().includes(q)
      );
    }

    if (formatFilter) {
      result = result.filter((ds) => {
        const latest = ds.versions[ds.versions.length - 1];
        return latest?.file_format?.toLowerCase() === formatFilter.toLowerCase();
      });
    }

    if (selectedOrgId) {
      // Client-side filter by organization (simplified)
      result = result.filter((ds) => ds.organization_id === selectedOrgId);
    }

    switch (sortBy) {
      case "recent":
        result = [...result].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        break;
      case "name":
        result = [...result].sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "versionCount":
        result = [...result].sort((a, b) => b.versions.length - a.versions.length);
        break;
      case "riskLow":
        result = [...result].sort((a, b) => {
          const aRisk = a.versions[a.versions.length - 1]?.content_hash.length;
          const bRisk = b.versions[b.versions.length - 1]?.content_hash.length;
          return bRisk - aRisk;
        });
        break;
    }

    return result;
  }, [datasets, searchQuery, formatFilter, sortBy, selectedOrgId]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    try {
      const reader = new FileReader();
      reader.onprogress = (ev) => {
        if (ev.lengthComputable) {
          setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
        }
      };
      reader.onload = async () => {
        setUploadProgress(80);
        // In a real app, we'd send the file to the backend via the local worker channel
        // For demo, we simulate success
        await new Promise((r) => setTimeout(r, 2000));
        setUploadProgress(100);
        setUploading(false);
        // Refresh datasets after upload
        const result = await api.listDatasets(100, 0);
        if (Array.isArray(result) && result.length > 0) {
          setDatasets(result);
        }
      };
      reader.readAsArrayBuffer(file);
    } catch (err) {
      console.error("Upload failed:", err);
      setUploading(false);
    }
  };

  const formatFilters = [
    { value: "", label: "All formats" },
    { value: "csv", label: "CSV" },
    { value: "xlsx", label: "Excel" },
    { value: "json", label: "JSON" },
  ];

  const sortOptions = [
    { value: "recent", label: "Most Recent" },
    { value: "name", label: "Alphabetical" },
    { value: "versionCount", label: "Most Versions" },
  ];

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
            <Database className="h-5 w-5 text-rg-primary" />
            Datasets
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">
                Demo
              </Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            {useDemoData
              ? "Synthetic dataset catalog for demonstration"
              : ` ${datasets.length} dataset${datasets.length !== 1 ? "s" : ""} registered`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {uploading ? (
            <div className="flex items-center gap-3 px-4 py-2 bg-rg-surface-alt rounded-lg border border-rg-border">
              <div className="h-8 w-8 rounded-full border-2 border-rg-primary border-t-transparent animate-spin" />
              <div className="text-sm">
                <p className="text-rg-text font-medium">Uploading…</p>
                <p className="text-xs text-rg-text-muted">{uploadProgress}%</p>
              </div>
            </div>
          ) : (
            <label
              className="inline-flex items-center gap-2 px-4 py-2 bg-rg-primary text-white rounded-lg text-sm font-medium hover:bg-rg-primary-dark transition-colors cursor-pointer"
              onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".csv,.xlsx,.json";
                input.onchange = handleFileUpload;
                input.click();
              }}
            >
              <Upload className="h-4 w-4" />
              Register / Upload Dataset
            </label>
          )}
        </div>
      </div>

      {/* Filters */}
      <Card className="overflow-hidden">
        <CardContent className="p-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <div className="flex-1 w-full">
            <Input
              placeholder="Search datasets by name or description…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-rg-surface-alt border-rg-border/50"
            />
          </div>
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <Select
              options={formatFilters}
              value={formatFilter}
              onChange={(e) => setFormatFilter(e.target.value)}
              className="w-full sm:w-32"
            />
            <Select
              options={sortOptions}
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="w-full sm:w-32"
            />
            <Button variant="secondary" size="sm" onClick={() => {
              setSearchQuery("");
              setFormatFilter("");
              setSortBy("recent");
            }}>
              <Filter className="h-4 w-4" />
              Clear
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Dataset Grid */}
      {isLoading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="p-5">
              <div className="flex items-start gap-3 mb-4">
                <div className="h-10 w-10 rounded-lg skeleton" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 w-3/4 rounded skeleton" />
                  <div className="h-3 w-1/2 rounded skeleton" />
                </div>
              </div>
              <div className="space-y-2">
                <div className="h-3 w-full rounded skeleton" />
                <div className="h-3 w-2/3 rounded skeleton" />
                <div className="h-3 w-1/3 rounded skeleton" />
              </div>
            </Card>
          ))}
        </div>
      ) : filteredDatasets.length > 0 ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredDatasets.map((ds, index) => {
            const latest = ds.versions[ds.versions.length - 1];
            const org = DEMO_ORGANIZATIONS.find((o) => o.id === ds.organization_id);
            return (
              <Card
                key={ds.id}
                className="group hover:shadow-md hover:border-rg-primary-light/50 transition-all duration-200 animate-fade-in"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="p-5">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rg-primary/10 text-rg-primary">
                        <Database className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-rg-text group-hover:text-rg-primary transition-colors truncate max-w-[180px]">
                          {ds.name}
                        </h3>
                        <p className="text-xs text-rg-text-muted">
                          {ds.versions.length} version{ds.versions.length !== 1 ? "s" : ""}
                          {org ? `• ${org.name}` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <a
                        href={`/datasets/${ds.id}`}
                        className="p-1.5 rounded-md hover:bg-rg-surface-alt text-rg-text-muted hover:text-rg-text"
                        title="View details"
                      >
                        <Eye className="h-4 w-4" />
                      </a>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-rg-text-muted mb-3 line-clamp-2">
                    {ds.description || "No description provided"}
                  </p>

                  {/* Metadata */}
                  <div className="space-y-2 mb-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted">Latest version</span>
                      <span className="font-mono text-rg-text font-medium">vlatest</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted">Format</span>
                      <Badge variant="outline" className="text-[10px]">
                        {latest?.file_format?.toUpperCase()}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted">Size</span>
                      <span className="text-rg-text">{formatBytes(latest?.file_size || 0)}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted">SHA-256</span>
                      <span className="font-mono text-rg-text truncate max-w-[120px]">
                        {truncateHash(latest?.content_hash || "", 6, 4)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-rg-text-muted">Created</span>
                      <span className="text-rg-text">{formatDate(ds.created_at)}</span>
                    </div>
                  </div>

                  {/* Version list */}
                  {ds.versions.length > 1 && (
                    <div className="border-t border-rg-border/50 pt-3">
                      <p className="text-xs font-medium text-rg-text-muted mb-2">All Versions</p>
                      <div className="flex flex-wrap gap-1.5">
                        {ds.versions.map((v) => (
                          <button
                            key={v.id}
                            onClick={() => window.location.href = `/datasets/${ds.id}?version=${v.version_number}`}
                            className="inline-flex items-center px-2 py-1 rounded-md bg-rg-surface-alt text-xs text-rg-text-muted hover:bg-rg-primary-light hover:text-rg-primary transition-colors"
                          >
                            v{v.version_number}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Footer */}
                  <div className="mt-4 pt-3 border-t border-rg-border/50 flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs text-rg-text-muted">
                      <GitBranch className="h-3.5 w-3.5" />
                      <span>{ds.versions.length} versions</span>
                    </div>
                    <a
                      href={`/datasets/${ds.id}`}
                      className="text-xs font-medium text-rg-primary hover:text-rg-primary-dark transition-colors"
                    >
                      View details <span className="ml-1">→</span>
                    </a>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rg-surface-alt mb-4">
              <Database className="h-7 w-7 text-rg-text-muted" />
            </div>
            <h3 className="text-lg font-semibold text-rg-text mb-1">No datasets found</h3>
            <p className="text-sm text-rg-text-muted mb-6 max-w-sm">
              {searchQuery
                ? `No datasets match "${searchQuery}". Try a different search term.`
                : "Get started by registering or uploading your first dataset."}
            </p>
            {!searchQuery && (
              <label className="inline-flex items-center gap-2 px-5 py-2.5 bg-rg-primary text-white rounded-lg text-sm font-medium hover:bg-rg-primary-dark transition-colors cursor-pointer">
                <Upload className="h-4 w-4" />
                Upload a dataset
              </label>
            )}
          </div>
        </Card>
      )}

      {/* Hidden file input */}
      <input
        type="file"
        id="dataset-upload"
        accept=".csv,.xlsx,.json"
        className="hidden"
        onChange={handleFileUpload}
      />
    </div>
  );
}

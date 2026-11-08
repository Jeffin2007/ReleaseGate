import { useState, useMemo } from "react";
import {
  Send,
  CheckCircle,
  XCircle,
  Loader2,
  Hash,
  Shield,
  Clock,
  ExternalLink,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn, formatDate, truncateHash, getRiskBadgeClass, getStatusColor } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { DEMO_DATASETS, DEMO_INSPECTIONS } from "@/lib/api/mockData";

interface PublicationRecord {
  id: string;
  release_id: string;
  dataset_id: string;
  version_number: number;
  content_hash: string;
  destination_target: string;
  status: "STAGED" | "PUBLISHED" | "VERIFIED" | "FAILED" | "WITHDRAWN";
  published_hash: string | null;
  integrity_verified: boolean;
  receipt_id: string | null;
  idempotency_key: string;
  published_at: string | null;
  verified_at: string | null;
  attempts: number;
  is_idempotent: boolean;
}

const DEMO_PUBLICATIONS: PublicationRecord[] = [
  {
    id: "pub-001",
    release_id: "rel_0123456789ab",
    dataset_id: "ds-clean-001",
    version_number: 1,
    content_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    destination_target: "s3://release-evidence/exports",
    status: "VERIFIED",
    published_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    integrity_verified: true,
    receipt_id: "receipt-abc123",
    idempotency_key: "idem-001",
    published_at: "2026-10-15T10:30:00Z",
    verified_at: "2026-10-15T10:35:00Z",
    attempts: 1,
    is_idempotent: true,
  },
  {
    id: "pub-002",
    release_id: "rel_023456789abc",
    dataset_id: "ds-pii-002",
    version_number: 1,
    content_hash: "d2a8f5c3b91e7d4f2a6c8e3b5d9f1a4c7e2b8d3f6a0c5e9b2d8f4a1c7e3b5d9f",
    destination_target: "s3://release-evidence/exports",
    status: "PUBLISHED",
    published_hash: "d2a8f5c3b91e7d4f2a6c8e3b5d9f1a4c7e2b8d3f6a0c5e9b2d8f4a1c7e3b5d9f",
    integrity_verified: true,
    receipt_id: "receipt-def456",
    idempotency_key: "idem-002",
    published_at: "2026-10-20T16:30:00Z",
    verified_at: null,
    attempts: 1,
    is_idempotent: true,
  },
];

export function PublicationExecution({ publicationId }: { publicationId?: string }) {
  const { isAuthenticated } = useAuth();
  const [publications, setPublications] = useState<PublicationRecord[]>(DEMO_PUBLICATIONS);
  const [selectedPub, setSelectedPub] = useState<PublicationRecord | null>(
    publicationId ? DEMO_PUBLICATIONS.find((p) => p.id === publicationId) || null : null
  );
  const [isPublishing, setIsPublishing] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [useDemoData, setUseDemoData] = useState(false);

  const pendingPublications = useMemo(() => publications.filter((p) => p.status === "STAGED"), [publications]);
  const publishedPublications = useMemo(() => publications.filter((p) => p.status === "PUBLISHED" || p.status === "VERIFIED"), [publications]);

  const handleSelect = (pub: PublicationRecord) => setSelectedPub(pub);

  const handlePublish = async () => {
    if (!selectedPub || selectedPub.status !== "STAGED") return;
    setIsPublishing(true);
    await new Promise((r) => setTimeout(r, 2500));
    setIsPublishing(false);
    const updated = { ...selectedPub, status: "PUBLISHED" as const, published_at: new Date().toISOString() };
    setPublications((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    setSelectedPub(updated);
    setUseDemoData(true);
  };

  const handleVerify = async () => {
    if (!selectedPub) return;
    setIsVerifying(true);
    await new Promise((r) => setTimeout(r, 1800));
    setIsVerifying(false);
    const updated = {
      ...selectedPub,
      status: "VERIFIED" as const,
      integrity_verified: selectedPub.published_hash === selectedPub.content_hash,
      verified_at: new Date().toISOString(),
    };
    setPublications((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    setSelectedPub(updated);
    setUseDemoData(true);
  };

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
            <Send className="h-5 w-5 text-rg-primary" />
            Publication Execution
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            Execute and verify dataset publications with idempotency and integrity checks.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge className={cn(pendingPublications.length > 0 ? "bg-amber-100 text-amber-700 border-amber-200" : "bg-green-100 text-green-700 border-green-200")}>
            {pendingPublications.length} pending
          </Badge>
          <Badge className="bg-green-100 text-green-700 border-green-200">
            {publishedPublications.length} published
          </Badge>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Publication list */}
        <div className="lg:col-span-2 space-y-4">
          {publications.map((pub, idx) => (
            <Card
              key={pub.id}
              className={cn(
                "transition-all duration-200 animate-fade-in cursor-pointer hover:shadow-md hover:border-rg-primary-light/50",
                selectedPub?.id === pub.id && "border-rg-primary ring-2 ring-rg-primary/20"
              )}
              style={{ animationDelay: `${idx * 50}ms` }}
              onClick={() => handleSelect(pub)}
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                    pub.status === "VERIFIED" ? "bg-green-100 text-green-600" :
                    pub.status === "PUBLISHED" ? "bg-blue-100 text-blue-600" :
                    pub.status === "FAILED" ? "bg-red-100 text-red-600" :
                    "bg-amber-100 text-amber-600"
                  )}>
                    {pub.status === "VERIFIED" ? (
                      <CheckCircle className="h-5 w-5" />
                    ) : pub.status === "PUBLISHED" ? (
                      <Send className="h-5 w-5" />
                    ) : pub.status === "FAILED" ? (
                      <XCircle className="h-5 w-5" />
                    ) : (
                      <Clock className="h-5 w-5" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-rg-text truncate">
                        {DEMO_DATASETS.find((d) => d.id === pub.dataset_id)?.name || "Unknown dataset"}
                      </h3>
                      <Badge variant="outline" className={cn(getStatusColor(pub.status))} className="text-[10px]">
                        {pub.status}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-rg-text-muted">
                      <span className="font-mono">{truncateHash(pub.content_hash, 8, 8)}</span>
                      <span>→ {pub.destination_target}</span>
                      {pub.idempotency_key && (
                        <span className="flex items-center gap-1">
                          <Hash className="h-3 w-3" />
                          Idempotent
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-xs text-rg-text-muted">
                        {pub.published_at ? `Published ${formatDate(pub.published_at)}` : pub.status === "STAGED" ? "Awaiting publication" : ""}
                      </span>
                      {pub.integrity_verified !== null && (
                        <Badge variant={pub.integrity_verified ? "success" : "error"} className="text-[10px]">
                          {pub.integrity_verified ? "Integrity verified" : "Integrity check pending"}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {publications.length === 0 && (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Send className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">No publications yet</h3>
                <p className="text-sm text-rg-text-muted">Prepare a release to begin the publication workflow.</p>
              </div>
            </Card>
          )}
        </div>

        {/* Detail panel */}
        <div className="space-y-4">
          {selectedPub ? (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Hash className="h-4 w-4 text-rg-text-muted" />
                    Publication Details
                  </CardTitle>
                  <CardDescription>
                    {selectedPub.status === "STAGED" ? "Awaiting publication" :
                     selectedPub.status === "PUBLISHED" ? "Published" :
                     selectedPub.status === "VERIFIED" ? "Verified" :
                     "Failed"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Release ID</p>
                      <p className="font-mono text-rg-text">{selectedPub.release_id}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Dataset</p>
                      <p className="text-rg-text truncate ml-2 max-w-[120px]">
                        {DEMO_DATASETS.find((d) => d.id === selectedPub.dataset_id)?.name}
                      </p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Version</p>
                      <p className="text-rg-text">v{selectedPub.version_number}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-xs text-rg-text-muted">Destination</p>
                      <p className="text-rg-text truncate ml-2 font-mono">{selectedPub.destination_target}</p>
                    </div>
                  </div>

                  <div className="p-3 bg-rg-surface-alt rounded-lg">
                    <p className="text-xs text-rg-text-muted mb-1">Content Hash (SHA-256)</p>
                    <code className="block font-mono text-sm text-rg-text break-all bg-white rounded px-2 py-1.5 border border-rg-border">
                      {selectedPub.content_hash}
                    </code>
                  </div>

                  {selectedPub.published_hash && (
                    <div className="p-3 bg-rg-surface-alt rounded-lg">
                      <p className="text-xs text-rg-text-muted mb-1">Published Hash</p>
                      <code className="block font-mono text-sm text-rg-text break-all bg-white rounded px-2 py-1.5 border border-rg-border">
                        {selectedPub.published_hash}
                      </code>
                      <div className="flex items-center gap-2 mt-1.5">
                        <Badge variant={selectedPub.integrity_verified ? "success" : "error"} className="text-[10px]">
                          {selectedPub.integrity_verified ? "Integrity verified" : "Mismatch"}
                        </Badge>
                        {selectedPub.receipt_id && (
                          <span className="text-xs text-rg-text-muted">
                            Receipt: <span className="font-mono">{selectedPub.receipt_id}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="pt-3 border-t border-rg-border/50 space-y-1 text-xs text-rg-text-muted">
                    <div className="flex justify-between">
                      <span>Idempotency Key</span>
                      <span className="font-mono text-rg-text truncate ml-2 max-w-[120px]">{selectedPub.idempotency_key}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Attempts</span>
                      <span className="text-rg-text">{selectedPub.attempts}</span>
                    </div>
                    {selectedPub.published_at && (
                      <div className="flex justify-between">
                        <span>Published At</span>
                        <span>{formatDate(selectedPub.published_at)}</span>
                      </div>
                    )}
                    {selectedPub.verified_at && (
                      <div className="flex justify-between">
                        <span>Verified At</span>
                        <span>{formatDate(selectedPub.verified_at)}</span>
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-rg-border/50">
                    {selectedPub.status === "STAGED" && (
                      <div className="flex gap-3">
                        <Button className="flex-1" disabled={isPublishing} onClick={handlePublish} loading={isPublishing}>
                          <Send className="h-4 w-4" />
                          {isPublishing ? "Publishing…" : "Publish Now"}
                        </Button>
                      </div>
                    )}
                    {selectedPub.status === "PUBLISHED" && !selectedPub.integrity_verified && (
                      <div className="flex gap-3">
                        <Button className="flex-1" disabled={isVerifying} onClick={handleVerify} loading={isVerifying}>
                          <Shield className="h-4 w-4" />
                          {isVerifying ? "Verifying…" : "Verify Publication"}
                        </Button>
                      </div>
                    )}
                    {selectedPub.status === "VERIFIED" && (
                      <div className="flex items-center gap-3 p-3 bg-green-50 rounded-lg border border-green-200">
                        <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
                        <div>
                          <p className="text-sm font-medium text-green-800">Publication Verified</p>
                          <p className="text-xs text-green-600">Integrity check passed. Publication is complete and verified.</p>
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4 text-sm text-rg-text-muted space-y-2">
                  <div className="flex items-start gap-2">
                    <Hash className="h-3.5 w-3.5 text-rg-text-muted shrink-0 mt-0.5" />
                    <span>Publication binds to the exact SHA-256 hash approved by the human steward.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <Shield className="h-3.5 w-3.5 text-rg-text-muted shrink-0 mt-0.5" />
                    <span>Idempotency ensures repeated publication attempts with the same key are safe and produce the same result.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <Clock className="h-3.5 w-3.5 text-rg-text-muted shrink-0 mt-0.5" />
                    <span>Independent verification confirms the destination artifact matches the approved hash.</span>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Send className="h-12 w-12 text-rg-text-muted mb-4 opacity-50" />
                <h3 className="text-lg font-semibold text-rg-text mb-1">Select a publication</h3>
                <p className="text-sm text-rg-text-muted">Choose a publication record to view details and execute or verify.</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

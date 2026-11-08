import { useState, useCallback } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Dashboard } from "@/pages/Dashboard";
import { LoginPage } from "@/pages/Login";
import { DatasetList } from "@/pages/DatasetList";
import { DatasetDetail } from "@/pages/DatasetDetail";
import { InspectionWorkspace } from "@/pages/InspectionWorkspace";
import { FindingDetail } from "@/pages/FindingDetail";
import { TransformationWorkspace } from "@/pages/TransformationWorkspace";
import { AIVisionReport } from "@/pages/AIVisionReport";
import { IndependentReviewer } from "@/pages/IndependentReviewer";
import { ReleasePreparation } from "@/pages/ReleasePreparation";
import { HumanApproval } from "@/pages/HumanApproval";
import { PublicationExecution } from "@/pages/PublicationExecution";
import { WithdrawalScreen } from "@/pages/WithdrawalScreen";
import { AuditLogPage } from "@/pages/AuditLog";
import { SystemStatus } from "@/pages/SystemStatus";
import { ToastContainer } from "@/components/layout/ToastContainer";
import {
  LayoutDashboard,
  Database,
  Search,
  AlertTriangle,
  GitBranch,
  FileSearch,
  Shield,
  Send,
  CheckCircle,
  XCircle,
  Clock,
  BarChart3,
  Loader2,
  Wifi,
  WifiOff,
  AlertCircle,
} from "lucide-react";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/datasets", label: "Datasets", icon: Database },
  { path: "/inspections", label: "Inspections", icon: FileSearch },
  { path: "/reviews", label: "Reviews", icon: Shield },
  { path: "/releases", label: "Releases", icon: GitBranch },
  { path: "/approvals", label: "Approvals", icon: Clock },
  { path: "/publications", label: "Publications", icon: Send },
  { path: "/audit", label: "Audit Log", icon: BarChart3 },
  { path: "/status", label: "System Status", icon: Wifi },
];

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();
  const [path, setPath] = useState(window.location.pathname);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-rg-surface">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-rg-primary animate-spin" />
          <span className="text-sm text-rg-text-muted">Loading ReleaseGate…</span>
        </div>
      </div>
    );
  }

  const renderPage = () => {
    if (!isAuthenticated) {
      return <LoginPage />;
    }

    const params = new URLSearchParams(window.location.search);
    switch (path) {
      case "/":
        return <Dashboard />;
      case "/datasets":
        return <DatasetList />;
      case "/datasets/:id":
        const dsId = params.get("id");
        return dsId ? <DatasetDetail datasetId={dsId} /> : <DatasetList />;
      case "/inspections":
        const inspId = params.get("id");
        return inspId ? <InspectionWorkspace inspectionId={inspId} /> : <InspectionWorkspace />;
      case "/findings/:id":
        const fdId = params.get("id");
        return fdId ? <FindingDetail findingId={fdId} /> : <InspectionWorkspace />;
      case "/transformations":
        return <TransformationWorkspace />;
      case "/ai-report":
        return <AIVisionReport />;
      case "/reviews":
        const revId = params.get("id");
        return revId ? <IndependentReviewer reviewId={revId} /> : <IndependentReviewer />;
      case "/releases/prepare":
        const relId = params.get("release_id");
        return relId ? <ReleasePreparation releaseId={relId} /> : <ReleasePreparation />;
      case "/approvals":
        const appId = params.get("id");
        return appId ? <HumanApproval approvalId={appId} /> : <HumanApproval />;
      case "/publications":
        const pubId = params.get("id");
        return pubId ? <PublicationExecution publicationId={pubId} /> : <PublicationExecution />;
      case "/withdraw":
        const wdId = params.get("release_id");
        return wdId ? <WithdrawalScreen releaseId={wdId} /> : <WithdrawalScreen />;
      case "/audit":
        return <AuditLogPage />;
      case "/status":
        return <SystemStatus />;
      default:
        return (
          <div className="min-h-screen flex items-center justify-center bg-rg-surface">
            <div className="text-center">
              <AlertCircle className="w-12 h-12 text-rg-text-muted mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-rg-text mb-2">Page not found</h2>
              <p className="text-sm text-rg-text-muted mb-6">
                The page you&apos;re looking for doesn&apos;t exist.
              </p>
              <a
                href="/"
                className="inline-flex items-center gap-2 px-4 py-2 bg-rg-primary text-white rounded-lg text-sm font-medium hover:bg-rg-primary-dark transition-colors"
              >
                Return to Dashboard
              </a>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-rg-surface">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-rg-border bg-rg-surface/95 backdrop-blur supports-backdrop-filter">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rg-primary">
                <Shield className="h-4 w-4 text-white" />
              </div>
              <div className="hidden sm:block">
                <span className="text-sm font-semibold text-rg-text">ReleaseGate</span>
                <span className="ml-2 text-xs text-rg-text-muted font-mono">v1.0</span>
              </div>
            </div>

            {/* Nav links */}
            <nav className="hidden md:flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <a
                  key={item.path}
                  href={item.path}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    path === item.path || (item.path !== "/" && path.startsWith(item.path))
                      ? "bg-rg-primary-light text-rg-primary font-semibold"
                      : "text-rg-text-muted hover:text-rg-text hover:bg-rg-surface-alt"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </a>
              ))}
            </nav>

            {/* Right side */}
            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 text-xs text-rg-text-muted">
                <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                <span>API Connected</span>
              </div>
              <a
                href="/status"
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium text-rg-text-muted hover:text-rg-text hover:bg-rg-surface-alt transition-colors"
                title="System Status"
              >
                <Wifi className="h-4 w-4 text-green-500" />
              </a>
              <button
                onClick={() => {
                  localStorage.clear();
                  window.location.href = "/login";
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-rg-text-muted hover:text-red-600 hover:bg-red-50 transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6">
        {renderPage()}
      </main>

      {/* Footer */}
      <footer className="border-t border-rg-border mt-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p className="text-xs text-rg-text-muted">
            ReleaseGate v1.0 — Evidence-Driven AI Data Release Governance
          </p>
          <p className="text-xs text-rg-text-muted">
            Hybrid Governance Platform • Architecture Baseline v1.0 Frozen
          </p>
        </div>
      </footer>

      <ToastContainer />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

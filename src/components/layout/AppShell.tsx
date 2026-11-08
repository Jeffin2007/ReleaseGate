import { ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Shield, LogOut, LayoutDashboard, Database, Search, FileText, ClipboardCheck, Layers, FileSearch, GitCompare, FilePen, Send, BookCheck, Archive, ScrollText, Activity } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { RoleGate } from "@/pages/RoleGate";

const navItems = [
  { path: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: ["ADMIN", "STEWARD", "AUDITOR"] },
  { path: "/datasets", label: "Datasets", icon: Database, roles: ["ADMIN", "STEWARD"] },
  { path: "/audit", label: "Audit Log", icon: ScrollText, roles: ["ADMIN", "AUDITOR"] },
  { path: "/status", label: "System Status", icon: Activity, roles: ["ADMIN"] },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-rg-bg text-rg-text">
      <nav className="border-b border-rg-border bg-rg-surface">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-rg-primary text-white">
                <Shield className="w-5 h-5" />
              </div>
              <div className="hidden sm:block">
                <h1 className="text-lg font-bold text-rg-text">ReleaseGate</h1>
                <p className="text-xs text-rg-text-muted mt-0.5">AI Data Release Governance</p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              {navItems.map((item) => (
                <RoleGate key={item.path} roles={item.roles}>
                  <button
                    onClick={() => navigate(item.path)}
                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      location.pathname === item.path
                        ? "bg-rg-primary text-white"
                        : "text-rg-text-muted hover:bg-rg-hover hover:text-rg-text"
                    }`}
                  >
                    <item.icon className="w-4 h-4" />
                    <span className="hidden sm:inline">{item.label}</span>
                  </button>
                </RoleGate>
              ))}
            </div>

            <div className="flex items-center gap-3">
              {user && (
                <div className="text-right">
                  <p className="text-sm font-medium text-rg-text">{user.full_name}</p>
                  <p className="text-xs text-rg-text-muted capitalize">{user.role.toLowerCase()}</p>
                </div>
              )}
              <button onClick={handleLogout} className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-rg-text-muted hover:text-red-600 hover:bg-red-50 transition-colors">
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>
    </div>
  );
}

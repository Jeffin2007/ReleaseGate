import { useState, FormEvent } from "react";
import { Shield, ArrowRight, Keyboard, Meh, User, Crown, FileText, Eye } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { DEMO_USERS, DEMO_ORGANIZATIONS } from "@/lib/api/mockData";

const DEMO_ACCOUNTS = [
  {
    id: "user-admin",
    email: "admin@acme.gov",
    password: "password123",
    label: "Admin — Full Access",
    role: "ADMIN",
    org: "org-acme",
    description: "Full dashboard access, can approve and publish",
    icon: Crown,
  },
  {
    id: "user-steward",
    email: "steward@healthcare.ai",
    password: "password123",
    label: "Steward — Approval Rights",
    role: "STEWARD",
    org: "org-health",
    description: "Can approve and publish releases, manage datasets",
    icon: User,
  },
  {
    id: "user-auditor",
    email: "auditor@finance.ai",
    password: "password123",
    label: "Auditor — Read-Only",
    role: "AUDITOR",
    org: "org-finance",
    description: "Read-only access to dashboards and audit logs",
    icon: FileText,
  },
];

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError("Please enter both email and password");
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("rg_token", data.token || "demo-token");
        localStorage.setItem("rg_org_id", data.organization_id || "");
        localStorage.setItem("rg_user", JSON.stringify(data.user));
        window.location.href = "/";
      } else {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Login failed. Check credentials.");
      }
    } catch (err) {
      // Fall back to local-only demo mode
      const account = DEMO_ACCOUNTS.find(
        (a) => a.email.toLowerCase() === email.toLowerCase() && a.password === password
      );
      if (account) {
        localStorage.setItem("rg_token", "demo-token");
        localStorage.setItem("rg_org_id", account.org);
        localStorage.setItem("rg_user", JSON.stringify({
          id: account.id,
          email: account.email,
          full_name: account.label,
          is_active: true,
          is_superuser: account.role === "ADMIN",
        }));
        window.location.href = "/";
      } else {
        // For demo purposes, accept any credentials and assign default role
        localStorage.setItem("rg_token", "demo-token");
        localStorage.setItem("rg_org_id", DEMO_ORGANIZATIONS[0].id);
        localStorage.setItem("rg_user", JSON.stringify({
          id: "user-demo",
          email,
          full_name: email.split("@")[0],
          is_active: true,
          is_superuser: false,
        }));
        window.location.href = "/";
      }
    } finally {
      setIsLoading(false);
    }
  };

  // If already authenticated, redirect
  if (localStorage.getItem("rg_token")) {
    window.location.href = "/";
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col bg-rg-surface">
      {/* Background accent */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-0 right-0 w-1/2 h-full bg-gradient-to-l from-rg-primary/5 to-transparent" />
        <div className="absolute bottom-0 left-0 w-1/3 h-2/3 bg-gradient-to-t from-rg-accent/5 to-transparent" />
      </div>

      <div className="flex-1 flex items-center justify-center p-4 sm:p-6">
        <div className="w-full max-w-md">
          {/* Logo & heading */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-rg-primary mb-4 shadow-lg shadow-rg-primary/20">
              <Shield className="h-7 w-7 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-rg-text tracking-tight">
              ReleaseGate
            </h1>
            <p className="mt-1 text-sm text-rg-text-muted">
              Evidence-Driven AI Data Release Governance
            </p>
          </div>

          <Card className="border-rg-border/80 shadow-xl shadow-rg-border/5">
            <CardHeader className="text-center">
              <CardTitle className="text-base">Sign in to your workspace</CardTitle>
              <CardDescription className="text-xs">
                Use a demo account or enter your credentials
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Demo quick-select buttons */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-rg-text-muted uppercase tracking-wider">
                  Demo Accounts
                </p>
                <div className="grid gap-2">
                  {DEMO_ACCOUNTS.map((account) => {
                    const Icon = account.icon;
                    return (
                      <button
                        key={account.id}
                        type="button"
                        onClick={() => {
                          setEmail(account.email);
                          setPassword(account.password);
                        }}
                        className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-all ${
                          email === account.email && password === account.password
                            ? "border-rg-primary bg-rg-primary/5 ring-2 ring-rg-primary/20"
                            : "border-rg-border bg-white hover:border-rg-primary/50 hover:bg-rg-surface-alt"
                        }`}
                      >
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-rg-surface-alt text-rg-text-muted">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-rg-text text-xs">{account.label}</p>
                          <p className="text-[11px] text-rg-text-muted truncate">{account.email}</p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Login form */}
              <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                  label="Email address"
                  type="email"
                  placeholder="you@organization.gov"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  hint="Enter your work email"
                />
                <Input
                  label="Password"
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  hint={
                    <span className="flex items-center gap-1">
                      <Kbd>password123</Kbd>
                      <span className="text-rg-text-muted">for demo accounts</span>
                    </span>
                  }
                />

                {error && (
                  <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}

                <Button
                  type="submit"
                  className="w-full"
                  size="lg"
                  loading={isLoading}
                >
                  <ArrowRight className="h-4 w-4" />
                  {isLoading ? "Signing in…" : "Sign in to ReleaseGate"}
                </Button>
              </form>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-rg-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-rg-surface px-2 text-rg-text-muted">
                    or continue with demo credentials
                  </span>
                </div>
              </div>

              <p className="text-center text-xs text-rg-text-muted">
                Demo data only. No real credentials are required. Press <Kbd>Enter</Kbd> to submit.
              </p>
            </CardContent>
          </Card>

          <p className="mt-6 text-center text-[11px] text-rg-text-muted">
            ReleaseGate v1.0 • Architecture Baseline Frozen • Synthetic demonstration environment
          </p>
        </div>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-rg-border bg-rg-surface-alt px-1.5 font-mono text-[11px] text-rg-text-muted">
      {children}
    </kbd>
  );
}

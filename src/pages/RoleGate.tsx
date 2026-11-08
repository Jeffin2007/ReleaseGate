import { ReactNode } from "react";
import { useAuth } from "@/contexts/AuthContext";

interface RoleGateProps {
  roles: Array<"ADMIN" | "STEWARD" | "AUDITOR">;
  fallback?: ReactNode;
  children: ReactNode;
}

export function RoleGate({ roles, fallback, children }: RoleGateProps) {
  const { user } = useAuth();

  if (!user || !roles.includes(user.role as "ADMIN" | "STEWARD" | "AUDITOR")) {
    return fallback || (
      <div className="p-8 text-center border border-rg-border rounded-lg bg-rg-surface-alt">
        <p className="text-sm text-rg-text-muted">You do not have permission to view this section.</p>
      </div>
    );
  }

  return <>{children}</>;
}

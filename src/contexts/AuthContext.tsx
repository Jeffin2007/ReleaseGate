import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from "react";
import { api, SessionUser } from "@/lib/api";

interface AuthContextType {
  user: SessionUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  switchOrganization: (orgId: string) => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const restoreSession = useCallback(async () => {
    const token = localStorage.getItem("rg_token");
    const orgId = localStorage.getItem("rg_org_id");
    const storedUser = localStorage.getItem("rg_user");
    if (!token || !orgId || !storedUser) {
      setIsLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser({ user: me, organization_id: orgId, role: "USER" });
    } catch {
      localStorage.removeItem("rg_token");
      localStorage.removeItem("rg_org_id");
      localStorage.removeItem("rg_user");
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    const session: SessionUser = {
      user: result.user,
      organization_id: result.organization_id || "",
      role: result.role || "USER",
    };
    localStorage.setItem("rg_token", "simulated-jwt-token");
    localStorage.setItem("rg_org_id", session.organization_id);
    localStorage.setItem("rg_user", JSON.stringify(session.user));
    setUser(session);
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setUser(null);
  }, []);

  const switchOrganization = useCallback((orgId: string) => {
    if (user) {
      localStorage.setItem("rg_org_id", orgId);
      setUser({ ...user, organization_id: orgId });
    }
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        switchOrganization,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

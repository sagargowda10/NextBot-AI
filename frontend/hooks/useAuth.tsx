"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, tokens } from "@/services/api";
import type { Role, TokenPair, User } from "@/types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (full_name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const me = await api<User>("/api/v1/auth/me");
    setUser(me);
    return me;
  }, []);

  useEffect(() => {
    if (!tokens.access) { setLoading(false); return; }
    loadMe().catch(() => tokens.clear()).finally(() => setLoading(false));
  }, [loadMe]);

  const value = useMemo<AuthCtx>(() => ({
    user,
    loading,
    async login(email, password) {
      tokens.set(await api<TokenPair>("/api/v1/auth/login", { method: "POST", json: { email, password } }));
      return loadMe();
    },
    async register(full_name, email, password) {
      tokens.set(await api<TokenPair>("/api/v1/auth/register", { method: "POST", json: { full_name, email, password } }));
      return loadMe();
    },
    logout() { tokens.clear(); setUser(null); },
    hasRole: (...roles) => !!user && user.roles.some((r) => roles.includes(r)),
  }), [user, loading, loadMe]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

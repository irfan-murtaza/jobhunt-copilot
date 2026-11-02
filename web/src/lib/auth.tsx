"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, json, setToken } from "@/lib/api";
import type { TokenResponse, User } from "@/lib/types";

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Resolve the session asynchronously so state updates happen in a callback, not the effect body.
    const bootstrap = getToken() ? api<User>("/auth/me").then(setUser).catch(() => setToken(null)) : Promise.resolve();
    bootstrap.finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await api<TokenResponse>("/auth/login", { method: "POST", body: json({ email, password }) });
    setToken(token.access_token);
    setUser(await api<User>("/auth/me"));
  }, []);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const token = await api<TokenResponse>("/auth/register", {
      method: "POST",
      body: json({ email, password, display_name: displayName || null }),
    });
    setToken(token.access_token);
    setUser(await api<User>("/auth/me"));
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Redirects to /login when there is no session. Returns the user once known. */
export function useRequireAuth(): User | null {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  return user;
}

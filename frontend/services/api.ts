"use client";

import type { TokenPair } from "@/types";

// Empty = same origin: the browser calls /api/... on the frontend's own address and Next.js proxies it to the backend
// (see next.config.mjs). Works on localhost, a phone on the LAN, a tunnel URL or a real domain. Set NEXT_PUBLIC_API_URL
// only to call a backend on another domain directly.
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const ACCESS = "nb_access";
const REFRESH = "nb_refresh";

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

export const tokens = {
  get access() { return typeof window === "undefined" ? null : localStorage.getItem(ACCESS); },
  get refresh() { return typeof window === "undefined" ? null : localStorage.getItem(REFRESH); },
  set(pair: TokenPair) { localStorage.setItem(ACCESS, pair.access_token); localStorage.setItem(REFRESH, pair.refresh_token); },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH); },
};

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const rt = tokens.refresh;
  if (!rt) return false;
  refreshing ??= fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }),
  }).then(async (r) => {
    if (!r.ok) { tokens.clear(); return false; }
    tokens.set(await r.json());
    return true;
  }).finally(() => { refreshing = null; });
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  const at = tokens.access;
  if (at) headers.set("Authorization", `Bearer ${at}`);
  const res = await fetch(`${API_URL}${path}`, {
    ...init, headers, body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 401 && retry && (await tryRefresh())) return api<T>(path, init, false);
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = body?.error?.message ?? (Array.isArray(body?.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : body?.detail) ?? res.statusText;
    throw new ApiError(res.status, String(msg), body?.error?.details);
  }
  return body as T;
}

export const inr = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");

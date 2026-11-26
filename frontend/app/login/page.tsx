"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Button, ErrorNote, Input } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";

const DEMO = [
  ["Customer", "asha@nextbot.demo", "Demo@1234"], ["Admin", "admin@nextbot.demo", "Admin@1234"],
  ["Support", "support@nextbot.demo", "Support@1234"], ["Inventory", "inventory@nextbot.demo", "Inventory@1234"],
];

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      const home = user.roles.includes("ADMIN") ? "/admin" : user.roles.includes("INVENTORY_MANAGER") ? "/admin/inventory"
        : user.roles.includes("SUPPORT_AGENT") ? "/support" : "/dashboard";
      router.push(next && next.startsWith("/") ? next : home);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-ink-100 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-card">
        <div>
          <h1 className="text-xl font-semibold">Sign in to NextBot AI</h1>
          <p className="text-sm text-ink-500">No account? <Link href="/register" className="text-brand-600 hover:underline">Create one</Link></p>
        </div>
        <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        <ErrorNote message={error} />
        <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
        <div className="border-t border-ink-100 pt-4">
          <p className="mb-2 text-xs font-medium text-ink-500">Demo accounts (fictional data)</p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO.map(([label, e, p]) => (
              <button type="button" key={e} onClick={() => { setEmail(e); setPassword(p); }}
                      className="rounded-lg border border-ink-300 px-2 py-1.5 text-xs hover:border-brand-500">{label}</button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}

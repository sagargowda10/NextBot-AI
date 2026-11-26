"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Input } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.password.length < 8) return setError("Password must be at least 8 characters");
    setBusy(true);
    setError(null);
    try {
      await register(form.full_name, form.email, form.password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-ink-100 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-card">
        <div>
          <h1 className="text-xl font-semibold">Create your account</h1>
          <p className="text-sm text-ink-500">Already registered? <Link href="/login" className="text-brand-600 hover:underline">Sign in</Link></p>
        </div>
        <Input label="Full name" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <Input label="Email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input label="Password" type="password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <ErrorNote message={error} />
        <Button type="submit" disabled={busy} className="w-full">{busy ? "Creating…" : "Create account"}</Button>
      </form>
    </div>
  );
}

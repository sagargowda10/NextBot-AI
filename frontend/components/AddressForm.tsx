"use client";

import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Input } from "@/components/ui";
import { api } from "@/services/api";
import type { Address } from "@/types";

const STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
  "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
  "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
  "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Lakshadweep",
];

type Form = Omit<Address, "id">;
const EMPTY: Form = { label: "Home", line1: "", line2: "", city: "", state: "Karnataka", pincode: "", phone: "", is_default: false };

/** Create or edit an address. Validates the same rules as the backend (6-digit PIN, 10–13 digit phone). */
export function AddressForm({ initial, onSaved, onCancel }: { initial?: Address; onSaved: (a: Address) => void; onCancel?: () => void }) {
  const [f, setF] = useState<Form>(initial ? { ...initial, line2: initial.line2 ?? "" } : EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^[1-9][0-9]{5}$/.test(f.pincode)) return setError("PIN code must be 6 digits and can't start with 0");
    if (!/^\+?[0-9]{10,13}$/.test(f.phone)) return setError("Phone must be 10–13 digits (e.g. 9876543210)");
    setBusy(true);
    try {
      const body = { ...f, line2: f.line2?.trim() || null };
      const saved = initial
        ? await api<Address>(`/api/v1/auth/me/addresses/${initial.id}`, { method: "PUT", json: body })
        : await api<Address>("/api/v1/auth/me/addresses", { method: "POST", json: body });
      onSaved(saved);
      if (!initial) setF(EMPTY);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save address");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="grid gap-3 sm:grid-cols-2">
      <Input label="Label" placeholder="Home / Work" value={f.label} onChange={set("label")} required maxLength={40} />
      <Input label="Phone" placeholder="9876543210" inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value.replace(/[^\d+]/g, "") })} required />
      <div className="sm:col-span-2"><Input label="Address line 1" placeholder="House no, street, area" value={f.line1} onChange={set("line1")} required minLength={3} maxLength={200} /></div>
      <div className="sm:col-span-2"><Input label="Address line 2 (optional)" placeholder="Landmark, apartment" value={f.line2 ?? ""} onChange={set("line2")} maxLength={200} /></div>
      <Input label="City" placeholder="Bengaluru" value={f.city} onChange={set("city")} required minLength={2} />
      <label className="block text-sm">
        <span className="mb-1 block font-medium text-ink-700">State</span>
        <select value={f.state} onChange={set("state")} className="w-full rounded-lg border border-ink-300 px-3 py-2 outline-none ring-brand-500 focus:ring-2">
          {STATES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      <Input label="PIN code" placeholder="560001" inputMode="numeric" maxLength={6} value={f.pincode} onChange={(e) => setF({ ...f, pincode: e.target.value.replace(/\D/g, "") })} required />
      <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink-700">
        <input type="checkbox" checked={f.is_default} onChange={(e) => setF({ ...f, is_default: e.target.checked })} /> Make this my default address
      </label>
      <div className="sm:col-span-2"><ErrorNote message={error} /></div>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : initial ? "Update address" : "Save address"}</Button>
        {onCancel && <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}

export const formatAddress = (a: Address) => [a.line1, a.line2, a.city, `${a.state} ${a.pincode}`].filter(Boolean).join(", ");

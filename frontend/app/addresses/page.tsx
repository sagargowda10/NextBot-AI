"use client";

import { useState } from "react";
import { AddressForm, formatAddress } from "@/components/AddressForm";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Address } from "@/types";

export default function AddressesPage() {
  const { data, loading, error, reload } = useApi<Address[]>("/api/v1/auth/me/addresses");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try { await fn(); await reload(); } catch (e) { setActionError(e instanceof Error ? e.message : "Action failed"); }
  }

  return (
    <AppShell roles={["CUSTOMER"]}>
      <PageHeader title="Delivery addresses" subtitle="Used at checkout and for delivery-time estimates"
                  action={!adding && <Button onClick={() => { setAdding(true); setEditing(null); }}>+ Add address</Button>} />
      <ErrorNote message={error ?? actionError} />
      {adding && (
        <Card title="New address" className="mb-6">
          <AddressForm onSaved={() => { setAdding(false); void reload(); }} onCancel={() => setAdding(false)} />
        </Card>
      )}
      {loading ? <Spinner /> : !data?.length ? (
        !adding && (
          <Card><p className="text-sm text-ink-500">You haven&apos;t saved an address yet. Add one to place orders.</p>
            <Button className="mt-3" onClick={() => setAdding(true)}>Add your first address</Button></Card>
        )
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((a) => (
            <Card key={a.id} title={<span className="flex items-center gap-2">{a.label}{a.is_default && <Badge tone="green">Default</Badge>}</span>}>
              {editing === a.id ? (
                <AddressForm initial={a} onSaved={() => { setEditing(null); void reload(); }} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <p className="text-sm text-ink-700">{formatAddress(a)}</p>
                  <p className="mt-1 text-xs text-ink-500">📞 {a.phone}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => { setEditing(a.id); setAdding(false); }}>Edit</Button>
                    {!a.is_default && <Button variant="outline" onClick={() => act(() => api(`/api/v1/auth/me/addresses/${a.id}/default`, { method: "POST" }))}>Set as default</Button>}
                    <Button variant="ghost" className="text-rose-600"
                            onClick={() => act(() => api(`/api/v1/auth/me/addresses/${a.id}`, { method: "DELETE" }))}>Delete</Button>
                  </div>
                </>
              )}
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}

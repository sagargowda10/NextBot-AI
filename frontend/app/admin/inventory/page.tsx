"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { StockLevel } from "@/types";

export default function InventoryDashboard() {
  const [lowOnly, setLowOnly] = useState(false);
  const { data, loading, error, reload } = useApi<StockLevel[]>(`/api/v1/inventory?size=100&low_only=${lowOnly}`, [lowOnly]);
  const [delta, setDelta] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  async function adjust(row: StockLevel) {
    const d = Number(delta[row.inventory_id]);
    if (!d) return;
    try {
      const r = await api<{ applied: boolean; message: string; approval_request_id?: number }>(`/api/v1/inventory/${row.inventory_id}`,
        { method: "PUT", json: { delta: d, reason: "Manual adjustment from dashboard" } });
      setMsg(r.applied ? `${row.sku}: ${r.message}` : `${row.sku}: sent for approval (#${r.approval_request_id})`);
      setDelta({ ...delta, [row.inventory_id]: "" });
      await reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <AppShell roles={["ADMIN", "INVENTORY_MANAGER"]}>
      <PageHeader title="Inventory" subtitle="Per-warehouse stock. Adjustments of 500+ units need admin approval."
                  action={<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />Low stock only</label>} />
      <ErrorNote message={error} />
      {msg && <p className="mb-4 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-900">{msg}</p>}
      <Card>
        {loading ? <Spinner /> : (
          <Table head={["Product", "SKU", "Warehouse", "On hand", "Reserved", "Available", "Adjust"]}>
            {(data ?? []).map((r) => (
              <tr key={r.inventory_id}>
                <Td>{r.product_name}</Td><Td className="font-mono text-xs">{r.sku}</Td><Td>{r.warehouse}</Td>
                <Td>{r.quantity}</Td><Td>{r.reserved}</Td>
                <Td>{r.low_stock ? <Badge tone={r.available === 0 ? "red" : "amber"}>{r.available}</Badge> : r.available}</Td>
                <Td>
                  <div className="flex gap-2">
                    <input value={delta[r.inventory_id] ?? ""} onChange={(e) => setDelta({ ...delta, [r.inventory_id]: e.target.value })}
                           placeholder="+/-" className="w-20 rounded border border-ink-300 px-2 py-1 text-sm" aria-label={`Adjust ${r.sku}`} />
                    <Button variant="outline" className="px-2 py-1" onClick={() => adjust(r)}>Apply</Button>
                  </div>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, inr, when } from "@/services/api";
import type { Order, Page, Shipment } from "@/types";

// Courier flow on the backend (ShipmentService.FLOW). Each click = one courier webhook in real life.
const FLOW = ["CREATED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"];
const DONE = ["DELIVERED", "CANCELLED", "RETURN_REQUESTED", "RETURNED", "REFUNDED", "PAYMENT_PENDING", "PAYMENT_FAILED", "CREATED"];

export default function AdminOrdersPage() {
  const [status, setStatus] = useState("");
  const { data, loading, error, reload } = useApi<Page<Order>>(`/api/v1/admin/orders?size=50${status ? `&status=${status}` : ""}`, [status]);
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function advance(o: Order, toDelivered = false) {
    setBusy(o.id); setMsg(null);
    try {
      const s = await api<Shipment | null>(`/api/v1/orders/${o.id}/tracking`);
      if (!s) throw new Error("No shipment yet - it is created a moment after payment; try again in a few seconds");
      const next = toDelivered ? "DELIVERED" : FLOW[FLOW.indexOf(s.status) + 1];
      if (!next) throw new Error(`Shipment is already ${s.status}`);
      await api(`/api/v1/shipments/${s.id}/status`, { method: "POST", json: { status: next, location: "Mysuru hub" } });
      setMsg(`${o.order_number} -> ${next}`);
      await reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }

  return (
    <AppShell roles={["ADMIN", "SUPPORT_AGENT", "INVENTORY_MANAGER"]}>
      <PageHeader title="All orders" subtitle="Simulate the courier: move shipments through Packed → Shipped → Out for delivery → Delivered"
                  action={<Badge tone="amber">Simulated courier</Badge>} />
      <div className="mb-4 flex items-center gap-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Status filter">
          {["", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "RETURN_REQUESTED", "CANCELLED", "PAYMENT_PENDING"].map((s) =>
            <option key={s} value={s}>{s ? s.replaceAll("_", " ") : "All statuses"}</option>)}
        </select>
        {msg && <p className="text-sm text-ink-700">{msg}</p>}
      </div>
      <ErrorNote message={error} />
      <Card>
        {loading ? <Spinner /> : !data?.items.length ? <p className="text-sm text-ink-500">No orders.</p> : (
          <Table head={["Order", "Placed", "Customer", "Total", "Payment", "Status", "Courier actions"]}>
            {data.items.map((o) => (
              <tr key={o.id}>
                <Td>
                  <Link href={`/orders/${o.id}`} className="font-medium text-brand-600 hover:underline">{o.order_number}</Link>
                  <Link href={`/admin/workflows?order=${o.id}`} className="ml-2 text-xs text-ink-500 hover:text-brand-600 hover:underline">workflow ↗</Link>
                </Td>
                <Td>{when(o.created_at)}</Td>
                <Td>#{o.user_id}</Td>
                <Td>{inr(o.total)}</Td>
                <Td>{o.payment_status ? <Badge>{o.payment_status}</Badge> : "—"}</Td>
                <Td><Badge>{o.status}</Badge></Td>
                <Td>
                  {DONE.includes(o.status) ? <span className="text-xs text-ink-500">—</span> : (
                    <div className="flex gap-2">
                      <Button variant="outline" className="px-3 py-1 text-xs" disabled={busy === o.id} onClick={() => advance(o)}>Next step</Button>
                      <Button className="px-3 py-1 text-xs" disabled={busy === o.id} onClick={() => advance(o, true)}>Mark delivered</Button>
                    </div>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}

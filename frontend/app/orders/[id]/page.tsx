"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, Table, Td, cx } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, inr, when } from "@/services/api";
import type { Order, Shipment } from "@/types";

const STEPS = ["CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"];

export default function OrderTrackingPage() {
  const { id } = useParams<{ id: string }>();
  const order = useApi<Order>(`/api/v1/orders/${id}`);
  const tracking = useApi<Shipment | null>(`/api/v1/orders/${id}/tracking`);
  const [msg, setMsg] = useState<string | null>(null);

  async function retryPayment() {
    try {
      await api("/api/v1/payments/initiate", { method: "POST", json: { order_id: Number(id), method: "mock_upi", idempotency_key: `retry-${crypto.randomUUID()}` } });
      await order.reload(); await tracking.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  async function cancel() {
    try {
      const r = await api<{ approval_request_id: number | null }>(`/api/v1/orders/${id}/cancel`, { method: "POST", json: { reason: "Customer request" } });
      setMsg(r.approval_request_id ? `Cancellation sent for review (#${r.approval_request_id}).` : "Order cancelled.");
      await order.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  if (order.loading) return <AppShell><Spinner /></AppShell>;
  const o = order.data;
  if (!o) return <AppShell><ErrorNote message={order.error ?? "Order not found"} /></AppShell>;
  const reached = STEPS.indexOf(o.status);

  return (
    <AppShell>
      <PageHeader title={`Order ${o.order_number}`} subtitle={`Placed ${when(o.created_at)}`} action={<Badge>{o.status}</Badge>} />
      <ErrorNote message={msg} />
      <Card title="Progress" className="mb-6">
        <ol className="grid grid-cols-3 gap-3 md:grid-cols-6">
          {STEPS.map((s, i) => (
            <li key={s} className={cx("rounded-lg border p-3 text-center text-xs font-medium", i <= reached ? "border-brand-600 bg-brand-50 text-brand-700" : "border-ink-100 text-ink-500")}>
              {s.replaceAll("_", " ")}
            </li>
          ))}
        </ol>
        {o.status === "PAYMENT_PENDING" && <Button className="mt-4" onClick={retryPayment}>Retry payment</Button>}
        {["CREATED", "PAYMENT_PENDING", "CONFIRMED", "PROCESSING"].includes(o.status) && <Button variant="outline" className="ml-2 mt-4" onClick={cancel}>Cancel order</Button>}
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Shipment">
          {tracking.loading ? <Spinner /> : !tracking.data ? <p className="text-sm text-ink-500">Not yet handed to a courier.</p> : (
            <>
              <p className="text-sm">{tracking.data.carrier} · <b>{tracking.data.tracking_number}</b> {tracking.data.is_simulated && <Badge tone="amber">simulated courier</Badge>}</p>
              {tracking.data.estimated_delivery && <p className="mt-1 text-sm text-ink-500">Estimated delivery: {tracking.data.estimated_delivery}</p>}
              <ul className="mt-4 space-y-3 border-l-2 border-brand-100 pl-4">
                {tracking.data.events.slice().reverse().map((e, i) => (
                  <li key={i} className="text-sm"><p className="font-medium">{e.note ?? e.status}</p><p className="text-xs text-ink-500">{when(e.at)} {e.location && `· ${e.location}`}</p></li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <Card title="Items">
          <Table head={["Product", "Qty", "Price"]}>
            {o.items.map((i) => <tr key={i.id}><Td>{i.product_name}</Td><Td>{i.quantity}</Td><Td>{inr(i.line_total)}</Td></tr>)}
          </Table>
          <p className="mt-4 text-right font-semibold">Total {inr(o.total)}</p>
        </Card>
      </div>
    </AppShell>
  );
}

"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { api, inr, when } from "@/services/api";
import type { Order, Page, ReturnRequest } from "@/types";

export default function ReturnsPage() {
  const { hasRole } = useAuth();
  const isCustomer = hasRole("CUSTOMER");
  const returns = useApi<ReturnRequest[]>("/api/v1/returns");
  const delivered = useApi<Page<Order>>(isCustomer ? "/api/v1/orders?size=50" : null);
  const [orderId, setOrderId] = useState<number | "">("");
  const [reason, setReason] = useState("Size doesn't fit");
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    setMsg(null);
    try {
      const r = await api<ReturnRequest>("/api/v1/returns", { method: "POST", json: { order_id: orderId || null, reason } });
      setMsg(r.eligible ? `Return #${r.id} is ${r.status.toLowerCase().replaceAll("_", " ")}.` : `Not eligible: ${r.eligibility_message}`);
      await returns.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  async function receive(id: number) {
    try { await api(`/api/v1/returns/${id}/receive`, { method: "POST" }); await returns.reload(); }
    catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  const eligible = delivered.data?.items.filter((o) => o.status === "DELIVERED") ?? [];
  return (
    <AppShell roles={["CUSTOMER", "SUPPORT_AGENT", "ADMIN"]}>
      <PageHeader title="Returns" subtitle="10-day return window · refunds ≥ ₹10,000 are reviewed by our team" />
      {isCustomer && (
        <Card title="Request a return" className="mb-6">
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <select value={orderId} onChange={(e) => setOrderId(e.target.value ? Number(e.target.value) : "")} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Order">
              <option value="">Latest delivered order</option>
              {eligible.map((o) => <option key={o.id} value={o.id}>{o.order_number} — {inr(o.total)}</option>)}
            </select>
            <input value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Reason" />
            <Button onClick={submit}>Submit</Button>
          </div>
          {msg && <p className="mt-3 text-sm text-ink-700">{msg}</p>}
        </Card>
      )}
      <ErrorNote message={returns.error} />
      <Card title="Return requests">
        {returns.loading ? <Spinner /> : !returns.data?.length ? <Empty title="No return requests." /> : (
          <Table head={["#", "Order", "Reason", "Refund", "Status", "Requested", ""]}>
            {returns.data.map((r) => (
              <tr key={r.id}>
                <Td>{r.id}</Td><Td>{r.order_number}</Td><Td>{r.reason}</Td><Td>{inr(r.refund_amount)}</Td>
                <Td><Badge>{r.status}</Badge></Td><Td>{when(r.created_at)}</Td>
                <Td>{!isCustomer && r.status === "APPROVED" && <Button variant="outline" onClick={() => receive(r.id)}>Mark received & refund</Button>}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}

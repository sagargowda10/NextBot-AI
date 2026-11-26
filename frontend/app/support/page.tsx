"use client";

import { AppShell } from "@/components/AppShell";
import { ChatPanel } from "@/components/ChatPanel";
import { Badge, Card, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { when } from "@/services/api";
import type { NotificationItem, Order, Page } from "@/types";

export default function SupportDashboard() {
  const notes = useApi<NotificationItem[]>("/api/v1/admin/notifications");
  const orders = useApi<Page<Order>>("/api/v1/admin/orders?size=10");
  const escalations = notes.data?.filter((n) => n.template === "support_escalation" && n.channel === "INTERNAL") ?? [];

  return (
    <AppShell roles={["ADMIN", "SUPPORT_AGENT"]}>
      <PageHeader title="Customer support desk" subtitle="Escalations, outbound notifications and recent orders" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Escalations (${escalations.length})`}>
          {notes.loading ? <Spinner /> : escalations.length === 0 ? <p className="text-sm text-ink-500">No open escalations.</p> : (
            <ul className="space-y-3">{escalations.map((e) => <li key={e.id} className="rounded-lg bg-amber-50 p-3 text-sm"><p className="font-medium">{e.subject}</p><p className="text-ink-700">{e.body}</p><p className="text-xs text-ink-500">{when(e.created_at)}</p></li>)}</ul>
          )}
        </Card>
        <Card title="Recent orders">
          <Table head={["Order", "Status", "Placed"]}>
            {(orders.data?.items ?? []).map((o) => <tr key={o.id}><Td>{o.order_number}</Td><Td><Badge>{o.status}</Badge></Td><Td>{when(o.created_at)}</Td></tr>)}
          </Table>
        </Card>
      </div>
      <Card title="Notification log (email / WhatsApp)" className="mt-6">
        <Table head={["When", "Channel", "Template", "Recipient", "Status"]}>
          {(notes.data ?? []).slice(0, 30).map((n) => (
            <tr key={n.id}><Td>{when(n.created_at)}</Td><Td>{n.channel}</Td><Td>{n.template}</Td><Td>{n.recipient}</Td><Td><Badge>{n.status}</Badge></Td></tr>
          ))}
        </Table>
      </Card>
      <div className="mt-6"><h2 className="mb-3 text-sm font-semibold">Assistant (support view)</h2><ChatPanel staff /></div>
    </AppShell>
  );
}

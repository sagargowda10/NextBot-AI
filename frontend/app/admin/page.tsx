"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { MiniBarChart } from "@/components/MiniChart";
import { Badge, Card, ErrorNote, PageHeader, Spinner, Stat, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { inr } from "@/services/api";
import type { Dashboard } from "@/types";

export default function AdminDashboard() {
  const { data: d, loading, error } = useApi<Dashboard>("/api/v1/analytics/dashboard");
  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title="Admin overview" subtitle="Live data from the platform (last 30 days)" />
      <ErrorNote message={error} />
      {loading || !d ? <Spinner /> : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="Revenue (30d)" value={inr(d.revenue_30d)} hint={`${d.orders_30d} paid orders`} />
            <Stat label="Customers" value={d.customers} hint={`${d.products} active products`} />
            <Stat label="Low-stock variants" value={d.low_stock_items} hint={<Link href="/admin/inventory" className="text-brand-600">Open inventory</Link>} />
            <Stat label="Pending approvals" value={d.pending_approvals} hint={<Link href="/admin/approvals" className="text-brand-600">Review</Link>} />
            <Stat label="Open returns" value={d.open_returns} />
            <Stat label="Plugins" value={`${d.plugins_enabled}/${d.plugins_total}`} hint="enabled" />
            <Stat label="Agent runs (24h)" value={d.agent_executions_24h} />
            <Stat label="Agent success rate" value={`${d.agent_success_rate}%`} />
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card title="Revenue by day">
              <MiniBarChart data={d.sales_by_day.map((s) => ({ label: s.date, value: Number(s.revenue) }))} />
            </Card>
            <Card title="Orders by status">
              <ul className="space-y-2 text-sm">
                {Object.entries(d.orders_by_status).map(([s, n]) => <li key={s} className="flex justify-between"><Badge>{s}</Badge><span>{n}</span></li>)}
              </ul>
            </Card>
          </div>
          <Card title="Top products" className="mt-6">
            <Table head={["Product", "Units", "Revenue"]}>
              {d.top_products.map((p) => <tr key={p.product_id}><Td>{p.name}</Td><Td>{p.units}</Td><Td>{inr(p.revenue)}</Td></tr>)}
            </Table>
          </Card>
        </>
      )}
    </AppShell>
  );
}

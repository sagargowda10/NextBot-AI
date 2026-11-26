"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { MiniBarChart } from "@/components/MiniChart";
import { Card, PageHeader, Spinner, Stat, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { inr } from "@/services/api";
import type { SalesSummary } from "@/types";

const PERIODS = ["today", "this week", "this month", "last month", "last 30 days", "this year"];

export default function AnalyticsPage() {
  const [period, setPeriod] = useState("this month");
  const sales = useApi<SalesSummary>(`/api/v1/analytics/sales?period=${encodeURIComponent(period)}`, [period]);
  const products = useApi<{ product_id: number; name: string; units: number; revenue: string }[]>("/api/v1/analytics/products?limit=10");
  const inventory = useApi<Record<string, number | string>>("/api/v1/analytics/inventory");

  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title="Analytics" action={
        <select value={period} onChange={(e) => setPeriod(e.target.value)} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Period">
          {PERIODS.map((p) => <option key={p}>{p}</option>)}
        </select>} />
      {sales.loading || !sales.data ? <Spinner /> : (
        <div className="grid gap-4 md:grid-cols-3">
          <Stat label="Revenue" value={inr(sales.data.revenue)} />
          <Stat label="Paid orders" value={sales.data.orders} />
          <Stat label="Average order value" value={inr(sales.data.average_order_value)} />
        </div>
      )}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title={`Revenue by day — ${period}`}>
          <MiniBarChart data={(sales.data?.by_day ?? []).map((d) => ({ label: d.date, value: Number(d.revenue) }))} />
        </Card>
        <Card title="Inventory insights">
          {inventory.data ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(inventory.data).map(([k, v]) => <div key={k}><dt className="text-ink-500">{k.replaceAll("_", " ")}</dt><dd className="font-semibold">{k === "stock_value" ? inr(v) : v}</dd></div>)}
            </dl>
          ) : <Spinner />}
        </Card>
      </div>
      <Card title="Product performance" className="mt-6">
        <Table head={["#", "Product", "Units sold", "Revenue"]}>
          {(products.data ?? []).map((p, i) => <tr key={p.product_id}><Td>{i + 1}</Td><Td>{p.name}</Td><Td>{p.units}</Td><Td>{inr(p.revenue)}</Td></tr>)}
        </Table>
      </Card>
    </AppShell>
  );
}

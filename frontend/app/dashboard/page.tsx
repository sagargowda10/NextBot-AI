"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge, Card, Empty, PageHeader, Spinner, Stat } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { inr, when } from "@/services/api";
import type { Cart, Order, Page, ReturnRequest } from "@/types";

export default function CustomerDashboard() {
  const { user } = useAuth();
  const orders = useApi<Page<Order>>("/api/v1/orders?size=5");
  const cart = useApi<Cart>("/api/v1/cart");
  const returns = useApi<ReturnRequest[]>("/api/v1/returns");
  const active = orders.data?.items.filter((o) => !["DELIVERED", "CANCELLED", "RETURNED"].includes(o.status)) ?? [];

  return (
    <AppShell roles={["CUSTOMER"]}>
      <PageHeader title={`Welcome back${user ? `, ${user.full_name.split(" ")[0]}` : ""}`} subtitle="Your orders, cart and returns at a glance"
                  action={<Link href="/assistant" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">Ask the AI assistant</Link>} />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Orders" value={orders.data?.total ?? "—"} />
        <Stat label="Active orders" value={active.length} />
        <Stat label="Cart" value={cart.data ? `${cart.data.items.length} item(s)` : "—"} hint={cart.data ? inr(cart.data.total) : undefined} />
        <Stat label="Returns" value={returns.data?.length ?? "—"} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Recent orders" action={<Link href="/orders" className="text-sm text-brand-600">View all</Link>}>
          {orders.loading ? <Spinner /> : !orders.data?.items.length ? <Empty title="No orders yet" action={{ href: "/products", label: "Start shopping" }} /> : (
            <ul className="divide-y divide-ink-100">
              {orders.data.items.map((o) => (
                <li key={o.id} className="flex items-center justify-between py-3 text-sm">
                  <Link href={`/orders/${o.id}`} className="font-medium hover:text-brand-700">{o.order_number}</Link>
                  <span className="text-ink-500">{when(o.created_at)}</span>
                  <span>{inr(o.total)}</span>
                  <Badge>{o.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Try asking NextBot">
          <ul className="space-y-2 text-sm text-ink-700">
            {["Track my latest order.", "Recommend a smartphone based on my budget.", "What is your return policy?", "I want to return my order."].map((q) => (
              <li key={q} className="rounded-lg bg-ink-100 px-3 py-2">“{q}”</li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}

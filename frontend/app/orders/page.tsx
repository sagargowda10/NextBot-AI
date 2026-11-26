"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge, Card, Empty, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { inr, when } from "@/services/api";
import type { Order, Page } from "@/types";

export default function OrdersPage() {
  const { data, loading } = useApi<Page<Order>>("/api/v1/orders?size=50");
  return (
    <AppShell roles={["CUSTOMER"]}>
      <PageHeader title="Order history" subtitle={data ? `${data.total} orders` : undefined} />
      <Card>
        {loading ? <Spinner /> : !data?.items.length ? <Empty title="No orders yet." action={{ href: "/products", label: "Start shopping" }} /> : (
          <Table head={["Order", "Placed", "Items", "Total", "Payment", "Status"]}>
            {data.items.map((o) => (
              <tr key={o.id} className="hover:bg-ink-100/50">
                <Td><Link href={`/orders/${o.id}`} className="font-medium text-brand-700 hover:underline">{o.order_number}</Link></Td>
                <Td>{when(o.created_at)}</Td>
                <Td>{o.items.map((i) => i.product_name).join(", ")}</Td>
                <Td>{inr(o.total)}</Td>
                <Td>{o.payment_status ? <Badge>{o.payment_status}</Badge> : "—"}</Td>
                <Td><Badge>{o.status}</Badge></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </AppShell>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Button, Card, Empty, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, inr } from "@/services/api";
import type { Cart } from "@/types";

export default function CartPage() {
  const { data: cart, loading, error, setData } = useApi<Cart>("/api/v1/cart");
  const [coupon, setCoupon] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<Cart>) {
    setErr(null);
    try { setData(await fn()); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <AppShell roles={["CUSTOMER"]}>
      <PageHeader title="Shopping cart" />
      <ErrorNote message={error ?? err} />
      {loading ? <Spinner /> : !cart?.items.length ? <Empty title="Your cart is empty." action={{ href: "/products", label: "Browse products" }} /> : (
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          <Card>
            <ul className="divide-y divide-ink-100">
              {cart.items.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-4 py-4">
                  <div className="flex-1">
                    <Link href={`/products/${i.product_id}`} className="font-medium hover:text-brand-700">{i.product_name}</Link>
                    <p className="text-xs text-ink-500">{[i.colour, i.size && `size ${i.size}`, i.sku].filter(Boolean).join(" · ")}</p>
                  </div>
                  <select value={i.quantity} aria-label="Quantity" className="rounded-lg border border-ink-300 px-2 py-1 text-sm"
                          onChange={(e) => run(() => api<Cart>(`/api/v1/cart/items/${i.id}`, { method: "PUT", json: { quantity: Number(e.target.value) } }))}>
                    {Array.from({ length: 10 }, (_, n) => n + 1).map((n) => <option key={n}>{n}</option>)}
                  </select>
                  <span className="w-24 text-right font-medium">{inr(i.line_total)}</span>
                  <Button variant="ghost" onClick={() => run(() => api<Cart>(`/api/v1/cart/items/${i.id}`, { method: "DELETE" }))}>Remove</Button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Summary">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt>Subtotal</dt><dd>{inr(cart.subtotal)}</dd></div>
              <div className="flex justify-between"><dt>Discount</dt><dd>-{inr(cart.discount)}</dd></div>
              <div className="flex justify-between"><dt>Shipping</dt><dd>{Number(cart.shipping) ? inr(cart.shipping) : "Free"}</dd></div>
              <div className="flex justify-between text-ink-500"><dt>GST included</dt><dd>{inr(cart.tax)}</dd></div>
              <div className="flex justify-between border-t border-ink-100 pt-2 text-base font-semibold"><dt>Total</dt><dd>{inr(cart.total)}</dd></div>
            </dl>
            <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(() => api<Cart>(`/api/v1/cart/coupon?code=${encodeURIComponent(coupon)}`, { method: "POST" })); }}>
              <input value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Coupon (WELCOME10)" className="flex-1 rounded-lg border border-ink-300 px-3 py-2 text-sm" />
              <Button variant="outline" type="submit">Apply</Button>
            </form>
            {cart.coupon_error && <p className="mt-2 text-xs text-rose-600">{cart.coupon_error}</p>}
            <Link href="/checkout" className="mt-4 block rounded-lg bg-brand-600 py-2.5 text-center text-sm font-medium text-white hover:bg-brand-700">Proceed to checkout</Link>
          </Card>
        </div>
      )}
    </AppShell>
  );
}

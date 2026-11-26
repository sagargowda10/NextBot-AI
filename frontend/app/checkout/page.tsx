"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AddressForm, formatAddress } from "@/components/AddressForm";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, inr } from "@/services/api";
import type { Address, Cart, Order } from "@/types";

const METHODS = [
  ["mock_upi", "UPI (simulated)"], ["mock_card", "Card (simulated)"], ["mock_fail", "Simulate a declined payment"],
];

export default function CheckoutPage() {
  const router = useRouter();
  const cart = useApi<Cart>("/api/v1/cart");
  const addresses = useApi<Address[]>("/api/v1/auth/me/addresses");
  const [addressId, setAddressId] = useState<number | null>(null);
  const [method, setMethod] = useState("mock_upi");
  const [showAddForm, setShowAddForm] = useState(false);
  const selectedId = addressId ?? addresses.data?.find((a) => a.is_default)?.id ?? addresses.data?.[0]?.id;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function placeOrder() {
    setBusy(true);
    setError(null);
    try {
      const key = `web-${crypto.randomUUID()}`;  // idempotency: double-clicks can't double-charge
      const order = await api<Order>("/api/v1/orders", { method: "POST", json: {
        address_id: selectedId, coupon_code: cart.data?.coupon_code, payment_method: method, idempotency_key: key } });
      router.push(`/orders/${order.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Checkout failed");
    } finally {
      setBusy(false);
    }
  }

  if (cart.loading || addresses.loading) return <AppShell roles={["CUSTOMER"]}><Spinner /></AppShell>;
  return (
    <AppShell roles={["CUSTOMER"]}>
      <PageHeader title="Checkout" subtitle="Stock is reserved for 30 minutes once the order is created" action={<Badge tone="amber">Mock payment gateway</Badge>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card title="Delivery address" action={addresses.data?.length ? (
            <button type="button" onClick={() => setShowAddForm((v) => !v)} className="text-sm font-medium text-brand-600 hover:underline">
              {showAddForm ? "Cancel" : "+ Add new address"}
            </button>) : undefined}>
            {!!addresses.data?.length && (
              <div className="space-y-2">
                {addresses.data.map((a) => (
                  <label key={a.id} className="flex cursor-pointer gap-3 rounded-lg border border-ink-300 p-3 text-sm has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50">
                    <input type="radio" name="addr" checked={selectedId === a.id} onChange={() => setAddressId(a.id)} />
                    <span><b>{a.label}</b>{a.is_default && <span className="ml-2 text-xs text-emerald-600">default</span>} — {formatAddress(a)}<br />
                      <span className="text-xs text-ink-500">📞 {a.phone}</span></span>
                  </label>
                ))}
              </div>
            )}
            {(!addresses.data?.length || showAddForm) && (
              <div className={addresses.data?.length ? "mt-4 border-t border-ink-100 pt-4" : ""}>
                {!addresses.data?.length && <p className="mb-3 text-sm text-ink-500">Add a delivery address to place your order.</p>}
                <AddressForm onSaved={async (a) => { setShowAddForm(false); await addresses.reload(); setAddressId(a.id); }}
                             onCancel={addresses.data?.length ? () => setShowAddForm(false) : undefined} />
              </div>
            )}
          </Card>
          <Card title="Payment method">
            <div className="space-y-2">
              {METHODS.map(([v, label]) => (
                <label key={v} className="flex items-center gap-3 text-sm">
                  <input type="radio" name="pay" checked={method === v} onChange={() => setMethod(v)} /> {label}
                </label>
              ))}
            </div>
            <p className="mt-3 text-xs text-ink-500">Card details are never stored by NextBot. Real gateways (Razorpay/Stripe) use hosted checkout.</p>
          </Card>
        </div>
        <Card title="Order total">
          <p className="text-3xl font-semibold">{inr(cart.data?.total)}</p>
          <p className="text-xs text-ink-500">{cart.data?.items.length ?? 0} item(s), GST included</p>
          {!selectedId && <p className="mt-2 text-xs text-amber-700">Add a delivery address to continue.</p>}
          <ErrorNote message={error} />
          <Button className="mt-4 w-full" onClick={placeOrder} disabled={busy || !cart.data?.items.length || !selectedId}>{busy ? "Placing order…" : "Place order & pay"}</Button>
        </Card>
      </div>
    </AppShell>
  );
}

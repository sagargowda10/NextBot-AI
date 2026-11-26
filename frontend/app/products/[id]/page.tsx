"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, inr } from "@/services/api";
import type { ProductDetail } from "@/types";

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: p, loading, error } = useApi<ProductDetail>(`/api/v1/products/${id}`);
  const [variantId, setVariantId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [msg, setMsg] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<string | null>(null);

  useEffect(() => { if (p) setVariantId(p.variants.find((v) => v.stock_available > 0)?.id ?? null); }, [p]);
  const selected = p?.variants.find((v) => v.id === variantId);

  async function add() {
    if (!variantId) return;
    try {
      await api("/api/v1/cart/items", { method: "POST", json: { variant_id: variantId, quantity: qty } });
      setMsg("Added to cart ✓");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    }
  }

  async function checkDelivery() {
    const r = await api<{ reply: string }>("/api/v1/ai/chat", { method: "POST", json: { message: "How long will delivery take to my address?" } });
    setEstimate(r.reply);
  }

  if (loading) return <AppShell><Spinner /></AppShell>;
  if (!p) return <AppShell><ErrorNote message={error ?? "Not found"} /></AppShell>;
  return (
    <AppShell>
      <PageHeader title={p.name} subtitle={`${p.brand} · ${p.category} · ⭐ ${p.rating} (${p.review_count} reviews)`} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={p.images[0]} alt={p.name} className="mx-auto h-72 object-contain" />
        </Card>
        <div className="space-y-4">
          <Card>
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-semibold">{inr(selected?.price ?? p.price)}</span>
              {p.discount_percent > 0 && <><span className="text-ink-500 line-through">{inr(p.mrp)}</span><Badge tone="green">{p.discount_percent}% off</Badge></>}
            </div>
            <p className="mt-3 text-sm text-ink-700">{p.description}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {p.variants.map((v) => (
                <button key={v.id} disabled={v.stock_available === 0} onClick={() => setVariantId(v.id)}
                        className={`rounded-lg border px-3 py-1.5 text-sm ${v.id === variantId ? "border-brand-600 bg-brand-50" : "border-ink-300"} disabled:opacity-40`}>
                  {[v.colour, v.size && `Size ${v.size}`].filter(Boolean).join(" · ") || v.sku} {v.stock_available <= 5 && v.stock_available > 0 ? `(only ${v.stock_available})` : ""}
                </button>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-3">
              <input type="number" min={1} max={10} value={qty} onChange={(e) => setQty(Math.max(1, Math.min(10, Number(e.target.value))))}
                     className="w-20 rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Quantity" />
              <Button onClick={add} disabled={!variantId}>Add to cart</Button>
              <Button variant="outline" onClick={checkDelivery}>Check delivery</Button>
            </div>
            {msg && <p className="mt-2 text-sm text-ink-500">{msg}</p>}
            {estimate && <p className="mt-2 rounded-lg bg-brand-50 p-3 text-sm text-brand-900">{estimate}</p>}
          </Card>
          <Card title="Specifications">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {Object.entries(p.specifications).map(([k, v]) => <div key={k} className="contents"><dt className="text-ink-500">{k}</dt><dd>{v}</dd></div>)}
            </dl>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

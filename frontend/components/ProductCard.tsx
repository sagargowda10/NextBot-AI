"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button } from "@/components/ui";
import { api, inr } from "@/services/api";
import type { Cart, Product } from "@/types";

export function ProductCard({ product, compact = false, onAdded }: { product: Product; compact?: boolean; onAdded?: (c: Cart) => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const variant = product.variants.find((v) => v.stock_available > 0);

  async function add() {
    if (!variant) return;
    setBusy(true);
    setMsg(null);
    try {
      const cart = await api<Cart>("/api/v1/cart/items", { method: "POST", json: { variant_id: variant.id, quantity: 1 } });
      setMsg("Added ✓");
      onAdded?.(cart);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-ink-100 bg-white shadow-card">
      <Link href={`/products/${product.id}`} className="grid aspect-[4/3] place-items-center bg-gradient-to-br from-brand-50 to-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={product.image_url ?? "/images/placeholder-product.svg"} alt={product.name} className="h-2/3 w-2/3 object-contain" />
      </Link>
      <div className="flex flex-1 flex-col gap-1.5 p-4">
        <p className="text-xs uppercase tracking-wide text-ink-500">{product.brand} · {product.category}</p>
        <Link href={`/products/${product.id}`} className="line-clamp-2 font-medium text-ink-900 hover:text-brand-700">{product.name}</Link>
        <div className="flex items-baseline gap-2">
          <span className="font-semibold">{inr(product.price)}</span>
          {product.discount_percent > 0 && <span className="text-xs text-ink-500 line-through">{inr(product.mrp)}</span>}
          {product.discount_percent > 0 && <span className="text-xs font-medium text-emerald-600">{product.discount_percent}% off</span>}
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-500">
          ⭐ {product.rating.toFixed(1)} {product.in_stock ? <Badge tone="green">In stock</Badge> : <Badge tone="red">Out of stock</Badge>}
        </div>
        {!compact && variant && (variant.size || variant.colour) && (
          <p className="text-xs text-ink-500">Variant: {[variant.colour, variant.size && `size ${variant.size}`].filter(Boolean).join(", ")}</p>
        )}
        <div className="mt-auto flex items-center gap-2 pt-2">
          <Button onClick={add} disabled={!variant || busy} className="w-full" aria-label={`Add ${product.name} to cart`}>
            {busy ? "Adding…" : "Add to cart"}
          </Button>
        </div>
        {msg && <p className="text-xs text-ink-500">{msg}</p>}
      </div>
    </div>
  );
}

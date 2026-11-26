"use client";

import Link from "next/link";
import { useApi } from "@/hooks/useApi";
import { inr } from "@/services/api";
import type { Page, Product } from "@/types";

/** Public, top-rated products for the landing page (catalogue reads don't need a login). */
export function FeaturedProducts() {
  const { data, loading, error } = useApi<Page<Product>>("/api/v1/products?size=8&sort=rating");
  if (error) return <p className="text-center text-sm text-rose-300">Couldn&apos;t load products: {error}</p>;
  if (loading) return <p className="text-center text-sm text-ink-300">Loading products…</p>;
  if (!data?.items.length) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {data.items.map((p) => (
        <Link key={p.id} href={`/products/${p.id}`} className="group overflow-hidden rounded-xl border border-white/10 bg-white/5 transition hover:border-brand-500 hover:bg-white/10">
          <div className="grid aspect-[4/3] place-items-center bg-white/90">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.image_url ?? "/images/placeholder-product.svg"} alt={p.name} className="h-2/3 w-2/3 object-contain" />
          </div>
          <div className="p-4">
            <p className="text-xs uppercase tracking-wide text-ink-300">{p.brand} · {p.category}</p>
            <p className="mt-1 line-clamp-2 font-medium group-hover:text-brand-100">{p.name}</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-semibold">{inr(p.price)}</span>
              {p.discount_percent > 0 && <span className="text-xs text-ink-300 line-through">{inr(p.mrp)}</span>}
              {p.discount_percent > 0 && <span className="text-xs text-emerald-400">{p.discount_percent}% off</span>}
            </div>
            <p className="mt-1 text-xs text-ink-300">⭐ {p.rating.toFixed(1)}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ProductCard } from "@/components/ProductCard";
import { Button, Empty, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import type { Page, Product } from "@/types";

const CATS = ["", "laptops", "smartphones", "audio", "footwear", "apparel", "wearables", "home-kitchen"];

export default function CataloguePage() {
  const [f, setF] = useState({ q: "", category: "", colour: "", variant_size: "", max_price: "", sort: "relevance", semantic: false });
  const [query, setQuery] = useState("");
  const { data, loading, error } = useApi<Page<Product>>(`/api/v1/products/search?size=24&${query}`, [query]);

  function apply() {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v !== "" && v !== false) p.set(k, String(v)); });
    setQuery(p.toString());
  }

  return (
    <AppShell>
      <PageHeader title="Product catalogue" subtitle={data ? `${data.total} products` : undefined} />
      <form onSubmit={(e) => { e.preventDefault(); apply(); }} className="mb-6 grid gap-3 rounded-xl border border-ink-100 bg-white p-4 shadow-card md:grid-cols-7">
        <input placeholder="Search (e.g. noise cancelling)" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} className="rounded-lg border border-ink-300 px-3 py-2 text-sm md:col-span-2" />
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Category">
          {CATS.map((c) => <option key={c} value={c}>{c || "All categories"}</option>)}
        </select>
        <input placeholder="Colour" value={f.colour} onChange={(e) => setF({ ...f, colour: e.target.value })} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" />
        <input placeholder="Size" value={f.variant_size} onChange={(e) => setF({ ...f, variant_size: e.target.value })} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" />
        <input placeholder="Max ₹" inputMode="numeric" value={f.max_price} onChange={(e) => setF({ ...f, max_price: e.target.value.replace(/\D/g, "") })} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-ink-500"><input type="checkbox" checked={f.semantic} onChange={(e) => setF({ ...f, semantic: e.target.checked })} />Semantic</label>
          <Button type="submit" className="flex-1">Search</Button>
        </div>
      </form>
      <ErrorNote message={error} />
      {loading ? <Spinner /> : !data?.items.length ? <Empty title="No products match these filters." /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.items.map((p) => <ProductCard key={p.id} product={p} />)}
        </div>
      )}
    </AppShell>
  );
}

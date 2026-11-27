"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, cx } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { inr, when } from "@/services/api";
import type { Order, Page } from "@/types";

type Status = "done" | "failed" | "review" | "pending" | "skipped";
interface WfNode { id: string; label: string; actor: string; kind: string; status: Status; at: string | null; summary: string; details: Record<string, unknown> }
interface WfEdge { source: string; target: string }
interface TimelineItem { at: string; title: string; detail: string | null; node: string }
interface N8nStatus { configured: boolean; editor_url: string | null; sent: number; failed: number; last_error: string | null }
interface Workflow {
  order: { id: number; order_number: string; status: string; total: string; created_at: string };
  nodes: WfNode[]; edges: WfEdge[]; timeline: TimelineItem[]; n8n: N8nStatus;
}

// Canvas layout (n8n-style left-to-right flow with a fan-out after the event bus)
const W = 176, H = 74, CX = 210, CY = 128, PAD = 36;
const GRID: Record<string, [number, number]> = {
  checkout: [0, 1], fraud: [1, 1], inventory: [2, 1], payment: [3, 1], events: [4, 1],
  shipping: [5, 0], email: [5, 1], whatsapp: [5, 2], n8n: [5, 3],
  courier: [6, 0], return: [7, 0], approval: [7, 1], refund: [7, 2],
};
const CANVAS_W = PAD * 2 + 7 * CX + W, CANVAS_H = PAD * 2 + 3 * CY + H;
const pos = (id: string) => { const [c, r] = GRID[id] ?? [0, 0]; return { x: PAD + c * CX, y: PAD + r * CY }; };

const COLOR: Record<Status, string> = { done: "#22c55e", failed: "#ef4444", review: "#f59e0b", pending: "#64748b", skipped: "#334155" };
const LABEL: Record<Status, string> = { done: "Success", failed: "Failed", review: "Needs review", pending: "Waiting", skipped: "Skipped" };
const ICON: Record<string, string> = { trigger: "⚡", agent: "🤖", bus: "📨", plugin: "🔌", notify: "✉️", n8n: "∞", human: "👤" };
const nodeIcon = (n: WfNode) => (n.id === "whatsapp" ? "💬" : ICON[n.kind] ?? "●");

function edgePath(a: { x: number; y: number }, b: { x: number; y: number }) {
  if (Math.abs(a.x - b.x) < 5) { // same column -> vertical link
    const x = a.x + W / 2;
    return `M ${x} ${a.y + H} C ${x} ${a.y + H + 30}, ${x} ${b.y - 30}, ${x} ${b.y}`;
  }
  const sx = a.x + W, sy = a.y + H / 2, tx = b.x, ty = b.y + H / 2, dx = Math.max(50, (tx - sx) / 2);
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
}

function Canvas({ wf, selected, onSelect }: { wf: Workflow; selected: string | null; onSelect: (id: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(1);
  const [zoom, setZoom] = useState<number | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setFit(Math.min(1, (el.clientWidth - 8) / CANVAS_W)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const scale = zoom ?? fit;
  const byId = useMemo(() => Object.fromEntries(wf.nodes.map((n) => [n.id, n])), [wf.nodes]);

  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-700 bg-[#1b1b29]">
      <style>{`@keyframes nbflow { to { stroke-dashoffset: -24; } } .nb-flow { animation: nbflow 1s linear infinite; }`}</style>
      <div className="absolute right-3 top-3 z-10 flex gap-1">
        {[["−", () => setZoom(Math.max(0.35, scale - 0.1))], ["Fit", () => setZoom(null)], ["+", () => setZoom(Math.min(1.6, scale + 0.1))]].map(([t, fn]) => (
          <button key={t as string} onClick={fn as () => void}
                  className="rounded-md border border-slate-600 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700">{t as string}</button>
        ))}
      </div>
      <div ref={box} className="overflow-auto" style={{ backgroundImage: "radial-gradient(#2e2e44 1px, transparent 1px)", backgroundSize: "20px 20px" }}>
        <div style={{ width: CANVAS_W * scale, height: CANVAS_H * scale }}>
          <div className="relative origin-top-left" style={{ width: CANVAS_W, height: CANVAS_H, transform: `scale(${scale})` }}>
            <svg width={CANVAS_W} height={CANVAS_H} className="absolute inset-0">
              <defs>
                {(Object.keys(COLOR) as Status[]).map((s) => (
                  <marker key={s} id={`arrow-${s}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={COLOR[s]} />
                  </marker>
                ))}
              </defs>
              {wf.edges.map((e) => {
                const t = byId[e.target], s = byId[e.source];
                const st: Status = !t || !s ? "pending" : s.status === "skipped" || t.status === "skipped" ? "skipped" : t.status;
                const live = st === "done" || st === "review";
                return (
                  <path key={`${e.source}-${e.target}`} d={edgePath(pos(e.source), pos(e.target))} fill="none" stroke={COLOR[st]}
                        strokeWidth={live ? 2.5 : 1.5} strokeDasharray={live ? "8 4" : "4 6"} opacity={st === "skipped" ? 0.45 : 1}
                        className={live ? "nb-flow" : undefined} markerEnd={`url(#arrow-${st})`} />
                );
              })}
            </svg>
            {wf.nodes.map((n) => {
              const p = pos(n.id);
              return (
                <button key={n.id} onClick={() => onSelect(n.id)} title={n.summary}
                        className={cx("absolute flex items-center gap-3 rounded-xl border-2 bg-[#2a2a3d] px-3 text-left shadow-lg transition hover:brightness-125",
                          selected === n.id && "ring-2 ring-white/70", n.status === "skipped" && "opacity-50")}
                        style={{ left: p.x, top: p.y, width: W, height: H, borderColor: COLOR[n.status], boxShadow: n.status === "done" ? "0 0 14px rgba(34,197,94,.25)" : undefined }}>
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#1b1b29] text-xl" aria-hidden>{nodeIcon(n)}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-slate-100">{n.label}</span>
                    <span className="block truncate text-[11px] text-slate-400">{n.actor}</span>
                    <span className="block truncate text-[11px]" style={{ color: COLOR[n.status] }}>{LABEL[n.status]}</span>
                  </span>
                  <span className="absolute -right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-[#1b1b29]" style={{ background: COLOR[n.status] }} />
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-4 border-t border-slate-700 px-4 py-2 text-xs text-slate-300">
        {(Object.keys(COLOR) as Status[]).map((s) => (
          <span key={s} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLOR[s] }} />{LABEL[s]}</span>
        ))}
        <span className="ml-auto text-slate-500">Click a node for details</span>
      </div>
    </div>
  );
}

function Detail({ node }: { node: WfNode | undefined }) {
  if (!node) return <p className="text-sm text-ink-500">Select a node on the canvas.</p>;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-2xl">{nodeIcon(node)}</span>
        <div>
          <p className="font-semibold text-ink-900">{node.label}</p>
          <p className="text-xs text-ink-500">{node.actor}</p>
        </div>
        <span className="ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium text-white" style={{ background: COLOR[node.status] }}>{LABEL[node.status]}</span>
      </div>
      <p className="text-ink-700">{node.summary || "—"}</p>
      <p className="text-xs text-ink-500">{when(node.at)}</p>
      {Object.keys(node.details).length > 0 && (
        <dl className="space-y-2 rounded-lg bg-ink-100 p-3 text-xs">
          {Object.entries(node.details).map(([k, v]) => (
            <div key={k}>
              <dt className="font-medium uppercase tracking-wide text-ink-500">{k.replaceAll("_", " ")}</dt>
              <dd className="mt-0.5 break-words text-ink-900">
                {Array.isArray(v)
                  ? <ul className="list-disc pl-4">{v.map((x, i) => <li key={i}>{typeof x === "object" ? Object.entries(x as object).map(([a, b]) => `${a}: ${b ?? "—"}`).join(" · ") : String(x)}</li>)}</ul>
                  : String(v ?? "—")}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function WorkflowsInner() {
  const params = useSearchParams();
  const orders = useApi<Page<Order>>("/api/v1/admin/orders?size=50");
  const [orderId, setOrderId] = useState<number | null>(params.get("order") ? Number(params.get("order")) : null);
  const [auto, setAuto] = useState(true);
  const [selected, setSelected] = useState<string | null>("checkout");
  useEffect(() => { if (orderId == null && orders.data?.items.length) setOrderId(orders.data.items[0].id); }, [orders.data, orderId]);
  const wf = useApi<Workflow>(orderId ? `/api/v1/admin/orders/${orderId}/workflow` : null, [orderId]);
  const { reload } = wf;
  useEffect(() => {
    if (!auto || !orderId) return;
    const t = setInterval(() => { void reload(); }, 5000);
    return () => clearInterval(t);
  }, [auto, orderId, reload]);
  const node = wf.data?.nodes.find((n) => n.id === selected);
  const n8n = wf.data?.n8n;

  return (
    <AppShell roles={["ADMIN", "SUPPORT_AGENT", "INVENTORY_MANAGER"]}>
      <PageHeader title="Order workflows" subtitle="n8n-style execution view: every node is filled in from real order, payment, event, courier and notification records"
                  action={n8n?.editor_url ? <a href={n8n.editor_url} target="_blank" rel="noreferrer"><Button variant="outline">Open n8n editor ↗</Button></a> : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={orderId ?? ""} onChange={(e) => { setOrderId(Number(e.target.value)); setSelected("checkout"); }}
                className="min-w-[18rem] rounded-lg border border-ink-300 bg-white px-3 py-2 text-sm" aria-label="Order">
          {orders.data?.items.map((o) => <option key={o.id} value={o.id}>{o.order_number} · {o.status.replaceAll("_", " ")} · {inr(o.total)}</option>)}
        </select>
        <Button variant="outline" onClick={() => void reload()}>Refresh</Button>
        <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Live (every 5 s)</label>
        {n8n && (
          <span className="ml-auto flex items-center gap-2 text-sm">
            <Badge tone={n8n.configured ? (n8n.failed && !n8n.sent ? "red" : "green") : "gray"}>n8n {n8n.configured ? "connected" : "not configured"}</Badge>
            {n8n.configured && <span className="text-xs text-ink-500">{n8n.sent} sent · {n8n.failed} failed</span>}
          </span>
        )}
      </div>
      {n8n?.last_error && <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">Last n8n delivery problem: {n8n.last_error}</p>}
      <ErrorNote message={orders.error ?? wf.error} />
      {!wf.data ? (orders.data && !orders.data.items.length ? <Card><p className="text-sm text-ink-500">No orders yet.</p></Card> : <Spinner />) : (
        <>
          <p className="mb-2 text-sm text-ink-700">
            <b>{wf.data.order.order_number}</b> · {wf.data.order.status.replaceAll("_", " ")} · {inr(wf.data.order.total)} · placed {when(wf.data.order.created_at)}
          </p>
          <Canvas wf={wf.data} selected={selected} onSelect={setSelected} />
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card title="Node details"><Detail node={node} /></Card>
            <Card title="Execution log">
              <ol className="max-h-96 space-y-2 overflow-auto pr-1">
                {wf.data.timeline.map((t, i) => {
                  const st = wf.data!.nodes.find((n) => n.id === t.node)?.status ?? "pending";
                  return (
                    <li key={i}>
                      <button onClick={() => setSelected(t.node)} className={cx("flex w-full gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-ink-100", selected === t.node && "bg-brand-50")}>
                        <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: COLOR[st] }} />
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium text-ink-900">{t.title}</span>
                          {t.detail && <span className="block truncate text-xs text-ink-500">{t.detail}</span>}
                        </span>
                        <span className="shrink-0 text-xs text-ink-500">{when(t.at)}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </Card>
          </div>
        </>
      )}
    </AppShell>
  );
}

export default function WorkflowsPage() {
  return <Suspense fallback={<Spinner />}><WorkflowsInner /></Suspense>;
}

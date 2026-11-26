"use client";

import { useEffect, useRef, useState } from "react";
import { ProductCard } from "@/components/ProductCard";
import { Badge, Button, cx } from "@/components/ui";
import { api } from "@/services/api";
import type { ChatResponse, Conversation } from "@/types";

interface Msg { role: "user" | "assistant"; content: string; res?: ChatResponse; error?: boolean }

const SUGGESTED = [
  "Find me a laptop under ₹60,000.", "Show me black running shoes in size 9.", "Recommend a smartphone based on my budget.",
  "Add the first product to my cart.", "Place my order.", "Track my latest order.", "What is your return policy?",
  "I want to return my order.",
];
const STAFF = ["Show products with low inventory.", "Show me this month's sales.", "Show me the status of all plugins.", "Show me recent AI agent executions."];

export function ChatPanel({ staff = false }: { staff?: boolean }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [history, setHistory] = useState<Conversation[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => { api<Conversation[]>("/api/v1/ai/conversations").then(setHistory).catch(() => undefined); }, [conversationId]);

  async function openConversation(id: number) {
    const c = await api<Conversation>(`/api/v1/ai/conversations/${id}`);
    setConversationId(id);
    setMessages((c.messages ?? []).map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content })));
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setBusy(true);
    try {
      const res = await api<ChatResponse>("/api/v1/ai/chat", { method: "POST", json: { message, conversation_id: conversationId } });
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply, res }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: e instanceof Error ? e.message : "Something went wrong.", error: true }]);
    } finally {
      setBusy(false);
    }
  }

  const last = [...messages].reverse().find((m) => m.res)?.res;
  const prompts = staff ? [...STAFF, ...SUGGESTED.slice(0, 2)] : SUGGESTED;

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="hidden flex-col gap-2 lg:flex">
        <Button variant="outline" onClick={() => { setConversationId(null); setMessages([]); }}>+ New chat</Button>
        <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-ink-500">History</p>
        {history.map((c) => (
          <button key={c.id} onClick={() => openConversation(c.id)}
                  className={cx("truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-white", c.id === conversationId && "bg-white shadow-card")}>
            {c.title}
          </button>
        ))}
      </aside>
      <div className="flex h-[calc(100vh-10rem)] flex-col rounded-xl border border-ink-100 bg-white shadow-card">
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3">
          <div>
            <p className="font-semibold">NextBot Assistant</p>
            <p className="text-xs text-ink-500">Supervisor + 11 specialised agents</p>
          </div>
          {last && <Badge tone={last.demo_mode ? "amber" : "green"}>{last.demo_mode ? `Demo mode · ${last.ai_provider} AI` : `Live · ${last.ai_provider}`}</Badge>}
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5" aria-live="polite">
          {messages.length === 0 && (
            <div className="mx-auto max-w-xl text-center">
              <p className="text-lg font-semibold">How can I help you shop today?</p>
              <p className="mt-1 text-sm text-ink-500">Try one of these:</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {prompts.map((p) => <button key={p} onClick={() => send(p)} className="rounded-full border border-ink-300 px-3 py-1.5 text-sm hover:border-brand-500 hover:text-brand-700">{p}</button>)}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cx("max-w-[85%] space-y-3", m.role === "user" && "text-right")}>
                <div className={cx("inline-block whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-left text-sm",
                  m.role === "user" ? "bg-brand-600 text-white" : m.error ? "bg-rose-50 text-rose-700" : "bg-ink-100 text-ink-900")}>
                  {m.content.replace(/\*\*(.+?)\*\*/g, "$1")}
                </div>
                {m.res && m.res.products.length > 0 && (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {m.res.products.slice(0, 6).map((p) => <ProductCard key={p.id} product={p} compact />)}
                  </div>
                )}
                {m.res && m.res.sources.length > 0 && (
                  <div className="text-xs text-ink-500">Sources: {m.res.sources.map((s, n) => <span key={s.id} className="mr-2">[{n + 1}] {s.title}</span>)}</div>
                )}
                {m.res && m.res.agents.length > 0 && (
                  <details className="text-xs text-ink-500">
                    <summary className="cursor-pointer select-none">Agents: {m.res.agents.map((a) => a.agent).join(" → ")} · intent {m.res.intent}</summary>
                    <ul className="mt-2 space-y-1">
                      {m.res.agents.map((a, n) => (
                        <li key={n} className="flex flex-wrap items-center gap-2">
                          <Badge tone={a.success ? "green" : "red"}>{a.agent}</Badge>
                          <span>{a.duration_ms.toFixed(0)} ms</span>
                          {a.tools.map((t) => <code key={t} className="rounded bg-ink-100 px-1">{t}</code>)}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {m.res?.requires_approval && <Badge tone="amber">Awaiting human approval</Badge>}
                {m.res && m.res.suggestions.length > 0 && i === messages.length - 1 && (
                  <div className="flex flex-wrap gap-2">
                    {m.res.suggestions.map((s) => <button key={s} onClick={() => send(s)} className="rounded-full bg-brand-50 px-3 py-1 text-xs text-brand-700 hover:bg-brand-100">{s}</button>)}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="flex items-center gap-2 text-sm text-ink-500"><span className="h-2 w-2 animate-bounce rounded-full bg-brand-500" />Agents are working…</div>}
          <div ref={endRef} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); void send(input); }} className="flex gap-2 border-t border-ink-100 p-4">
          <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} placeholder="Ask NextBot anything about products, orders, returns…"
                 aria-label="Message" className="flex-1 rounded-lg border border-ink-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-500" />
          <Button type="submit" disabled={busy || !input.trim()}>Send</Button>
        </form>
      </div>
    </div>
  );
}

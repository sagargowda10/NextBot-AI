"use client";

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, cx } from "@/components/ui";
import { ListenButton, MicButton, SpeakToggle } from "@/components/VoiceControls";
import { useApi } from "@/hooks/useApi";
import { useSpeech, useSpeechInput } from "@/hooks/useVoice";
import { api } from "@/services/api";

interface Link { url: string; title: string }
interface Answer {
  answer: string; citations: Link[]; sources: Link[]; web_used: boolean; store_used: boolean;
  provider: string; model: string; notice: string | null; remaining_today: number;
}
interface Turn { q: string; a?: Answer; error?: string; at: string }
interface Status { provider: string; model: string | null; daily_limit: number; per_minute: number }

const STORE_KEY = "nb_research_history";
const EXAMPLES = [
  "How are our sales in the last 30 days, and which products sell best?",
  "What is the current GST rate on laptops and smartphones in India?",
  "Compare Razorpay and Stripe fees for an Indian e-commerce store.",
  "Which items are low on stock and what should I reorder first?",
  "What are the latest consumer protection rules for e-commerce returns in India?",
];

/** Tiny, safe Markdown subset: **bold**, [text](url), bare URLs, "- " bullets, [n] citation markers. No HTML injection. */
function inline(text: string, cites: Link[]): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)]+)|\[(\d+)\]/g;
  let last = 0, m: RegExpExecArray | null, k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(<strong key={k++}>{m[1]}</strong>);
    else if (m[2]) out.push(<a key={k++} href={m[3]} target="_blank" rel="noreferrer" className="text-brand-600 underline">{m[2]}</a>);
    else if (m[4]) out.push(<a key={k++} href={m[4]} target="_blank" rel="noreferrer" className="break-all text-brand-600 underline">{m[4]}</a>);
    else if (m[5]) {
      const c = cites[Number(m[5]) - 1];
      out.push(c ? <a key={k++} href={c.url} target="_blank" rel="noreferrer" className="align-super text-[10px] text-brand-600">[{m[5]}]</a> : `[${m[5]}]`);
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Markdown({ text, cites }: { text: string; cites: Link[] }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) blocks.push(<ul key={blocks.length} className="list-disc space-y-1.5 pl-5">{bullets.map((b, i) => <li key={i}>{inline(b, cites)}</li>)}</ul>);
    bullets = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const b = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
    if (b) { bullets.push(b[1]); continue; }
    flush();
    if (line.trim()) {
      const h = line.match(/^#{1,4}\s+(.*)$/);
      blocks.push(h ? <p key={blocks.length} className="font-semibold text-ink-900">{inline(h[1], cites)}</p> : <p key={blocks.length}>{inline(line, cites)}</p>);
    }
  }
  flush();
  return <div className="space-y-2 text-sm leading-relaxed text-ink-900">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>;
}

function Sources({ a }: { a: Answer }) {
  const cited = new Set(a.citations.map((c) => c.url));
  const more = a.sources.filter((s) => !cited.has(s.url));
  if (!a.citations.length && !more.length) return null;
  const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
  return (
    <div className="mt-3 border-t border-ink-100 pt-3 text-xs">
      {a.citations.length > 0 && (
        <>
          <p className="mb-1 font-semibold uppercase tracking-wide text-ink-500">Sources</p>
          <ol className="space-y-1">
            {a.citations.map((c, i) => (
              <li key={c.url}><a href={c.url} target="_blank" rel="noreferrer" className="text-brand-600 hover:underline">[{i + 1}] {c.title}</a> <span className="text-ink-500">· {host(c.url)}</span></li>
            ))}
          </ol>
        </>
      )}
      {more.length > 0 && (
        <details className="mt-2 text-ink-500">
          <summary className="cursor-pointer select-none">{more.length} more page(s) consulted</summary>
          <ul className="mt-1 space-y-0.5">{more.slice(0, 20).map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">{host(s.url)}</a></li>)}</ul>
        </details>
      )}
    </div>
  );
}

export default function ResearchPage() {
  const status = useApi<Status>("/api/v1/admin/research/status");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [useWeb, setUseWeb] = useState(true);
  const [store, setStore] = useState<"auto" | "always" | "never">("auto");
  const endRef = useRef<HTMLDivElement>(null);
  const voice = useSpeech("nb_research_speak");
  const mic = useSpeechInput((text) => { void ask(text); });

  useEffect(() => { try { const s = localStorage.getItem(STORE_KEY); if (s) setTurns(JSON.parse(s) as Turn[]); } catch { /* ignore */ } }, []);
  useEffect(() => { try { localStorage.setItem(STORE_KEY, JSON.stringify(turns.slice(-30))); } catch { /* ignore */ } }, [turns]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, busy]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    const history = turns.slice(-3).flatMap((t) => (t.a ? [{ role: "user", content: t.q }, { role: "assistant", content: t.a.answer }] : []));
    setTurns((t) => [...t, { q, at: new Date().toISOString() }]);
    setBusy(true);
    try {
      const a = await api<Answer>("/api/v1/admin/research", { method: "POST", json: { question: q, use_web: useWeb, include_store: store, history } });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
      if (voice.auto) voice.speak(a.answer);
    } catch (e) {
      const error = e instanceof Error ? e.message : "Request failed";
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error } : x)));
    } finally {
      setBusy(false);
    }
  }

  const provider = status.data?.provider ?? "mock";
  const live = provider !== "mock";
  const providerLabel = provider === "openai" ? "ChatGPT" : provider.charAt(0).toUpperCase() + provider.slice(1);
  return (
    <AppShell roles={["ADMIN"]}>
      <div className="flex h-[calc(100vh-6rem)] flex-col rounded-xl border border-ink-100 bg-white shadow-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-ink-100 px-5 py-3">
          <div className="mr-auto">
            <p className="font-semibold">AI Research <span className="text-xs font-normal text-ink-500">· admin only</span></p>
            <p className="text-xs text-ink-500">Ask anything. Answers cite web sources, and use live store numbers for questions about the business.</p>
          </div>
          <SpeakToggle {...voice} />
          {status.data && <Badge tone={live ? "green" : "amber"}>{live ? `${providerLabel} · ${status.data.model}` : "Demo mode · no AI key"}</Badge>}
          {turns.length > 0 && <Button variant="ghost" onClick={() => setTurns([])}>Clear</Button>}
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5" aria-live="polite">
          {turns.length === 0 && (
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-lg font-semibold">What do you want to find out?</p>
              <p className="mt-1 text-sm text-ink-500">Type, paste, or tap the mic and speak.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((p) => <button key={p} onClick={() => ask(p)} className="rounded-full border border-ink-300 px-3 py-1.5 text-left text-sm hover:border-brand-500 hover:text-brand-700">{p}</button>)}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className="space-y-3">
              <div className="flex justify-end"><p className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-brand-600 px-4 py-2.5 text-sm text-white">{t.q}</p></div>
              {t.a && (
                <div className="max-w-[92%] rounded-2xl border border-ink-100 bg-ink-100/40 px-5 py-4">
                  <Markdown text={t.a.answer} cites={t.a.citations} />
                  <Sources a={t.a} />
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-500">
                    {t.a.web_used && <Badge tone="blue">🌐 Web search</Badge>}
                    {t.a.store_used && <Badge tone="green">📊 Store data</Badge>}
                    <span>{t.a.provider === "mock" ? "demo" : `${t.a.provider} · ${t.a.model}`} · {t.a.remaining_today} left today</span>
                    <ListenButton supported={voice.supported} onClick={() => voice.speak(t.a!.answer)} />
                    <button onClick={() => { void navigator.clipboard?.writeText(t.a!.answer); }} className="hover:text-brand-600">⧉ Copy</button>
                  </div>
                  {t.a.notice && <p className="mt-2 rounded-lg bg-amber-50 px-3 py-1.5 text-xs text-amber-800">{t.a.notice}</p>}
                </div>
              )}
              {t.error && <p className="max-w-[92%] rounded-2xl bg-rose-50 px-4 py-2.5 text-sm text-rose-700">{t.error}</p>}
            </div>
          ))}
          {busy && <div className="flex items-center gap-2 text-sm text-ink-500"><span className="h-2 w-2 animate-bounce rounded-full bg-brand-500" />{useWeb && provider === "openai" ? "Searching the web and writing the answer…" : "Thinking…"}</div>}
          <div ref={endRef} />
        </div>

        {(mic.listening || mic.error) && (
          <p className={cx("px-4 pt-2 text-xs", mic.error ? "text-rose-600" : "text-ink-500")}>{mic.error ?? (mic.interim ? `🎙 ${mic.interim}` : "🎙 Listening… speak now")}</p>
        )}
        <form onSubmit={(e) => { e.preventDefault(); void ask(input); }} className="space-y-2 border-t border-ink-100 p-4">
          <div className="flex gap-2">
            <MicButton supported={mic.supported} listening={mic.listening} onClick={mic.toggle} disabled={busy} />
            <textarea value={input} onChange={(e) => setInput(e.target.value)} maxLength={4000} rows={2} aria-label="Question"
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(input); } }}
                      placeholder="Paste or type any question… (Enter to send, Shift+Enter for a new line)"
                      className="flex-1 resize-none rounded-lg border border-ink-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-500" />
            <Button type="submit" disabled={busy || !input.trim()}>Ask</Button>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-ink-700">
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={useWeb} onChange={(e) => setUseWeb(e.target.checked)} /> 🌐 Search the web</label>
            <label className="flex items-center gap-1.5">📊 Store data
              <select value={store} onChange={(e) => setStore(e.target.value as "auto" | "always" | "never")} className="rounded border border-ink-300 px-1.5 py-0.5">
                <option value="auto">Auto (when the question is about the store)</option>
                <option value="always">Always include</option>
                <option value="never">Never</option>
              </select>
            </label>
            {status.data && <span className="ml-auto text-ink-500">Limits: {status.data.per_minute}/min · {status.data.daily_limit}/day</span>}
          </div>
        </form>
      </div>
    </AppShell>
  );
}

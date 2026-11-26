import Link from "next/link";
import { FeaturedProducts } from "@/components/FeaturedProducts";

const FEATURES = [
  ["Supervisor + 11 agents", "Shopping, product intelligence, inventory, orders, payments, returns, support, logistics, fraud, analytics and notifications — coordinated by a LangGraph supervisor."],
  ["12 governed plugins", "Every capability is a plugin with typed inputs, role permissions, agent allow-lists, health checks and execution tracing."],
  ["Grounded answers (RAG)", "Policy answers come from the knowledge base with citations — and the assistant says so when it doesn't know."],
  ["Model Context Protocol", "Commerce tools exposed over real MCP (Streamable HTTP + stdio) with the same permission checks as the app."],
  ["Event-driven", "Transactional outbox → Kafka with retries, dead-letter topics and idempotent consumers."],
  ["Human in the loop", "High-value refunds, large cancellations, big stock adjustments and risky orders wait for an admin."],
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-900 via-ink-900 to-ink-900 text-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <span className="flex items-center gap-2 text-lg font-semibold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-sm">NB</span>NextBot AI</span>
        <nav className="flex gap-3 text-sm">
          <Link href="/login" className="rounded-lg px-4 py-2 hover:bg-white/10">Sign in</Link>
          <Link href="/register" className="rounded-lg bg-brand-600 px-4 py-2 font-medium hover:bg-brand-700">Create account</Link>
        </nav>
      </header>
      <section className="mx-auto max-w-6xl px-6 pb-16 pt-12 text-center">
        <p className="mx-auto mb-4 inline-block rounded-full bg-white/10 px-3 py-1 text-xs">Demo mode works offline — no paid API keys needed</p>
        <h1 className="mx-auto max-w-3xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
          Shopping, orders and support — handled by a team of AI agents.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-ink-300">
          “Find me black running shoes under ₹3,000 in size 9, check stock and delivery” — NextBot routes it to the right agents,
          checks real inventory, quotes delivery, and can take you all the way to a tracked order.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link href="/assistant" className="rounded-lg bg-brand-600 px-5 py-3 font-medium hover:bg-brand-700">Try the assistant</Link>
          <Link href="/products" className="rounded-lg border border-white/20 px-5 py-3 hover:bg-white/10">Browse products</Link>
        </div>
      </section>
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="mb-4 flex items-end justify-between">
          <h2 className="text-xl font-semibold">Top-rated products</h2>
          <Link href="/products" className="text-sm text-brand-100 hover:underline">View full catalogue →</Link>
        </div>
        <FeaturedProducts />
      </section>
      <section className="mx-auto grid max-w-6xl gap-4 px-6 pb-20 md:grid-cols-3">
        {FEATURES.map(([t, d]) => (
          <div key={t} className="rounded-xl border border-white/10 bg-white/5 p-5">
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-2 text-sm text-ink-300">{d}</p>
          </div>
        ))}
      </section>
      <footer className="border-t border-white/10 py-6 text-center text-xs text-ink-500">NextBot AI · fictional demo store · Python FastAPI · Next.js</footer>
    </div>
  );
}

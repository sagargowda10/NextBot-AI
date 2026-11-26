"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Button({ variant = "primary", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "outline" }) {
  const styles = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-500/60",
    outline: "border border-ink-300 bg-white text-ink-900 hover:bg-ink-100",
    ghost: "text-ink-700 hover:bg-ink-100",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  }[variant];
  return <button {...p} className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed", styles, className)} />;
}

export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-ink-100 bg-white p-5 shadow-card", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-ink-900">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

const TONE: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  red: "bg-rose-50 text-rose-700 ring-rose-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  blue: "bg-brand-50 text-brand-700 ring-brand-600/20",
  gray: "bg-ink-100 text-ink-700 ring-ink-500/20",
};

export function statusTone(s: string): keyof typeof TONE {
  if (/(ENABLED|SUCCEEDED|DELIVERED|HEALTHY|APPROVED|EXECUTED|CONFIRMED|REFUNDED|SENT)/.test(s)) return "green";
  if (/(FAILED|CANCELLED|REJECTED|UNHEALTHY|DISABLED)/.test(s)) return "red";
  if (/(PENDING|REVIEW|RETURN|SIMULATED|INITIALIZING|mock)/.test(s)) return "amber";
  if (/(SHIPPED|PROCESSING|PACKED|OUT_FOR|CREATED)/.test(s)) return "blue";
  return "gray";
}

export function Badge({ children, tone }: { children: ReactNode; tone?: keyof typeof TONE }) {
  const t = tone ?? statusTone(String(children));
  return <span className={cx("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TONE[t])}>{children}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-ink-100 bg-white p-5 shadow-card">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-ink-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-ink-100 text-sm">
        <thead><tr>{head.map((h) => <th key={h} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-ink-500">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-ink-100">{children}</tbody>
      </table>
    </div>
  );
}

export const Td = ({ children, className }: { children: ReactNode; className?: string }) => <td className={cx("px-3 py-2.5 text-ink-700", className)}>{children}</td>;

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-8 text-sm text-ink-500"><span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />{label}</div>;
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{message}</p> : null;
}

export function Empty({ title, action }: { title: string; action?: { href: string; label: string } }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-ink-300 py-12 text-center">
      <p className="text-sm text-ink-500">{title}</p>
      {action && <Link href={action.href} className="text-sm font-medium text-brand-600 hover:underline">{action.label}</Link>}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  const { label, className, ...rest } = props;
  return (
    <label className="block text-sm">
      {label && <span className="mb-1 block font-medium text-ink-700">{label}</span>}
      <input {...rest} className={cx("w-full rounded-lg border border-ink-300 px-3 py-2 outline-none ring-brand-500 focus:ring-2", className)} />
    </label>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { cx, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";
import type { Role } from "@/types";

const NAV: { href: string; label: string; roles?: Role[] }[] = [
  { href: "/dashboard", label: "Dashboard", roles: ["CUSTOMER"] },
  { href: "/assistant", label: "AI Assistant" },
  { href: "/products", label: "Products" },
  { href: "/cart", label: "Cart", roles: ["CUSTOMER"] },
  { href: "/orders", label: "Orders", roles: ["CUSTOMER"] },
  { href: "/returns", label: "Returns", roles: ["CUSTOMER", "SUPPORT_AGENT"] },
  { href: "/addresses", label: "Addresses", roles: ["CUSTOMER"] },
  { href: "/admin", label: "Admin Overview", roles: ["ADMIN"] },
  { href: "/admin/orders", label: "All Orders", roles: ["ADMIN", "SUPPORT_AGENT", "INVENTORY_MANAGER"] },
  { href: "/admin/analytics", label: "Analytics", roles: ["ADMIN"] },
  { href: "/admin/inventory", label: "Inventory", roles: ["ADMIN", "INVENTORY_MANAGER"] },
  { href: "/admin/agents", label: "AI Agents", roles: ["ADMIN"] },
  { href: "/admin/plugins", label: "Plugins", roles: ["ADMIN"] },
  { href: "/admin/approvals", label: "Approvals", roles: ["ADMIN"] },
  { href: "/support", label: "Support Desk", roles: ["ADMIN", "SUPPORT_AGENT"] },
];

export function AppShell({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading, logout, hasRole } = useAuth();
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [loading, user, router, path]);

  if (loading || !user) return <div className="p-10"><Spinner /></div>;
  const allowed = !roles || hasRole(...roles);

  return (
    <div className="flex min-h-screen bg-ink-100/60">
      <aside className="hidden w-60 shrink-0 flex-col bg-ink-900 px-3 py-5 text-sm text-ink-300 md:flex">
        <Link href="/" className="mb-6 flex items-center gap-2 px-3 text-base font-semibold text-white">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-600 text-xs">NB</span> NextBot AI
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5">
          {NAV.filter((n) => !n.roles || hasRole(...n.roles)).map((n) => (
            <Link key={n.href} href={n.href}
                  className={cx("rounded-lg px-3 py-2 hover:bg-white/5 hover:text-white", path === n.href && "bg-white/10 text-white")}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-white/10 px-3 pt-4">
          <p className="truncate text-white">{user.full_name}</p>
          <p className="truncate text-xs">{user.roles.join(", ")}</p>
          <button onClick={() => { logout(); router.push("/login"); }} className="mt-3 text-xs text-brand-100 hover:underline">Sign out</button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="flex items-center justify-between border-b border-ink-100 bg-white px-6 py-3 md:hidden">
          <span className="font-semibold">NextBot AI</span>
          <Link href="/assistant" className="text-sm text-brand-600">Assistant</Link>
        </div>
        <div className="mx-auto max-w-7xl px-6 py-8">
          {allowed ? children : <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-800">You don&apos;t have access to this page.</p>}
        </div>
      </main>
    </div>
  );
}

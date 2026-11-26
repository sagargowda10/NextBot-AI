"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, Stat } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, when } from "@/services/api";
import type { PluginInfo } from "@/types";

export default function PluginDashboard() {
  const { data, loading, error, reload } = useApi<PluginInfo[]>("/api/v1/plugins");
  const count = (s: string) => data?.filter((p) => p.status === s).length ?? 0;
  const runs = data?.reduce((n, p) => n + p.stats.executions, 0) ?? 0;
  const fails = data?.reduce((n, p) => n + p.stats.failures, 0) ?? 0;

  async function toggle(p: PluginInfo) {
    await api(`/api/v1/plugins/${p.id}/${p.status === "ENABLED" ? "disable" : "enable"}`, { method: "POST" });
    await reload();
  }

  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title="Plugin management" subtitle="12 application-managed business plugins behind the Plugin Manager" />
      <ErrorNote message={error} />
      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <Stat label="Total" value={data?.length ?? "—"} />
        <Stat label="Enabled" value={count("ENABLED")} />
        <Stat label="Disabled" value={count("DISABLED")} />
        <Stat label="Failed" value={count("FAILED")} />
        <Stat label="Executions" value={runs} hint={`${fails} failed`} />
      </div>
      {loading ? <Spinner /> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(data ?? []).map((p) => (
            <Card key={p.id} title={<Link href={`/admin/plugins/${p.id}`} className="hover:text-brand-700">{p.name} <span className="text-xs font-normal text-ink-500">v{p.version}</span></Link>}
                  action={<Badge>{p.status}</Badge>}>
              <p className="min-h-[3rem] text-xs text-ink-500">{p.description}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <Badge>{p.health}</Badge>
                <Badge tone={p.mode === "mock" ? "amber" : "gray"}>{p.mode}</Badge>
                {p.requires_credentials && <Badge tone="gray">needs credentials for live mode</Badge>}
              </div>
              <dl className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
                <div><dt className="text-ink-500">Runs</dt><dd className="font-semibold">{p.stats.executions}</dd></div>
                <div><dt className="text-ink-500">OK</dt><dd className="font-semibold">{p.stats.successes}</dd></div>
                <div><dt className="text-ink-500">Failed</dt><dd className="font-semibold">{p.stats.failures}</dd></div>
                <div><dt className="text-ink-500">Avg ms</dt><dd className="font-semibold">{p.stats.avg_duration_ms}</dd></div>
              </dl>
              <p className="mt-2 text-[11px] text-ink-500">Last run: {when(p.stats.last_execution_at)}</p>
              <div className="mt-3 flex gap-2">
                <Button variant={p.status === "ENABLED" ? "outline" : "primary"} onClick={() => toggle(p)}>{p.status === "ENABLED" ? "Disable" : "Enable"}</Button>
                <Link href={`/admin/plugins/${p.id}`} className="rounded-lg px-4 py-2 text-sm text-brand-700 hover:bg-brand-50">Configure</Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}

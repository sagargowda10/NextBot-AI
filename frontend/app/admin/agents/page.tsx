"use client";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, PageHeader, Spinner, Stat, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { when } from "@/services/api";
import type { AgentExecution, AgentInfo } from "@/types";

export default function AgentMonitoring() {
  const agents = useApi<AgentInfo[]>("/api/v1/admin/agents");
  const execs = useApi<AgentExecution[]>("/api/v1/admin/agents/executions?limit=50");
  const total = agents.data?.reduce((n, a) => n + a.executions, 0) ?? 0;
  const failures = agents.data?.reduce((n, a) => n + a.failures, 0) ?? 0;

  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title="AI agent monitoring" subtitle="1 Supervisor + 11 specialised agents (in-process counters since start-up; history from the database)" />
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <Stat label="Agents" value={agents.data?.length ?? "—"} hint="1 supervisor + 11 specialised" />
        <Stat label="Executions" value={total} />
        <Stat label="Failures" value={failures} />
      </div>
      {agents.loading ? <Spinner /> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(agents.data ?? []).map((a) => (
            <Card key={a.name} title={<span className="flex items-center gap-2">{a.display_name}{a.is_supervisor && <Badge tone="blue">Supervisor</Badge>}</span>}
                  action={<Badge tone="green">READY</Badge>}>
              <p className="text-xs text-ink-500">{a.description}</p>
              <dl className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
                <div><dt className="text-ink-500">Runs</dt><dd className="text-base font-semibold">{a.executions}</dd></div>
                <div><dt className="text-ink-500">Success</dt><dd className="text-base font-semibold">{a.success_rate}%</dd></div>
                <div><dt className="text-ink-500">Failed</dt><dd className="text-base font-semibold">{a.failures}</dd></div>
                <div><dt className="text-ink-500">Avg ms</dt><dd className="text-base font-semibold">{a.avg_duration_ms.toFixed(0)}</dd></div>
              </dl>
              <p className="mt-3 text-[11px] text-ink-500">Limits: {a.max_iterations} tool calls · {a.timeout_s}s</p>
              <div className="mt-2 flex flex-wrap gap-1">{a.allowed_tools.map((t) => <code key={t} className="rounded bg-ink-100 px-1 text-[11px]">{t}</code>)}</div>
            </Card>
          ))}
        </div>
      )}
      <Card title="Recent executions" className="mt-6">
        <Table head={["Agent", "Intent", "Result", "Duration", "Tool calls", "When", "Error"]}>
          {(execs.data ?? []).map((e) => (
            <tr key={e.id}>
              <Td>{e.agent}</Td><Td>{e.intent}</Td><Td><Badge tone={e.success ? "green" : "red"}>{e.success ? "OK" : "FAILED"}</Badge></Td>
              <Td>{e.duration_ms.toFixed(0)} ms</Td><Td>{e.tool_calls}</Td><Td>{when(e.started_at)}</Td><Td className="text-xs text-rose-600">{e.error}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </AppShell>
  );
}

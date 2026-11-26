"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner, Table, Td } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, when } from "@/services/api";
import type { PluginExecution, PluginInfo } from "@/types";

export default function PluginConfigPage() {
  const { id } = useParams<{ id: string }>();
  const plugin = useApi<PluginInfo>(`/api/v1/plugins/${id}`);
  const [failedOnly, setFailedOnly] = useState(false);
  const execs = useApi<PluginExecution[]>(`/api/v1/plugins/${id}/executions?failed_only=${failedOnly}`, [failedOnly]);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!plugin.data) return;
    const editable = Object.fromEntries(Object.entries(plugin.data.config).filter(([, v]) => v !== "********"));
    setDraft(JSON.stringify(editable, null, 2));
  }, [plugin.data]);

  async function save() {
    setMsg(null);
    try {
      const values = JSON.parse(draft) as Record<string, unknown>;
      for (const [k, v] of Object.entries(values)) if (v === null) delete values[k];
      await api(`/api/v1/plugins/${id}/config`, { method: "PUT", json: { values } });
      setMsg("Saved ✓ (plugin re-initialised)");
      await plugin.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Invalid JSON"); }
  }

  if (plugin.loading) return <AppShell roles={["ADMIN"]}><Spinner /></AppShell>;
  const p = plugin.data;
  if (!p) return <AppShell roles={["ADMIN"]}><ErrorNote message={plugin.error} /></AppShell>;
  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title={`${p.name} v${p.version}`} subtitle={p.description} action={<div className="flex gap-2"><Badge>{p.status}</Badge><Badge>{p.health}</Badge><Badge tone="amber">{p.mode}</Badge></div>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Configuration" action={<Button onClick={save}>Save</Button>}>
          <p className="mb-2 text-xs text-ink-500">Secrets (API keys, passwords) are never shown or editable here — set them as environment variables on the server.</p>
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={12} spellCheck={false}
                    className="w-full rounded-lg border border-ink-300 p-3 font-mono text-xs" aria-label="Plugin configuration JSON" />
          {msg && <p className="mt-2 text-sm text-ink-700">{msg}</p>}
          <p className="mt-3 text-xs font-medium text-ink-500">Masked secrets</p>
          <ul className="text-xs text-ink-500">{Object.entries(p.config).filter(([, v]) => v === "********").map(([k]) => <li key={k}>{k}: ********</li>)}</ul>
        </Card>
        <Card title="Actions & permissions">
          <Table head={["Action", "Permission", "Description"]}>
            {p.actions.map((a) => <tr key={a.name}><Td className="font-mono text-xs">{a.name}</Td><Td><code className="text-xs">{a.permission}</code></Td><Td className="text-xs">{a.description}</Td></tr>)}
          </Table>
        </Card>
      </div>
      <Card title="Execution log" className="mt-6" action={<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />Failed only</label>}>
        <Table head={["When", "Action", "Agent", "User", "Result", "Duration", "Error"]}>
          {(execs.data ?? []).map((e) => (
            <tr key={e.id}>
              <Td>{when(e.started_at)}</Td><Td className="font-mono text-xs">{e.action}</Td><Td>{e.agent ?? "API"}</Td><Td>—</Td>
              <Td><Badge tone={e.success ? "green" : "red"}>{e.success ? "OK" : "FAILED"}</Badge></Td><Td>{e.duration_ms} ms</Td>
              <Td className="text-xs text-rose-600">{e.error}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </AppShell>
  );
}

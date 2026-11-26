"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, when } from "@/services/api";
import type { Approval } from "@/types";

export default function ApprovalsPage() {
  const [status, setStatus] = useState("PENDING");
  const { data, loading, error, reload } = useApi<Approval[]>(`/api/v1/admin/approvals${status ? `?status=${status}` : ""}`, [status]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  async function decide(a: Approval, approve: boolean) {
    try {
      const r = await api<Approval>(`/api/v1/admin/approvals/${a.id}/decision`, { method: "POST", json: { approve, note: notes[a.id] || null } });
      setMsg(`#${a.id} → ${r.status}`);
      await reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <AppShell roles={["ADMIN"]}>
      <PageHeader title="Human approvals" subtitle="Agents propose sensitive operations; nothing runs until an administrator approves it"
                  action={<select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-ink-300 px-3 py-2 text-sm" aria-label="Status">
                    {["PENDING", "EXECUTED", "REJECTED", "FAILED", ""].map((s) => <option key={s} value={s}>{s || "All"}</option>)}
                  </select>} />
      <ErrorNote message={error} />
      {msg && <p className="mb-4 rounded-lg bg-brand-50 px-3 py-2 text-sm">{msg}</p>}
      {loading ? <Spinner /> : !data?.length ? <Empty title="Nothing waiting for review." /> : (
        <div className="space-y-4">
          {data.map((a) => (
            <Card key={a.id} title={<span className="flex items-center gap-2">#{a.id} <Badge tone="blue">{a.action.replaceAll("_", " ")}</Badge></span>} action={<Badge>{a.status}</Badge>}>
              <p className="text-sm">{a.summary}</p>
              <p className="mt-1 text-xs text-ink-500">Requested {when(a.created_at)}{a.requested_by_agent && ` by ${a.requested_by_agent} agent`}</p>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-ink-100 p-3 text-xs">{JSON.stringify(a.result ?? a.payload, null, 2)}</pre>
              {a.status === "PENDING" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <input placeholder="Review note (optional)" value={notes[a.id] ?? ""} onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })}
                         className="flex-1 rounded-lg border border-ink-300 px-3 py-2 text-sm" />
                  <Button onClick={() => decide(a, true)}>Approve & execute</Button>
                  <Button variant="danger" onClick={() => decide(a, false)}>Reject</Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}

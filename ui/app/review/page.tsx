"use client";

import { useCallback, useEffect, useState } from "react";
import { Cites, Severity } from "@/components/Citations";
import { get, post, type Finding } from "@/lib/api";

type Item = { finding_id: string; status: string; reviewer: string | null; finding: Finding };

export default function Review() {
  const [runId, setRunId] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [reviewer, setReviewer] = useState("consultant@ledgerline");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<Finding>>({});

  const load = useCallback(async (id: string) => {
    const r = await get<{ items: Item[]; summary: Record<string, number> }>(`/engagements/${id}/review`);
    setItems(r.items);
    setSummary(r.summary);
  }, []);
  useEffect(() => {
    get<{ run_id: string; status?: string }[]>("/engagements").then((rs) => {
      const id = rs.find((r) => r.status !== "running")?.run_id;
      if (id) { setRunId(id); load(id); }
    });
  }, [load]);

  const act = async (fid: string, action: string, edits?: Partial<Finding>) => {
    await post(`/engagements/${runId}/review/${fid}`, { action, reviewer, edits, reason: action === "edit" ? "reviewer edit" : "" });
    setEditing(null);
    load(runId);
  };

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Review queue</h1>
          <p className="text-sm text-slate-500">Accept, edit or reject each finding. Every action is logged; exports apply decisions.</p>
        </div>
        <div className="text-xs">
          reviewer <input className="rounded border px-2 py-1" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          <span className="ml-3">{Object.entries(summary).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>
        </div>
      </header>
      <div className="space-y-2">
        {items.map((it) => (
          <div key={it.finding_id} className="card !p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono">{it.finding_id}</span><Severity s={it.finding.severity} />
                  <span className={`rounded px-1.5 py-0.5 ${it.status === "rejected" ? "bg-red-50 text-red-700" : it.status === "pending" ? "bg-slate-100" : "bg-emerald-50 text-emerald-700"}`}>{it.status}</span>
                  {it.reviewer && <span className="text-slate-400">by {it.reviewer}</span>}
                </div>
                {editing === it.finding_id ? (
                  <div className="mt-2 grid gap-2">
                    <input className="rounded border px-2 py-1 text-sm" defaultValue={it.finding.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                    <textarea className="rounded border px-2 py-1 text-sm" defaultValue={it.finding.recommendation} onChange={(e) => setDraft({ ...draft, recommendation: e.target.value })} />
                    <select className="w-40 rounded border px-2 py-1 text-sm" defaultValue={it.finding.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value as Finding["severity"] })}>
                      {["critical", "high", "medium", "low"].map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </div>
                ) : (
                  <>
                    <div className="mt-1 font-medium">{it.finding.title}</div>
                    <div className="text-sm text-slate-600">{it.finding.rationale}</div>
                    <div className="mt-1 text-sm"><b>Recommendation:</b> {it.finding.recommendation}</div>
                  </>
                )}
                <div className="mt-1"><Cites cites={[...it.finding.evidence_citations, ...it.finding.requirement_citations]} max={4} /></div>
              </div>
              <div className="flex shrink-0 gap-1">
                {editing === it.finding_id ? (
                  <>
                    <button className="btn" onClick={() => act(it.finding_id, "edit", draft)}>Save</button>
                    <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button className="btn-ghost" onClick={() => act(it.finding_id, "accept")}>Accept</button>
                    <button className="btn-ghost" onClick={() => { setDraft({}); setEditing(it.finding_id); }}>Edit</button>
                    <button className="btn-ghost" onClick={() => act(it.finding_id, "reject")}>Reject</button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

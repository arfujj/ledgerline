"use client";

import { useEffect, useState } from "react";
import { Cite } from "@/components/Citations";
import { get } from "@/lib/api";

type Doc = { doc_id: string; title: string; doc_type: string; publication_date: string | null; effective_date: string | null; valid_to: string | null; issuer: string };
type Lineage = { lineage_id: string; versions: Doc[]; status_today: string };
type Change = { section: string; change: string; similarity: number; diff: string[]; old_cite: string | null; new_cite: string | null };
type Diff = { old: Doc; new: Doc; counts: Record<string, number>; changes: Change[] };

export default function Regulations() {
  const [lins, setLins] = useState<Lineage[]>([]);
  const [sel, setSel] = useState<string>("occ-genius-issuer-rule");
  const [diff, setDiff] = useState<Diff | null>(null);
  const [only, setOnly] = useState(true);
  useEffect(() => { get<Lineage[]>("/regulations").then(setLins); }, []);
  useEffect(() => { setDiff(null); get<Diff>(`/regulations/${sel}/diff`).then(setDiff).catch(() => setDiff(null)); }, [sel]);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Regulation versions</h1>
      <div className="grid gap-3 md:grid-cols-2">
        {lins.filter((l) => l.versions.length > 1).map((l) => (
          <button key={l.lineage_id} onClick={() => setSel(l.lineage_id)} className={`card text-left ${sel === l.lineage_id ? "ring-2 ring-indigo-500" : ""}`}>
            <div className="font-mono text-xs text-slate-500">{l.lineage_id}</div>
            <div className="mt-1 text-sm">{l.status_today}</div>
            <ol className="mt-2 space-y-1 text-xs text-slate-600">
              {l.versions.map((v) => (
                <li key={v.doc_id}>{v.publication_date} · <b>{v.doc_type.replace("_", " ")}</b> {v.doc_id}{v.effective_date ? ` · effective ${v.effective_date}` : ""}{v.valid_to ? ` · superseded ${v.valid_to}` : ""}</li>
              ))}
            </ol>
          </button>
        ))}
      </div>
      {diff && (
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">{diff.old.doc_type.replace("_", " ")} ({diff.old.publication_date}) → {diff.new.doc_type.replace("_", " ")} ({diff.new.publication_date})</h2>
            <div className="flex items-center gap-3 text-xs">
              {Object.entries(diff.counts).map(([k, n]) => <span key={k}>{k}: <b>{n}</b></span>)}
              <label><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> changed only</label>
            </div>
          </div>
          <div className="space-y-2">
            {diff.changes.filter((c) => !only || c.change !== "unchanged").map((c) => (
              <div key={c.section} className="rounded border border-slate-200 p-2">
                <div className="flex items-center justify-between text-sm">
                  <span><b>§ {c.section}</b> · {c.change} {c.change === "modified" && <span className="text-xs text-slate-500">(similarity {c.similarity})</span>}</span>
                  <span>{c.old_cite && <Cite c={c.old_cite} />}{c.new_cite && <Cite c={c.new_cite} />}</span>
                </div>
                {c.diff.length > 0 && (
                  <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] leading-snug">
                    {c.diff.map((l, i) => <div key={i} className={l.startsWith("+") ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}>{l}</div>)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

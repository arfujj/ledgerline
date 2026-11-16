"use client";

import { useState } from "react";
import { Cites } from "@/components/Citations";
import { post } from "@/lib/api";

type Ans = {
  answer: string; insufficient: boolean; route: string; corpus: string; as_of: string | null; escalated: boolean; agent_steps: number;
  sentences: { text: string; cites: string[]; status: string; note: string }[];
  verifier: Record<string, number>; latency_ms: number; cost_usd: number;
};

const EXAMPLES = [
  "Does NovaPay's dispute procedure meet Regulation E provisional credit timing?",
  "As of June 1, 2026, which version of the OCC rule implementing the GENIUS Act governs?",
  "What share of reconciliation steps at NovaPay are manual?",
  "What changed between the OCC's proposed and final GENIUS Act rule?",
  "What is NovaPay's 2027 marketing budget?",
];

export default function Ask() {
  const [q, setQ] = useState(EXAMPLES[0]);
  const [a, setA] = useState<Ans | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => { setBusy(true); setA(null); try { setA(await post<Ans>("/ask", { question: q })); } finally { setBusy(false); } };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Ask the data room</h1>
      <div className="card space-y-2">
        <textarea className="w-full rounded border p-2 text-sm" rows={2} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex flex-wrap gap-2">
          <button className="btn" onClick={go} disabled={busy}>{busy ? "Thinking…" : "Ask"}</button>
          {EXAMPLES.map((x) => <button key={x} className="btn-ghost" onClick={() => setQ(x)}>{x.slice(0, 48)}…</button>)}
        </div>
      </div>
      {a && (
        <div className="card space-y-3">
          <div className="text-xs text-slate-500">
            route <b>{a.route}</b> · corpus {a.corpus}{a.as_of ? ` · as of ${a.as_of}` : ""} · {a.escalated ? `escalated (${a.agent_steps} tool calls)` : "cheap path"} · {Math.round(a.latency_ms)} ms · ${a.cost_usd.toFixed(5)}
          </div>
          {a.insufficient && a.sentences.filter((s) => s.status === "supported").length === 0 ? (
            <p className="text-sm font-medium text-amber-700">{a.answer}</p>
          ) : (
            <p className="text-sm leading-relaxed">
              {a.sentences.filter((s) => s.status === "supported").map((s, i) => <span key={i}>{s.text} <Cites cites={s.cites} max={3} /> </span>)}
            </p>
          )}
          {a.sentences.some((s) => s.status !== "supported") && (
            <div className="rounded bg-red-50 p-2 text-xs text-red-800">
              Verifier removed: {a.sentences.filter((s) => s.status !== "supported").map((s) => `"${s.text.slice(0, 80)}" (${s.status})`).join("; ")}
            </div>
          )}
          <div className="text-xs text-slate-400">Verifier: {Object.entries(a.verifier).map(([k, v]) => `${k}=${v}`).join(" · ")} · Not legal advice.</div>
        </div>
      )}
    </div>
  );
}

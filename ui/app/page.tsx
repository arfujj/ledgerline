"use client";

import Link from "next/link";
import { useState } from "react";
import { Cites, Severity } from "@/components/Citations";
import { useLatestRun } from "@/components/useRun";
import { API, post, usd } from "@/lib/api";

export default function Overview() {
  const { run, runs, reload, error } = useLatestRun();
  const [starting, setStarting] = useState(false);
  const [exported, setExported] = useState<Record<string, Record<string, string>> | null>(null);

  const start = async () => {
    setStarting(true);
    const r = await post<{ run_id: string }>("/engagements");
    window.location.href = `/trace?run=${r.run_id}`;
  };

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">NovaPay · AI Readiness &amp; Compliance Engagement</h1>
          <p className="text-sm text-slate-500">
            Payments, a planned USD stablecoin (NovaUSD) and AI agents in support and disputes.
          </p>
        </div>
        <button className="btn" disabled={starting} onClick={start}>
          {starting ? "Starting…" : "Run new engagement"}
        </button>
      </header>
      {error && <p className="card text-sm text-red-600">API unreachable: {error}</p>}
      {!run && !error && <p className="card text-sm">No completed engagement yet. Start one above.</p>}
      {run && (
        <>
          <section className="grid grid-cols-2 gap-4 md:grid-cols-5">
            {[
              ["Compliance gaps", run.gaps.length],
              ["Inefficiencies", run.inefficiencies.length],
              ["Opportunities", run.opportunities.length],
              ["Run cost", `$${(run.cost_usd ?? 0).toFixed(4)}`],
              ["Latency", `${run.latency_s}s`],
            ].map(([k, v]) => (
              <div key={String(k)} className="card">
                <div className="text-xs uppercase tracking-wide text-slate-500">{k}</div>
                <div className="mt-1 text-2xl font-semibold">{v}</div>
              </div>
            ))}
          </section>
          <section className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Executive memo (verified draft)</h2>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                run {run.run_id} · {run.model} via {run.provider}
                <button
                  className="btn-ghost"
                  onClick={async () => setExported(await post(`/engagements/${run.run_id}/export`))}
                >
                  Export DOCX / PDF / MD
                </button>
              </div>
            </div>
            {exported && (
              <div className="mb-3 flex flex-wrap gap-3 text-xs">
                {Object.entries(exported).map(([name, fmts]) => (
                  <span key={name}>
                    {name}:{" "}
                    {Object.entries(fmts).map(([f, href]) => (
                      <a key={f} className="mr-1 text-indigo-700 underline" href={`${API}${href}`}>
                        {f}
                      </a>
                    ))}
                  </span>
                ))}
              </div>
            )}
            {run.memo.map((sec) => (
              <div key={sec.title} className="mb-4">
                <h3 className="mb-1 text-sm font-semibold text-slate-700">
                  {sec.title}{" "}
                  <span className="text-xs font-normal text-slate-400">
                    {sec.verifier.supported}/{sec.verifier.claims} claims verified
                  </span>
                </h3>
                <p className="text-sm leading-relaxed">
                  {sec.sentences
                    .filter((s) => s.status === "supported")
                    .map((s, i) => (
                      <span key={i}>
                        {s.text} <Cites cites={s.cites} max={2} />{" "}
                      </span>
                    ))}
                </p>
              </div>
            ))}
            <p className="text-xs text-slate-400">{run.disclaimer}</p>
          </section>
          <section className="card">
            <h2 className="mb-3 font-semibold">Highest-severity findings</h2>
            <table className="grid-table">
              <tbody>
                {[...run.gaps.filter((g) => g.confidence >= 0.6), ...run.inefficiencies, ...run.security]
                  .sort((a, b) => ["critical", "high", "medium", "low"].indexOf(a.severity) - ["critical", "high", "medium", "low"].indexOf(b.severity))
                  .slice(0, 8)
                  .map((f) => (
                    <tr key={f.finding_id}>
                      <td className="w-24 font-mono text-xs">{f.finding_id}</td>
                      <td className="w-20"><Severity s={f.severity} /></td>
                      <td>{f.title}</td>
                      <td className="w-72"><Cites cites={[...f.evidence_citations, ...f.requirement_citations]} max={2} /></td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <Link href="/gaps" className="mt-3 inline-block text-sm text-indigo-700 underline">Full register →</Link>
          </section>
          <section className="card">
            <h2 className="mb-3 font-semibold">90-day roadmap</h2>
            <table className="grid-table">
              <thead><tr><th>Window</th><th>Track</th><th>Action</th><th>Owner</th><th>Value</th></tr></thead>
              <tbody>
                {run.roadmap.map((r, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap">{r.window}</td>
                    <td className="whitespace-nowrap text-xs">{r.track.replace("_", " ")}</td>
                    <td>{r.action} <Cites cites={r.citations} max={2} /></td>
                    <td className="text-xs">{r.owner}</td>
                    <td className="whitespace-nowrap text-xs">{r.value ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <p className="text-xs text-slate-400">
            Runs: {runs.map((r) => r.run_id).join(", ")} ·{" "}
            <button className="underline" onClick={reload}>refresh</button> · Opportunity value example:{" "}
            {run.opportunities[0] && usd(run.opportunities[0].npv_usd)} NPV
          </p>
        </>
      )}
    </div>
  );
}

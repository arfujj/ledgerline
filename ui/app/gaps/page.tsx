"use client";

import { useState } from "react";
import { Cites, Severity } from "@/components/Citations";
import { useLatestRun } from "@/components/useRun";

export default function Gaps() {
  const { run } = useLatestRun();
  const [cat, setCat] = useState<string>("all");
  const [minConf, setMinConf] = useState(0.6);
  if (!run) return <p className="card text-sm">Loading…</p>;
  const all = [...run.gaps, ...run.inefficiencies, ...run.security].filter(
    (f) => (cat === "all" || f.category === cat) && (f.confidence ?? 1) >= minConf,
  );
  const order = ["critical", "high", "medium", "low"];
  all.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Gap &amp; findings register</h1>
          <p className="text-sm text-slate-500">Click any citation to open the source passage and page image.</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {["all", "compliance_gap", "inefficiency", "security"].map((c) => (
            <button key={c} className={c === cat ? "btn" : "btn-ghost"} onClick={() => setCat(c)}>{c.replace("_", " ")}</button>
          ))}
          <label className="ml-2">min confidence
            <select className="ml-1 rounded border px-1" value={minConf} onChange={(e) => setMinConf(Number(e.target.value))}>
              {[0, 0.5, 0.6, 0.8].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        </div>
      </header>
      <div className="card !p-0">
        <table className="grid-table">
          <thead><tr><th>ID</th><th>Severity</th><th>Finding</th><th>Evidence</th><th>Requirement</th><th>Recommendation</th><th>Owner</th></tr></thead>
          <tbody>{all.map((f) => (
            <tr key={f.finding_id}>
              <td className="font-mono text-xs">{f.finding_id}</td>
              <td><Severity s={f.severity} /></td>
              <td className="max-w-md"><div className="font-medium">{f.title}</div><div className="text-xs text-slate-500">{f.rationale}</div></td>
              <td className="w-56"><Cites cites={f.evidence_citations} max={3} /></td>
              <td className="w-48"><Cites cites={f.requirement_citations} max={2} /></td>
              <td className="max-w-xs text-xs">{f.recommendation}</td>
              <td className="text-xs">{f.owner || "-"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

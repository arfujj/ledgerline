"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get } from "@/lib/api";

type Evals = {
  retrieval_summary?: Record<string, { n: number; "recall@10": number; mrr: number; "ndcg@10": number; latency_ms: { p50: number; p95: number } }>;
  temporal?: Record<string, { n: number; temporal_correctness: number }>;
  answer_key?: Record<string, { findings: number; precision: number; recall: number; severity_within_one: number; missed: string[] }>;
  guardrails?: { detection_recall: number; false_positives: string[]; clean_docs: number };
  qa_summary?: Record<string, Record<string, number>>;
};

export default function EvalsPage() {
  const [e, setE] = useState<Evals | null>(null);
  useEffect(() => { get<Evals>("/evals").then(setE); }, []);
  if (!e) return <p className="card text-sm">Loading…</p>;
  const rs = Object.entries(e.retrieval_summary ?? {}).map(([k, v]) => ({ name: k, recall: v["recall@10"], mrr: v.mrr, ndcg: v["ndcg@10"] }));
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Eval dashboard</h1>
      <p className="text-sm text-slate-500">All numbers are read from evals/results/*.json produced by running the eval harness.</p>
      <div className="card" style={{ height: 340 }}>
        <h2 className="mb-2 font-semibold">Retrieval ablation</h2>
        <ResponsiveContainer>
          <BarChart data={rs}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" fontSize={10} /><YAxis domain={[0, 1]} /><Tooltip /><Legend />
            <Bar dataKey="recall" fill="#4f46e5" isAnimationActive={false} /><Bar dataKey="mrr" fill="#f59e0b" isAnimationActive={false} /><Bar dataKey="ndcg" fill="#10b981" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <h2 className="mb-2 font-semibold">Answer-key scoring</h2>
          <table className="grid-table"><thead><tr><th>Run</th><th>Precision</th><th>Recall</th><th>Sev ±1</th><th>Missed</th></tr></thead>
            <tbody>{Object.entries(e.answer_key ?? {}).map(([k, v]) => (
              <tr key={k}><td className="text-xs">{k}</td><td>{v.precision}</td><td>{v.recall}</td><td>{v.severity_within_one}</td><td className="text-xs">{v.missed.join(", ") || "-"}</td></tr>
            ))}</tbody></table>
        </div>
        <div className="card">
          <h2 className="mb-2 font-semibold">Temporal &amp; guardrails</h2>
          <table className="grid-table"><tbody>
            {Object.entries(e.temporal ?? {}).map(([k, v]) => <tr key={k}><td>{k}</td><td>temporal correctness {v.temporal_correctness} (n={v.n})</td></tr>)}
            {e.guardrails && <tr><td>injection detection</td><td>recall {e.guardrails.detection_recall} · false positives {e.guardrails.false_positives.length}/{e.guardrails.clean_docs}</td></tr>}
          </tbody></table>
        </div>
      </div>
      {e.qa_summary && (
        <div className="card">
          <h2 className="mb-2 font-semibold">Q&amp;A by question type</h2>
          <table className="grid-table"><thead><tr><th>Type</th>{Object.keys(Object.values(e.qa_summary)[0] ?? {}).map((k) => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>{Object.entries(e.qa_summary).map(([t, m]) => <tr key={t}><td>{t}</td>{Object.values(m).map((v, i) => <td key={i}>{typeof v === "number" ? v.toFixed(3) : String(v)}</td>)}</tr>)}</tbody></table>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, Controls, ReactFlow, MarkerType, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { get } from "@/lib/api";

type PNode = { id: string; events: number; manual_share: number; median_wait_h: number | null };
type PEdge = { source: string; target: string; frequency: number; median_h: number };
type PView = {
  engine: string;
  nodes: PNode[];
  edges: PEdge[];
  query_ids: string[];
  variants: { variant: string; cases: number; share: number; median_h: number }[];
  bottlenecks: { activity: string; median_wait_h: number; distinct_resources: number; manual_share: number }[];
  cycle_time: { cases: number; p50_h: number; p90_h: number };
};

export default function ProcessPage() {
  const [proc, setProc] = useState("kyc");
  const [v, setV] = useState<PView | null>(null);
  useEffect(() => { setV(null); get<PView>(`/process/${proc}`).then(setV); }, [proc]);

  const { nodes, edges } = useMemo(() => {
    if (!v) return { nodes: [] as Node[], edges: [] as Edge[] };
    // Left-to-right layered layout: DFS from start nodes to drop back edges (rework loops),
    // then rank = longest path from a start node over the remaining DAG.
    const out = new Map<string, PEdge[]>();
    v.edges.forEach((e) => out.set(e.source, [...(out.get(e.source) ?? []), e]));
    const targets = new Set(v.edges.map((e) => e.target));
    const starts = v.nodes.filter((n) => !targets.has(n.id)).map((n) => n.id);
    const state = new Map<string, number>();
    const back = new Set<string>();
    const dfs = (n: string) => {
      state.set(n, 1);
      for (const e of (out.get(n) ?? []).sort((a, b) => b.frequency - a.frequency)) {
        const s2 = state.get(e.target);
        if (s2 === 1) back.add(`${e.source}>${e.target}`);
        else if (!s2) dfs(e.target);
      }
      state.set(n, 2);
    };
    (starts.length ? starts : [v.nodes[0].id]).forEach(dfs);
    v.nodes.forEach((n) => !state.has(n.id) && dfs(n.id));
    const rank = new Map<string, number>();
    const fwd = v.edges.filter((e) => !back.has(`${e.source}>${e.target}`) && e.source !== e.target);
    v.nodes.forEach((n) => rank.set(n.id, 0));
    for (let it = 0; it < v.nodes.length; it++)
      fwd.forEach((e) => rank.set(e.target, Math.max(rank.get(e.target)!, rank.get(e.source)! + 1)));
    const cols = new Map<number, string[]>();
    v.nodes.forEach((n) => cols.set(rank.get(n.id)!, [...(cols.get(rank.get(n.id)!) ?? []), n.id]));
    const pos = new Map<string, { x: number; y: number }>();
    cols.forEach((ids, r) => ids.forEach((id, k) => pos.set(id, { x: (k - (ids.length - 1) / 2) * 250, y: r * 105 })));
    const maxW = Math.max(...v.nodes.map((n) => n.median_wait_h ?? 0), 1);
    const maxF = Math.max(...v.edges.map((e) => e.frequency), 1);
    return {
      nodes: v.nodes.map((nn, i) => {
        const id = nn.id;
        const n = v.nodes.find((x) => x.id === id)!;
        const heat = (n.median_wait_h ?? 0) / maxW;
        return {
          id,
          position: pos.get(id) ?? { x: 0, y: i * 120 },
          data: {
            label: (
              <div className="text-left text-[11px]">
                <div className="font-semibold">{id}</div>
                <div>{n.events.toLocaleString()} events · {(n.manual_share * 100).toFixed(0)}% manual</div>
                <div>wait p50 {n.median_wait_h ?? 0}h</div>
              </div>
            ),
          },
          sourcePosition: "bottom",
          targetPosition: "top",
          style: { width: 210, borderRadius: 10, border: "1px solid #cbd5e1", background: `rgba(239,68,68,${0.08 + heat * 0.6})` },
        } as Node;
      }),
      edges: v.edges.map((e, i) => ({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        animated: back.has(`${e.source}>${e.target}`),
        label: e.frequency / maxF > 0.15 ? `${e.frequency.toLocaleString()} · ${e.median_h}h` : undefined,
        labelStyle: { fontSize: 9 },
        style: { strokeWidth: 1 + (5 * e.frequency) / maxF, stroke: back.has(`${e.source}>${e.target}`) ? "#dc2626" : "#64748b" },
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    };
  }, [v]);

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Process maps</h1>
          <p className="text-sm text-slate-500">Mined from ~219K events. Red nodes = long waits (bottlenecks); edge width = frequency; animated red edges = rework loops.</p>
        </div>
        <div className="flex gap-2">
          {["kyc", "disputes", "recon"].map((p) => (
            <button key={p} className={p === proc ? "btn" : "btn-ghost"} onClick={() => setProc(p)}>{p}</button>
          ))}
        </div>
      </header>
      {!v && <p className="card text-sm">Mining…</p>}
      {v && (
        <>
          <div className="card !p-0" style={{ height: 760 }}>
            <ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.05 }} proOptions={{ hideAttribution: true }}>
              <Background />
              <Controls />
            </ReactFlow>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="card">
              <h2 className="mb-2 font-semibold">Bottlenecks</h2>
              <table className="grid-table">
                <thead><tr><th>Activity</th><th>Median wait</th><th>People</th><th>Manual</th></tr></thead>
                <tbody>{v.bottlenecks.map((b) => (
                  <tr key={b.activity}><td>{b.activity}</td><td>{b.median_wait_h}h</td><td>{b.distinct_resources}</td><td>{(b.manual_share * 100).toFixed(0)}%</td></tr>
                ))}</tbody>
              </table>
              <p className="mt-2 text-xs text-slate-500">Cycle time p50 {v.cycle_time.p50_h}h · p90 {v.cycle_time.p90_h}h over {v.cycle_time.cases.toLocaleString()} cases · engine {v.engine}</p>
            </div>
            <div className="card">
              <h2 className="mb-2 font-semibold">Top variants</h2>
              <table className="grid-table">
                <thead><tr><th>Share</th><th>Cases</th><th>p50</th><th>Path</th></tr></thead>
                <tbody>{v.variants.map((x, i) => (
                  <tr key={i}><td>{(x.share * 100).toFixed(1)}%</td><td>{x.cases}</td><td>{x.median_h}h</td><td className="text-[11px] text-slate-600">{x.variant}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

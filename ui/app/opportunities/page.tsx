"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Label, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Cites } from "@/components/Citations";
import { get, usd, type Opportunity } from "@/lib/api";

type Resp = { base: Opportunity[]; scenarios: Record<string, Opportunity[]> };
const COLORS: Record<string, string> = { quick_win: "#059669", strategic_bet: "#4f46e5", fill_in: "#d97706", deprioritize: "#94a3b8" };

export default function Opportunities() {
  const [d, setD] = useState<Resp | null>(null);
  useEffect(() => { get<Resp>("/opportunities").then(setD); }, []);
  if (!d) return <p className="card text-sm">Loading…</p>;
  const npv = (sc: string, id: string) => d.scenarios[sc]?.find((o) => o.id === id)?.npv_usd ?? 0;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Opportunity matrix</h1>
      <p className="text-sm text-slate-500">Value vs effort (relative 0-10). Hours come from mined event logs; costs and rates are explicit assumptions.</p>
      <div className="card" style={{ height: 420 }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 20, right: 30, bottom: 30, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="effort_score" domain={[0, 10]}><Label value="Effort →" position="bottom" /></XAxis>
            <YAxis type="number" dataKey="value_score" domain={[0, 10]}><Label value="Value →" angle={-90} position="left" /></YAxis>
            <ZAxis type="number" dataKey="annual_value_usd" range={[120, 900]} />
            <Tooltip content={({ payload }) => {
              const o = payload?.[0]?.payload as Opportunity | undefined;
              return o ? <div className="rounded border bg-white p-2 text-xs shadow"><b>{o.title}</b><br />{o.priority} · NPV {usd(o.npv_usd)}</div> : null;
            }} />
            {Object.keys(COLORS).map((p) => (
              <Scatter key={p} name={p} data={d.base.filter((o) => o.priority === p)} fill={COLORS[p]} isAnimationActive={false} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
        <div className="flex gap-4 text-xs">{Object.entries(COLORS).map(([k, c]) => <span key={k}><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: c }} />{k.replace("_", " ")}</span>)}</div>
      </div>
      <div className="card">
        <table className="grid-table">
          <thead><tr><th>Opportunity</th><th>Priority</th><th>Hours/yr</th><th>Value/yr</th><th>Impl.</th><th>NPV low / base / high</th><th>Payback</th><th>Sources</th></tr></thead>
          <tbody>{d.base.map((o) => (
            <tr key={o.id}>
              <td><div className="font-medium">{o.title}</div><div className="font-mono text-[10px] text-slate-400">{o.id}</div></td>
              <td><span className="whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] text-white" style={{ background: COLORS[o.priority] }}>{o.priority.replace("_", " ")}</span></td>
              <td>{o.annual_hours_saved.toLocaleString()}</td>
              <td>{usd(o.annual_value_usd)}</td>
              <td>{usd(o.implementation_cost_usd)}</td>
              <td className="whitespace-nowrap text-xs">{usd(npv("low", o.id))} / <b>{usd(o.npv_usd)}</b> / {usd(npv("high", o.id))}</td>
              <td>{o.payback_months ? `${o.payback_months} mo` : "n/a"}</td>
              <td className="w-64"><Cites cites={o.citations} max={3} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

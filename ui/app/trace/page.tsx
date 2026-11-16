"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Cites } from "@/components/Citations";
import { API, get } from "@/lib/api";

type Ev = { kind: string; stage: string | null; name: string; ts: string; model: string | null; cost_usd: number; latency_ms: number; input_tokens: number; output_tokens: number; cached: boolean; payload: Record<string, unknown> };

const STAGES = ["discovery", "process_analysis", "opportunity_sizing", "gap_analysis", "synthesis"];

function Trace() {
  const params = useSearchParams();
  const [runId, setRunId] = useState<string>(params.get("run") ?? "");
  const [events, setEvents] = useState<Ev[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (runId) return;
    get<{ run_id: string }[]>("/engagements").then((r) => r[0] && setRunId(r[0].run_id));
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    setDone(false);
    const es = new EventSource(`${API}/engagements/${runId}/events`);
    const onAny = (e: MessageEvent) => setEvents((xs) => [...xs, JSON.parse(e.data)]);
    for (const k of ["stage", "tool_call", "llm_call", "route", "verify"]) es.addEventListener(k, onAny);
    es.addEventListener("done", () => { setDone(true); es.close(); });
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId]);

  const byStage = useMemo(() => {
    const m: Record<string, Ev[]> = {};
    for (const e of events) (m[e.stage ?? "other"] ??= []).push(e);
    return m;
  }, [events]);
  const cost = events.reduce((a, e) => a + (e.cost_usd || 0), 0);
  const tokens = events.reduce((a, e) => a + e.input_tokens + e.output_tokens, 0);

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Live agent trace</h1>
          <p className="text-sm text-slate-500">Stage → tool calls → evidence, streamed over SSE from the audit log.</p>
        </div>
        <div className="text-right text-xs text-slate-500">
          run <span className="font-mono">{runId}</span> · {events.length} events · {tokens.toLocaleString()} tokens · ${cost.toFixed(4)}
          {done ? " · complete" : " · streaming…"}
        </div>
      </header>
      <div className="grid gap-4 lg:grid-cols-5">
        {STAGES.map((s) => (
          <div key={s} className="card !p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold capitalize">{s.replace("_", " ")}</h2>
              <span className={`h-2 w-2 rounded-full ${byStage[s]?.some((e) => e.name === "stage_end") ? "bg-emerald-500" : byStage[s] ? "bg-amber-400" : "bg-slate-200"}`} />
            </div>
            <ol className="space-y-1.5 text-xs">
              {(byStage[s] ?? []).filter((e) => !(e.kind === "stage" && e.name === "tool_call")).map((e, i) => (
                <li key={i} className="rounded border border-slate-100 bg-slate-50 p-1.5">
                  <div className="flex justify-between gap-2">
                    <span className="font-medium">{e.kind === "llm_call" ? `LLM · ${e.name}` : e.kind === "tool_call" ? `tool · ${e.name}` : e.name}</span>
                    <span className="text-slate-400">{Math.round(e.latency_ms)}ms</span>
                  </div>
                  {e.kind === "llm_call" && (
                    <div className="text-slate-500">{e.model} · {e.input_tokens}+{e.output_tokens} tok · ${e.cost_usd.toFixed(5)}{e.cached ? " · cached" : ""}</div>
                  )}
                  {Array.isArray(e.payload.cites) && <div className="mt-0.5"><Cites cites={e.payload.cites as string[]} max={3} /></div>}
                  {e.name === "section_verified" && (
                    <div className="text-emerald-700">{String(e.payload.section)}: {String(e.payload.supported)}/{String(e.payload.claims)} verified</div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Trace />
    </Suspense>
  );
}

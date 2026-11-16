"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { API, get } from "@/lib/api";

type Source = {
  doc_id: string;
  title: string;
  issuer: string;
  locator: string;
  page: number | null;
  trusted: boolean;
  source_url?: string | null;
  passages: { chunk_id: string; section: string; clause: string | null; page: number | null; text: string }[];
  page_image: string | null;
};

const Ctx = createContext<(cite: string) => void>(() => {});

export function CitationProvider({ children }: { children: ReactNode }) {
  const [cite, setCite] = useState<string | null>(null);
  const [src, setSrc] = useState<Source | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const open = async (c: string) => {
    setCite(c);
    setSrc(null);
    setErr(null);
    const m = c.match(/^\[doc:([^#\]]+)#([^\]]+)\]$/);
    if (!m) return;
    try {
      setSrc(await get<Source>(`/documents/${encodeURIComponent(m[1])}?locator=${encodeURIComponent(m[2])}`));
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <Ctx.Provider value={open}>
      {children}
      {cite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-6" onClick={() => setCite(null)}>
          <div className="max-h-[90vh] w-full max-w-5xl overflow-auto rounded-xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between gap-4">
              <div>
                <div className="font-mono text-xs text-indigo-700">{cite}</div>
                <h3 className="text-lg font-semibold">{src?.title ?? describe(cite)}</h3>
                {src && <div className="text-xs text-slate-500">{src.issuer}{!src.trusted && " · quarantined (untrusted)"}</div>}
              </div>
              <button className="btn-ghost" onClick={() => setCite(null)}>Close</button>
            </div>
            {err && <p className="text-sm text-red-600">{err}</p>}
            {!cite.startsWith("[doc:") && <p className="text-sm text-slate-600">{describe(cite)}</p>}
            {src && (
              <div className={`grid gap-4 ${src.page_image ? "md:grid-cols-2" : ""}`}>
                <div className="space-y-3">
                  {src.passages.map((p) => (
                    <div key={p.chunk_id} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <div className="mb-1 text-xs font-semibold text-amber-900">
                        {p.clause ? `§ ${p.clause}` : p.section} {p.page ? `· page ${p.page}` : ""}
                      </div>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{p.text}</p>
                    </div>
                  ))}
                  {src.source_url && (
                    <a className="text-xs text-indigo-700 underline" href={src.source_url} target="_blank" rel="noreferrer">
                      Original source
                    </a>
                  )}
                </div>
                {src.page_image && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`${API}${src.page_image}`} alt={`Page ${src.page}`} className="w-full rounded border" />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

function describe(c: string): string {
  if (c.startsWith("[q:")) return `Data query ${c.slice(3, -1)} over NovaPay event logs (re-runnable; see audit log).`;
  if (c.startsWith("[a:")) return `ROI model assumption ${c.slice(3, -1)} (config/roi_assumptions.yaml).`;
  if (c === "[calc]") return "Deterministic calculation.";
  return c;
}

export function Cite({ c }: { c: string }) {
  const open = useContext(Ctx);
  const label = c.startsWith("[doc:") ? c.slice(5, -1).replace("#", " · ") : c.slice(1, -1);
  return (
    <span className="cite" title={c} onClick={() => open(c)}>
      {label.length > 34 ? label.slice(0, 34) + "…" : label}
    </span>
  );
}

export function Cites({ cites, max = 4 }: { cites: string[]; max?: number }) {
  return (
    <>
      {cites.slice(0, max).map((c) => (
        <Cite key={c} c={c} />
      ))}
      {cites.length > max && <span className="text-[10px] text-slate-400"> +{cites.length - max}</span>}
    </>
  );
}

export function Severity({ s }: { s: string }) {
  const cls: Record<string, string> = {
    critical: "bg-red-600 text-white",
    high: "bg-orange-100 text-orange-800",
    medium: "bg-amber-50 text-amber-800",
    low: "bg-slate-100 text-slate-600",
  };
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase ${cls[s] ?? ""}`}>{s}</span>;
}

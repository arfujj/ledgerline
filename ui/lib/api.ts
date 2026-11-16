export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export type Finding = {
  finding_id: string;
  category: "compliance_gap" | "inefficiency" | "security";
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  status: string;
  evidence_citations: string[];
  requirement_citations: string[];
  rationale: string;
  recommendation: string;
  owner: string;
  confidence: number;
};

export type Sentence = { text: string; cites: string[]; status: string; note: string };
export type Section = { title: string; sentences: Sentence[]; verifier: Record<string, number> };

export type Opportunity = {
  id: string;
  title: string;
  process: string;
  priority: string;
  annual_hours_saved: number;
  annual_value_usd: number;
  implementation_cost_usd: number;
  npv_usd: number;
  payback_months: number | null;
  time_to_value_months: number;
  value_score: number;
  effort_score: number;
  citations: string[];
};

export type Engagement = {
  run_id: string;
  status?: string;
  cost_usd?: number;
  latency_s?: number;
  model?: string;
  provider?: string;
  gaps: Finding[];
  inefficiencies: Finding[];
  security: Finding[];
  opportunities: Opportunity[];
  memo: Section[];
  roadmap: { window: string; track: string; action: string; owner: string; ref: string; citations: string[]; value?: string }[];
  business_map?: { section: Section; inventory: Record<string, number>; documents: number };
  stage_timings?: Record<string, number>;
  disclaimer?: string;
};

export const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

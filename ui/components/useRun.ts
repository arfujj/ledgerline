"use client";

import { useEffect, useState } from "react";
import { get, type Engagement } from "@/lib/api";

export function useLatestRun(): { run: Engagement | null; runs: { run_id: string; status?: string }[]; reload: () => void; error: string | null } {
  const [runs, setRuns] = useState<{ run_id: string; status?: string }[]>([]);
  const [run, setRun] = useState<Engagement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    get<{ run_id: string; status?: string }[]>("/engagements")
      .then(async (rs) => {
        setRuns(rs);
        const done = rs.find((r) => r.status !== "running");
        if (done) setRun(await get<Engagement>(`/engagements/${done.run_id}`));
      })
      .catch((e) => setError(String(e)));
  }, [n]);
  return { run, runs, reload: () => setN((x) => x + 1), error };
}

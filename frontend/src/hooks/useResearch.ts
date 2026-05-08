"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type { ResearchStatus, ResearchResult } from "@/lib/types";
import { getResearchStatus, getResearchResults } from "@/lib/api";

type Phase = "idle" | "polling" | "complete" | "error";

export function useResearch(researchId: string | null) {
  const [status, setStatus] = useState<ResearchStatus | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(
    async (id: string) => {
      try {
        const s = await getResearchStatus(id);
        setStatus(s);

        if (s.status === "complete") {
          stopPolling();
          try {
            const res = await getResearchResults(id);
            setResult(res);
          } catch (e) {
            console.error("Failed to fetch research results:", e);
          }
          setPhase("complete");
        } else if (s.status === "error") {
          stopPolling();
          setError(s.error ?? "Research failed");
          setPhase("error");
        }
      } catch (err) {
        console.error("Status poll error:", err);
      }
    },
    [stopPolling]
  );

  useEffect(() => {
    if (!researchId) {
      setPhase("idle");
      setStatus(null);
      setResult(null);
      setError(null);
      stopPolling();
      return;
    }

    setPhase("polling");
    fetchStatus(researchId);
    intervalRef.current = setInterval(() => fetchStatus(researchId), 3000);

    return () => stopPolling();
  }, [researchId, fetchStatus, stopPolling]);

  return { status, result, phase, error };
}

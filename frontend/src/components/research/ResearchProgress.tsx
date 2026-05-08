"use client";

import {
  Loader2,
  Search,
  Brain,
  BookOpen,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchStatus } from "@/lib/types";

const PHASE_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; color: string }
> = {
  queued: { label: "Queued...", icon: Loader2, color: "text-text-muted" },
  planning: { label: "Planning tasks...", icon: Brain, color: "text-purple-400" },
  researching: { label: "Searching & gathering sources...", icon: Search, color: "text-blue-400" },
  synthesizing: { label: "Synthesizing report...", icon: BookOpen, color: "text-accent-light" },
  complete: { label: "Complete", icon: CheckCircle2, color: "text-green-400" },
  error: { label: "Error", icon: XCircle, color: "text-red-400" },
};

export default function ResearchProgress({ status }: { status: ResearchStatus }) {
  const cfg = PHASE_CONFIG[status.status] ?? PHASE_CONFIG.queued;
  const Icon = cfg.icon;
  const isActive = !["complete", "error"].includes(status.status);
  const pct = status.progress?.percentage ?? 0;
  const completed = status.progress?.completed_tasks ?? 0;
  const total = status.progress?.total_tasks ?? 0;

  return (
    <div className="rounded-xl border border-border bg-bg-card p-4 space-y-3 animate-fade-in">
      <div className="flex items-center gap-2.5">
        <Icon
          className={cn(
            "w-4 h-4 shrink-0",
            cfg.color,
            isActive && "animate-spin-slow"
          )}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-text-primary truncate">
            {status.topic ?? "Researching..."}
          </p>
          <p className={cn("text-xs mt-0.5", cfg.color)}>{cfg.label}</p>
        </div>
        <span className="text-xs text-text-muted font-mono shrink-0">
          {Math.round(pct)}%
        </span>
      </div>

      <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            status.status === "error" ? "bg-red-500" : "bg-accent"
          )}
          style={{ width: `${Math.max(4, pct)}%` }}
        />
      </div>

      {total > 0 && (
        <p className="text-xs text-text-muted">
          {completed} / {total} tasks completed
        </p>
      )}

      {status.status === "error" && status.error && (
        <p className="text-xs text-red-400 bg-red-950/30 rounded-lg px-3 py-2">
          {status.error}
        </p>
      )}
    </div>
  );
}

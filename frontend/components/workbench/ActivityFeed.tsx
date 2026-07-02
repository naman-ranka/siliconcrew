"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  RotateCcw,
  Search,
  User,
  X,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { selectActivity, useStore } from "@/lib/store";
import { openArtifact } from "@/lib/openArtifact";
import { commandForTool, runCommand } from "@/lib/commands";
import {
  filterActivity,
  toolKind,
  type ActivityActorFilter,
  type ActivityKindFilter,
} from "@/lib/activityFilters";
import { relativeTime } from "./runStatus";
import { Skeleton } from "@/components/ui/skeleton";
import type { ActivityEvent } from "@/types";

const KIND_PILLS: { id: ActivityKindFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "lint", label: "Lint" },
  { id: "sim", label: "Sim" },
  { id: "synth", label: "Synth" },
  { id: "writes", label: "Writes" },
];

const ACTOR_LABEL: Record<ActivityActorFilter, string> = {
  both: "Both",
  agent: "Agent",
  you: "You",
};
const ACTOR_NEXT: Record<ActivityActorFilter, ActivityActorFilter> = {
  both: "agent",
  agent: "you",
  you: "both",
};

/** 890ms / 1.4s / 2m 10s */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

function StatusMark({ status }: { status: ActivityEvent["status"] }) {
  if (status === "ok") return <Check className="h-3.5 w-3.5 shrink-0 text-status-pass" />;
  if (status === "error") return <X className="h-3.5 w-3.5 shrink-0 text-status-fail" />;
  return <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-status-running" />;
}

/**
 * The unified Activity feed (BottomDock "Activity" tab): every tool invocation
 * — agent, user (⌘K), MCP — newest-first, filterable, with expandable detail
 * and per-event actions (open artifact / re-run).
 */
export function ActivityFeed() {
  const currentSession = useStore((s) => s.currentSession);
  const events = useStore(selectActivity);
  const runs = useStore((s) => s.runs);
  const lintResult = useStore((s) => s.lintResult);
  const activityStatus = useStore((s) => s.activity.status);
  const nextBefore = useStore((s) => s.activity.nextBefore);
  const loadActivity = useStore((s) => s.loadActivity);
  const sid = currentSession?.id ?? null;

  const [kind, setKind] = useState<ActivityKindFilter>("all");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [actor, setActor] = useState<ActivityActorFilter>("both");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loadingMore, setLoadingMore] = useState(false);

  const filtered = useMemo(
    () => filterActivity(events, { kind, errorsOnly, actor, query }),
    [events, kind, errorsOnly, actor, query]
  );

  // Pill counts share the actor/query context; the Errors pill counts errors
  // within the current kind.
  const counts = useMemo(() => {
    const base = filterActivity(events, { kind: "all", errorsOnly, actor, query });
    const byKind: Record<ActivityKindFilter, number> = {
      all: base.length,
      lint: 0,
      sim: 0,
      synth: 0,
      writes: 0,
    };
    for (const e of base) {
      const k = toolKind(e.tool);
      if (k !== "other") byKind[k] += 1;
    }
    const errors = filterActivity(events, { kind, errorsOnly: false, actor, query }).filter(
      (e) => e.status === "error"
    ).length;
    return { byKind, errors };
  }, [events, kind, errorsOnly, actor, query]);

  // Only the MOST RECENT lint event owns the structured lintResult (the store
  // keeps just the latest lint's diagnostics).
  const latestLintId = useMemo(
    () => events.find((e) => e.tool === "linter_tool")?.id ?? null,
    [events]
  );

  const artifactKeyForRunId = (runId: string): string => {
    const run = runs.find((r) => r.id === runId);
    const isSim = run ? run.kind === "sim" : runId.startsWith("sim");
    return isSim ? `wave:${runId}` : `report:${runId}`;
  };

  const toggle = (id: string) => setExpanded((s) => ({ ...s, [id]: !s[id] }));

  const showSkeleton = activityStatus === "loading" && events.length === 0;

  return (
    <div className="flex flex-col">
      {/* Filter header */}
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-border px-2">
        {KIND_PILLS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setKind(p.id)}
            aria-pressed={kind === p.id}
            className={cn(
              "rounded-full border px-1.5 py-px text-[10px] outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              kind === p.id
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-surface-2"
            )}
          >
            {p.label}
            <span className="ml-1 opacity-70">{counts.byKind[p.id]}</span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => setErrorsOnly((v) => !v)}
          aria-pressed={errorsOnly}
          className={cn(
            "rounded-full border px-1.5 py-px text-[10px] outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            errorsOnly
              ? "border-status-fail/50 bg-status-fail/10 text-status-fail"
              : "border-border text-muted-foreground hover:bg-status-fail/10 hover:text-status-fail"
          )}
        >
          Errors
          <span className="ml-1 opacity-70">{counts.errors}</span>
        </button>
        <button
          type="button"
          onClick={() => setActor((a) => ACTOR_NEXT[a])}
          title={`Actor filter: ${ACTOR_LABEL[actor]} (click to cycle)`}
          className={cn(
            "flex items-center gap-1 rounded-full border px-1.5 py-px text-[10px] outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            actor === "both"
              ? "border-border text-muted-foreground hover:bg-surface-2"
              : "border-primary/50 bg-primary/10 text-primary"
          )}
        >
          {actor === "you" ? <User className="h-2.5 w-2.5" /> : <Bot className="h-2.5 w-2.5" />}
          {ACTOR_LABEL[actor]}
        </button>
        <div className="ml-auto flex items-center gap-1">
          <Search className="h-3 w-3 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter…"
            aria-label="Filter activity"
            className="h-5 w-28 rounded border border-border bg-surface-2 px-1.5 text-[11px] outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
          />
        </div>
      </div>

      {/* Rows */}
      {showSkeleton ? (
        <div className="space-y-px px-2 py-1" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex h-8 items-center gap-2">
              <Skeleton className="h-3.5 w-3.5 rounded-full" />
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 flex-1" />
              <Skeleton className="h-3 w-12" />
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-muted-foreground">
          No activity yet — run a command (⌘K) or ask the assistant.
        </div>
      ) : filtered.length === 0 ? (
        <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">
          No events match the current filters.
        </div>
      ) : (
        <div>
          {filtered.map((e) => {
            const isOpen = !!expanded[e.id];
            const cmd = commandForTool(e.tool);
            const run = e.runId ? runs.find((r) => r.id === e.runId) : undefined;
            const isAgent = e.source === "agent" || e.source === "mcp";
            const showLintDiags =
              isOpen && e.tool === "linter_tool" && !!lintResult && e.id === latestLintId;
            return (
              <div key={e.id} className="border-b border-border/50">
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  onClick={() => toggle(e.id)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter" || ev.key === " ") {
                      ev.preventDefault();
                      toggle(e.id);
                    }
                  }}
                  className="flex min-h-8 cursor-pointer items-center gap-2 px-2 outline-none hover:bg-surface-2 focus-visible:ring-1 focus-visible:ring-primary/60"
                >
                  <StatusMark status={e.status} />
                  <span className="shrink-0 font-mono text-xs">{e.tool}</span>
                  {e.runId ? (
                    <button
                      type="button"
                      onClick={(ev) => {
                        ev.stopPropagation();
                        if (sid && e.runId) openArtifact(sid, artifactKeyForRunId(e.runId));
                      }}
                      className="shrink-0 rounded border border-primary/40 bg-primary/10 px-1 font-mono text-[10px] text-primary outline-none hover:bg-primary/20 focus-visible:ring-1 focus-visible:ring-primary/60"
                      title={`Open ${e.runId}`}
                    >
                      {e.runId}
                    </button>
                  ) : null}
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-[11px]",
                      e.status === "error" ? "text-status-fail" : "text-muted-foreground"
                    )}
                  >
                    {e.resultSummary}
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-[10px] text-muted-foreground">
                    {isAgent ? (
                      <span title={e.source === "mcp" ? "MCP" : "Agent"}>
                        <Bot className="h-3 w-3" />
                      </span>
                    ) : (
                      <span title="You">
                        <User className="h-3 w-3" />
                      </span>
                    )}
                    {e.durationMs != null ? <span>{formatDuration(e.durationMs)}</span> : null}
                    <span>{relativeTime(e.ts)}</span>
                    {isOpen ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                  </span>
                </div>

                {isOpen && (
                  <div className="space-y-2 px-8 pb-2 pt-1">
                    <pre className="max-h-40 overflow-auto thin-scrollbar rounded bg-surface-2 p-2 font-mono text-[11px]">
                      {JSON.stringify(e.args, null, 2)}
                    </pre>
                    {e.resultSummary ? (
                      <div
                        className={cn(
                          "whitespace-pre-wrap text-[11px]",
                          e.status === "error" ? "text-status-fail" : "text-muted-foreground"
                        )}
                      >
                        {e.resultSummary}
                      </div>
                    ) : null}

                    {showLintDiags && lintResult ? (
                      <div className="space-y-0.5">
                        {[...lintResult.errors, ...lintResult.warnings].map((d, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-[11px]">
                            {d.severity === "error" ? (
                              <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-status-fail" />
                            ) : (
                              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-status-warn" />
                            )}
                            {d.file ? (
                              <button
                                type="button"
                                onClick={() => {
                                  if (sid && d.file) openArtifact(sid, `code:${d.file}`);
                                }}
                                className="shrink-0 font-mono text-primary outline-none hover:underline focus-visible:ring-1 focus-visible:ring-primary/60"
                              >
                                {d.file}
                                {d.line != null ? `:${d.line}` : ""}
                              </button>
                            ) : null}
                            <span className="text-muted-foreground">{d.message}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    <div className="flex items-center gap-2">
                      {run ? (
                        <button
                          type="button"
                          onClick={() => {
                            if (sid && e.runId) openArtifact(sid, artifactKeyForRunId(e.runId));
                          }}
                          className="rounded border border-border px-1.5 py-0.5 text-[10px] text-foreground outline-none hover:bg-surface-2 focus-visible:ring-1 focus-visible:ring-primary/60"
                        >
                          Open {run.kind === "sim" ? "waveform" : "report"}
                        </button>
                      ) : null}
                      {cmd ? (
                        <button
                          type="button"
                          disabled={e.status === "running"}
                          onClick={() => void runCommand(cmd)}
                          className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] text-foreground outline-none hover:bg-surface-2 focus-visible:ring-1 focus-visible:ring-primary/60 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <RotateCcw className="h-2.5 w-2.5" />
                          Re-run
                        </button>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Older pages */}
      {nextBefore && events.length > 0 ? (
        <button
          type="button"
          disabled={loadingMore}
          onClick={() => {
            setLoadingMore(true);
            void loadActivity({ more: true }).finally(() => setLoadingMore(false));
          }}
          className="flex h-7 w-full items-center justify-center gap-1 text-[11px] text-muted-foreground outline-none hover:bg-surface-2 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60 disabled:opacity-50"
        >
          {loadingMore ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Load more
        </button>
      ) : null}
    </div>
  );
}

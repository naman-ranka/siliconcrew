"use client";

import { useMemo } from "react";
import { ArrowRight, Cpu, FileCode2, Waves } from "lucide-react";
import { useStore } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { openArtifact, artifactKeyForFile } from "@/lib/openArtifact";
import { cn } from "@/lib/utils";
import { relativeTime, statusDotClass } from "./runStatus";
import type { RunSummary } from "@/types";

// The agent-shell artifact panel's HOME view (Wave 8): Runs + Files as an
// index INTO artifacts — every click here ends in "open something in this
// panel", which is why the lists live with the artifacts instead of in a
// fixed sidebar. Viewing only: no pin/compare/retry (IDE power), no lint
// rows (runs are sim/synth run dirs; lint lives in the activity feed).

const SECTION_LABEL =
  "px-3 pb-1 pt-3 flex items-center text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70";

/** The artifact a run opens to by default: waveform for sims, report for
 *  synth — same convention as the tool cards. */
export function primaryArtifactKey(r: RunSummary): string {
  return r.kind === "sim" ? `wave:${r.id}` : `report:${r.id}`;
}

export function ArtifactIndex() {
  const runs = useStore((s) => s.runs);
  const manifest = useStore((s) => s.manifest);
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { unreadRunIds, clearUnread } = useSessionUi(sid);

  const files = useMemo(
    () =>
      (manifest?.files ?? []).filter((f) =>
        ["rtl", "tb", "sdc", "include"].includes(f.role)
      ),
    [manifest]
  );

  return (
    <div className="h-full overflow-y-auto thin-scrollbar" data-testid="artifact-index">
      <div className={cn(SECTION_LABEL, "pt-3")} data-testid="agent-runs-section">
        Runs
        <span className="ml-auto font-mono text-muted-foreground/50">{runs.length}</span>
      </div>
      <div className="px-1.5 pb-2">
        {runs.length === 0 && (
          <p className="px-2 py-1 text-[11px] text-muted-foreground/60">No runs yet.</p>
        )}
        {runs.map((r) => (
          <button
            key={r.id}
            type="button"
            data-testid={`agent-run-${r.id}`}
            onClick={() => {
              if (!sid) return;
              openArtifact(sid, primaryArtifactKey(r));
              clearUnread(r.id);
            }}
            className="group flex h-10 w-full items-center gap-2.5 rounded-md px-2 text-left hover:bg-surface-2"
          >
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDotClass(r.status))} />
            {r.kind === "sim" ? (
              <Waves className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            ) : (
              <Cpu className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            )}
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="truncate font-mono text-[12px]">{r.id}</span>
                {unreadRunIds.includes(r.id) && (
                  <span
                    title="new"
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary animate-pulse-subtle"
                  />
                )}
              </span>
              {r.top && (
                <span className="block truncate text-[10.5px] text-muted-foreground/70">
                  {r.top}
                </span>
              )}
            </span>
            <span className="shrink-0 text-[9px] font-mono text-muted-foreground/50">
              {relativeTime(r.createdAt)}
            </span>
            <ArrowRight
              className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40 opacity-0 group-hover:opacity-100"
              aria-hidden
            />
          </button>
        ))}
      </div>

      <div className={SECTION_LABEL} data-testid="agent-files-section">
        Files
        <span className="ml-auto font-mono text-muted-foreground/50">{files.length}</span>
      </div>
      <div className="px-1.5 pb-3">
        {files.length === 0 && (
          <p className="px-2 py-1 text-[11px] text-muted-foreground/60">No design files yet.</p>
        )}
        {files.map((f) => (
          <button
            key={f.path}
            type="button"
            data-testid={`agent-file-${f.path}`}
            onClick={() => sid && openArtifact(sid, artifactKeyForFile(f.path))}
            className="flex h-8 w-full items-center gap-2.5 rounded-md px-2 text-left hover:bg-surface-2"
          >
            <FileCode2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate font-mono text-[12px]">{f.name}</span>
            <span className="ml-auto shrink-0 text-[9px] uppercase text-muted-foreground/40">
              {f.role}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

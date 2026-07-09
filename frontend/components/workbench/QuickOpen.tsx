"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Command } from "cmdk";
import {
  Activity,
  BarChart3,
  CircuitBoard,
  Code2,
  FileText,
  Layers,
  Search,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { workspaceApi } from "@/lib/api";
import { parseArtifactKey } from "@/lib/artifactKeys";
import { artifactKeyForFile, artifactLabel, openArtifact } from "@/lib/openArtifact";
import type { ArtifactKind } from "@/types";

const KIND_ICON: Record<ArtifactKind, React.ComponentType<{ className?: string }>> = {
  code: Code2,
  spec: FileText,
  wave: Activity,
  report: BarChart3,
  layout: Layers,
  schematic: CircuitBoard,
};

const KIND_NAME: Record<ArtifactKind, string> = {
  code: "Code",
  spec: "Spec",
  wave: "Waveform",
  report: "Report",
  layout: "Layout",
  schematic: "Schematic",
};

interface QuickOpenItem {
  key: string;
  label: string;
  kind: ArtifactKind;
}

/**
 * v2 quick-open (⌘P) — one fuzzy list over EVERY openable artifact: workspace
 * file paths, run artifacts (wave/report/layout) and the spec, all resolving
 * to artifact keys through the single openArtifact() entry point.
 */
export function QuickOpen() {
  const open = useWorkbenchUiStore((s) => s.quickOpenOpen);
  const setOpen = useWorkbenchUiStore((s) => s.setQuickOpenOpen);
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const runs = useStore((s) => s.runs);
  const spec = useStore((s) => s.spec);

  // File-path source: fetched when the dialog opens, cached per session in
  // component state (stale list stays usable while a refresh is in flight).
  const [paths, setPaths] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const cacheRef = useRef<{ sessionId: string; paths: string[]; truncated: boolean } | null>(null);

  useEffect(() => {
    if (!open || !sessionId) return;
    if (cacheRef.current?.sessionId === sessionId) {
      setPaths(cacheRef.current.paths);
      setTruncated(cacheRef.current.truncated);
    } else {
      setPaths([]);
      setTruncated(false);
    }
    let cancelled = false;
    workspaceApi
      .getDirPaths(sessionId)
      .then((res) => {
        if (cancelled) return;
        cacheRef.current = { sessionId, paths: res.paths, truncated: res.truncated };
        setPaths(res.paths);
        setTruncated(res.truncated);
      })
      .catch(() => {
        /* keep whatever list we have — quick-open stays usable */
      });
    return () => {
      cancelled = true;
    };
  }, [open, sessionId]);

  const items = useMemo<QuickOpenItem[]>(() => {
    const map = new Map<string, QuickOpenItem>();
    const add = (key: string, label: string) => {
      if (map.has(key)) return; // dedup: file → wave:<id> duplicates the run entry
      const kind = parseArtifactKey(key)?.kind;
      if (!kind) return;
      map.set(key, { key, label, kind });
    };
    // (c) the spec singleton
    if (spec) add("spec", "Spec");
    // (b) run artifacts — sim runs carry a waveform; synth runs a report + layout
    for (const r of runs) {
      if (r.kind === "sim") {
        add(`wave:${r.id}`, artifactLabel(`wave:${r.id}`));
      } else {
        add(`report:${r.id}`, artifactLabel(`report:${r.id}`));
        add(`layout:${r.id}`, artifactLabel(`layout:${r.id}`));
      }
    }
    // (a) every workspace file, routed through the type-aware key mapping
    for (const p of paths) add(artifactKeyForFile(p), p);
    return Array.from(map.values());
  }, [runs, spec, paths]);

  const select = (key: string) => {
    openArtifact(sessionId, key);
    setOpen(false);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Quick open"
      overlayClassName="fixed inset-0 z-50 bg-black/50 animate-fade-in"
      contentClassName="fixed left-1/2 top-[18%] z-50 w-[560px] max-w-[92vw] -translate-x-1/2 animate-scale-in"
      className="rounded-lg border border-border bg-popover text-popover-foreground shadow-e3 overflow-hidden"
    >
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <Command.Input
          placeholder="Open artifact…"
          className="h-9 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
        />
      </div>
      <Command.List className="max-h-72 overflow-y-auto thin-scrollbar p-1">
        <Command.Empty className="py-6 text-center text-xs text-muted-foreground">
          No matching artifact.
        </Command.Empty>
        {items.map((item) => {
          const Icon = KIND_ICON[item.kind];
          return (
            <Command.Item
              key={item.key}
              value={`${item.label} ${item.key}`}
              onSelect={() => select(item.key)}
              className={[
                "flex h-8 cursor-pointer select-none items-center gap-2 rounded-md px-2 text-xs",
                "text-foreground data-[selected=true]:bg-surface-2",
              ].join(" ")}
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate font-mono">{item.label}</span>
              <span className="shrink-0 text-2xs text-muted-foreground">{KIND_NAME[item.kind]}</span>
            </Command.Item>
          );
        })}
      </Command.List>
      <div className="flex items-center gap-2 border-t border-border bg-surface-1 px-3 py-1.5 text-2xs text-muted-foreground">
        <span>every openable artifact across the design</span>
        {truncated && <span className="ml-auto">file list truncated</span>}
      </div>
    </Command.Dialog>
  );
}

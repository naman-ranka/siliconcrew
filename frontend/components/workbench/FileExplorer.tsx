"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Activity,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  CircuitBoard,
  Crown,
  File as FileIcon,
  FileCode2,
  FileText,
  FlaskConical,
  Folder,
  FolderOpen,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
} from "lucide-react";

import { useStore } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { openArtifact, artifactKeyForFile } from "@/lib/openArtifact";
import {
  dirPrefixesForPath,
  flattenTree,
  isSimTopFile,
  isSynthTopFile,
  runIdForDirEntry,
  validateNewFilePath,
  type FlatNode,
} from "@/lib/fileTree";
import { statusDotClass } from "./runStatus";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { IconTooltip } from "@/components/ui/tooltip";
import type { DesignManifest, FileRole } from "@/types";

const ROW_H = 26;
const INDENT = 12;

// Role badge palette — mirrors the old FileTree.tsx language: RTL anchors on
// info-blue, TB on the primary tint; SDC/INC/OTHER stay neutral. Status tokens
// are reserved for runs so the file list reads calm.
const ROLE_LABEL: Record<FileRole, string> = {
  rtl: "RTL",
  tb: "TB",
  sdc: "SDC",
  include: "INC",
  other: "OTHER",
};

const ROLE_BADGE: Record<FileRole, string> = {
  rtl: "bg-info/12 text-info border-info/25",
  tb: "bg-primary/12 text-primary border-primary/25",
  sdc: "bg-surface-3 text-foreground/70 border-border",
  include: "bg-surface-3 text-muted-foreground border-border",
  other: "bg-surface-3 text-muted-foreground border-border",
};

function fileIconFor(name: string) {
  const lower = name.toLowerCase();
  if (/\.(v|sv)$/.test(lower)) return <FileCode2 className="h-3.5 w-3.5" />;
  if (/\.(yaml|yml|md)$/.test(lower)) return <FileText className="h-3.5 w-3.5" />;
  if (lower.endsWith(".vcd")) return <Activity className="h-3.5 w-3.5" />;
  if (lower.endsWith(".gds")) return <Layers className="h-3.5 w-3.5" />;
  if (lower.endsWith(".svg")) return <CircuitBoard className="h-3.5 w-3.5" />;
  return <FileIcon className="h-3.5 w-3.5" />;
}

function roleForRootFile(name: string, manifest: DesignManifest | null): FileRole | null {
  return manifest?.files.find((f) => f.name === name)?.role ?? null;
}

/** Small header icon button (h-8 header, compact density). */
function HeaderButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <IconTooltip label={label}>
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        className={cn(
          "inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground outline-none",
          "hover:bg-surface-2 hover:text-foreground focus-visible:ring-2 focus-visible:ring-primary/60",
          "disabled:opacity-40 disabled:pointer-events-none transition-colors duration-fast ease-swift"
        )}
      >
        {children}
      </button>
    </IconTooltip>
  );
}

/**
 * Inline "New file" row (header + button / dir context menu → this). The path
 * may contain slashes (`rtl/alu.v`) — folders exist implicitly with their
 * first file, git-style. Creates via the SAME save path the CodeViewer uses
 * (store.saveCodeFile → PUT /code/{path}), then refreshes the affected dir
 * slices and opens the new file in a code tab.
 */
function NewFileRow({ prefix }: { prefix: string }) {
  const setNewFilePrefix = useWorkbenchUiStore((s) => s.setNewFilePrefix);
  const newFileKind = useWorkbenchUiStore((s) => s.newFileKind);
  const currentSession = useStore((s) => s.currentSession);
  const saveCodeFile = useStore((s) => s.saveCodeFile);
  const invalidateDirs = useStore((s) => s.invalidateDirs);
  const pushToast = useStore((s) => s.pushToast);
  const isFolder = newFileKind === "folder";

  const [value, setValue] = useState(prefix ? `${prefix}/` : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const close = () => setNewFilePrefix(null);

  const submit = async () => {
    if (busy) return;
    const path = value.trim().replace(/\/+$/, "");
    const err = validateNewFilePath(path);
    if (err) {
      setError(err);
      return;
    }
    setBusy(true);
    try {
      if (isFolder) {
        // Folders exist through their first file (git-style; the workspace
        // tarball has no empty dirs). `.gitkeep` is the standard marker — and
        // dotfiles are hidden in the tree, so the user just sees the folder.
        await saveCodeFile(`${path}/.gitkeep`, "");
        invalidateDirs(dirPrefixesForPath(`${path}/.gitkeep`));
        pushToast({ kind: "success", title: "Folder created", detail: path });
      } else {
        await saveCodeFile(path, "");
        invalidateDirs(dirPrefixesForPath(path));
        if (currentSession) openArtifact(currentSession.id, `code:${path}`);
        pushToast({ kind: "success", title: "File created", detail: path });
      }
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-border px-2 py-1.5">
      <div className="flex items-center gap-1.5">
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" aria-hidden />
        ) : (
          <FileIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <input
          ref={inputRef}
          type="text"
          aria-label={isFolder ? "New folder path" : "New file path"}
          placeholder={isFolder ? "path/to/folder" : "path/to/file.v"}
          value={value}
          disabled={busy}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void submit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              close();
            }
          }}
          onBlur={() => {
            // Abandoning an untouched (or in-flight) input closes it quietly.
            if (!busy && value.trim() === (prefix ? `${prefix}/` : "")) close();
          }}
          className={cn(
            "h-6 w-full min-w-0 rounded border bg-surface-2 px-1.5 font-mono text-xs outline-none",
            "placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-primary/60",
            error ? "border-status-fail/60" : "border-border"
          )}
        />
      </div>
      {error && <div className="mt-0.5 pl-5 text-[10px] text-status-fail">{error}</div>}
    </div>
  );
}

/**
 * v2 FileExplorer — the left-rail workspace tree. Lazy dirs via the store's
 * SWR dirCache, virtualized rows (@tanstack/react-virtual), manifest role
 * badges + top-module markers on root files, run-status dots on run dirs,
 * right-click context menu, "New file" (header + / folder right-click), and
 * full keyboard navigation.
 */
export function FileExplorer() {
  const currentSession = useStore((s) => s.currentSession);
  const manifest = useStore((s) => s.manifest);
  const runs = useStore((s) => s.runs);
  const dirCache = useStore((s) => s.dirCache);
  const loadDir = useStore((s) => s.loadDir);
  const invalidateDirs = useStore((s) => s.invalidateDirs);
  const setContextMenu = useWorkbenchUiStore((s) => s.setContextMenu);
  const newFilePrefix = useWorkbenchUiStore((s) => s.newFilePrefix);
  const setNewFilePrefix = useWorkbenchUiStore((s) => s.setNewFilePrefix);

  const sessionId = currentSession?.id ?? null;
  const { expandedDirs, activeTab, toggleDir } = useSessionUi(sessionId);

  const rows = useMemo(() => flattenTree(dirCache, expandedDirs), [dirCache, expandedDirs]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const rowEls = useRef(new Map<number, HTMLDivElement>());
  const [focusedIndex, setFocusedIndex] = useState(0);
  const focusIdx = rows.length === 0 ? 0 : Math.min(focusedIndex, rows.length - 1);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  });

  // Kick the root load once per session; also hydrate any persisted expanded
  // dirs whose slices aren't cached yet (they render as loading markers).
  useEffect(() => {
    if (!sessionId) return;
    if (!dirCache[""]) void loadDir("");
    for (const dir of expandedDirs) {
      if (!dirCache[dir]) void loadDir(dir);
    }
  }, [sessionId, dirCache, expandedDirs, loadDir]);

  const refresh = useCallback(() => {
    invalidateDirs(["", ...expandedDirs]);
  }, [invalidateDirs, expandedDirs]);

  // Only toggleDir exists on the UI store — collapse-all iterates it (each
  // call flips an expanded dir off).
  const collapseAll = useCallback(() => {
    for (const dir of expandedDirs) toggleDir(dir);
  }, [expandedDirs, toggleDir]);

  const openNode = useCallback(
    (node: FlatNode) => {
      if (!sessionId) return;
      openArtifact(sessionId, artifactKeyForFile(node.entry.path));
    },
    [sessionId]
  );

  const toggleNode = useCallback(
    (node: FlatNode) => {
      const path = node.entry.path;
      toggleDir(path);
      // Expanding an uncached dir fetches it (loadDir no-ops when populated).
      if (!node.expanded) void loadDir(path);
    },
    [toggleDir, loadDir]
  );

  const moveFocus = useCallback(
    (index: number) => {
      const next = Math.max(0, Math.min(index, rows.length - 1));
      setFocusedIndex(next);
      virtualizer.scrollToIndex(next);
      // Roving tabindex: focus the row element once it's rendered.
      requestAnimationFrame(() => rowEls.current.get(next)?.focus());
    },
    [rows.length, virtualizer]
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (rows.length === 0) return;
      const node = rows[focusIdx];
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          moveFocus(focusIdx + 1);
          break;
        case "ArrowUp":
          e.preventDefault();
          moveFocus(focusIdx - 1);
          break;
        case "ArrowRight":
          e.preventDefault();
          if (node?.entry.kind === "dir") {
            if (!node.expanded) toggleNode(node);
            else moveFocus(focusIdx + 1); // enter the open dir
          }
          break;
        case "ArrowLeft": {
          e.preventDefault();
          if (!node) break;
          if (node.entry.kind === "dir" && node.expanded) {
            toggleNode(node);
            break;
          }
          // Jump to the parent row (nearest prior row one level shallower).
          for (let i = focusIdx - 1; i >= 0; i--) {
            if (rows[i].depth < node.depth) {
              moveFocus(i);
              break;
            }
          }
          break;
        }
        case "Enter":
          e.preventDefault();
          if (!node) break;
          if (node.entry.kind === "dir") toggleNode(node);
          else openNode(node);
          break;
      }
    },
    [rows, focusIdx, moveFocus, toggleNode, openNode]
  );

  const rootSlice = dirCache[""];
  const rootLoading = !rootSlice || (rootSlice.status === "loading" && rootSlice.entries.length === 0);
  const rootError = rootSlice?.status === "error" && rootSlice.entries.length === 0;
  const rootEmpty =
    !!rootSlice &&
    (rootSlice.status === "ready" || rootSlice.status === "revalidating") &&
    rootSlice.entries.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex h-8 shrink-0 items-center justify-between gap-1 border-b border-border px-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Explorer
        </span>
        <div className="flex items-center gap-0.5">
          <HeaderButton
            label="New file"
            onClick={() => setNewFilePrefix("")}
            disabled={!sessionId}
          >
            <Plus className="h-3 w-3" />
          </HeaderButton>
          <HeaderButton label="Refresh" onClick={refresh} disabled={!sessionId}>
            <RefreshCw className="h-3 w-3" />
          </HeaderButton>
          <HeaderButton
            label="Collapse all"
            onClick={collapseAll}
            disabled={expandedDirs.length === 0}
          >
            <ChevronsDownUp className="h-3 w-3" />
          </HeaderButton>
        </div>
      </div>

      {/* Inline "New file" input — keyed so a new prefix resets the draft. */}
      {newFilePrefix != null && <NewFileRow key={newFilePrefix} prefix={newFilePrefix} />}

      {/* Body */}
      <div
        ref={scrollRef}
        role="tree"
        aria-label="Workspace files"
        tabIndex={0}
        onKeyDown={onKeyDown}
        onContextMenu={(e) => {
          // Empty-space right-click (rows stopPropagation) → workspace menu.
          e.preventDefault();
          setContextMenu({ x: e.clientX, y: e.clientY, path: "", kind: "empty" });
        }}
        className="thin-scrollbar relative flex-1 overflow-y-auto overflow-x-hidden py-1 outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary/40"
      >
        {rootLoading ? (
          <div aria-hidden="true">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex h-[26px] items-center gap-2 px-2">
                <Skeleton className="h-3.5 w-3.5 shrink-0 rounded" />
                <Skeleton className="h-3" style={{ width: `${72 - (i % 4) * 12}%` }} />
              </div>
            ))}
          </div>
        ) : rootError ? (
          <div className="flex h-[26px] items-center gap-2 px-2 text-xs text-muted-foreground">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-status-fail" />
            <span className="truncate">Couldn’t load files.</span>
            <button
              type="button"
              onClick={() => void loadDir("", { revalidate: true })}
              className="shrink-0 rounded px-1 text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              Retry
            </button>
          </div>
        ) : rootEmpty ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            No files yet — ask the assistant to scaffold a design.
          </div>
        ) : (
          <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((vi) => {
              const node = rows[vi.index];
              if (!node) return null;
              const { entry } = node;
              const isDir = entry.kind === "dir";
              const runId = isDir ? runIdForDirEntry(entry) : null;
              const run = runId ? runs.find((r) => r.id === runId) : undefined;
              const role = !isDir && node.depth === 0 ? roleForRootFile(entry.name, manifest) : null;
              const synthTop = !isDir && node.depth === 0 && isSynthTopFile(entry.name, manifest);
              const simTop = !isDir && node.depth === 0 && isSimTopFile(entry.name, manifest);
              const active = !isDir && activeTab != null && artifactKeyForFile(entry.path) === activeTab;
              const focused = vi.index === focusIdx;

              return (
                <div
                  key={entry.path || vi.index}
                  ref={(el) => {
                    if (el) rowEls.current.set(vi.index, el);
                    else rowEls.current.delete(vi.index);
                  }}
                  role="treeitem"
                  aria-level={node.depth + 1}
                  aria-expanded={isDir ? node.expanded : undefined}
                  aria-selected={active || undefined}
                  tabIndex={focused ? 0 : -1}
                  title={entry.path}
                  style={{
                    height: ROW_H,
                    transform: `translateY(${vi.start}px)`,
                    paddingLeft: 8 + node.depth * INDENT,
                  }}
                  className={cn(
                    "absolute left-0 top-0 flex w-full cursor-pointer select-none items-center gap-1.5 pr-2 outline-none",
                    "transition-colors duration-fast ease-swift",
                    active ? "bg-primary/10 text-foreground" : "hover:bg-surface-2",
                    "focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/60"
                  )}
                  onClick={() => {
                    setFocusedIndex(vi.index);
                    if (isDir) toggleNode(node);
                    else openNode(node);
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation(); // keep the body's empty-space menu from overriding
                    setFocusedIndex(vi.index);
                    setContextMenu({
                      x: e.clientX,
                      y: e.clientY,
                      path: entry.path,
                      kind: isDir ? "dir" : "file",
                    });
                  }}
                >
                  {/* Left accent for the active file. */}
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                    />
                  )}

                  {isDir ? (
                    <>
                      <span className="shrink-0 text-muted-foreground" aria-hidden="true">
                        {node.loading ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : node.expanded ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                      </span>
                      <span className="shrink-0 text-muted-foreground">
                        {node.expanded ? (
                          <FolderOpen className="h-3.5 w-3.5" />
                        ) : (
                          <Folder className="h-3.5 w-3.5" />
                        )}
                      </span>
                      <span className="min-w-0 truncate font-mono text-xs">{entry.name}</span>
                      {runId && (
                        <span
                          aria-hidden="true"
                          title={run ? `${runId}: ${run.status}` : runId}
                          className={cn(
                            "ml-0.5 h-1.5 w-1.5 shrink-0 rounded-full",
                            statusDotClass(run?.status)
                          )}
                        />
                      )}
                    </>
                  ) : (
                    <>
                      {/* Files have no chevron — keep the 12px gutter aligned. */}
                      <span className="w-3 shrink-0" aria-hidden="true" />
                      <span
                        className={cn(
                          "shrink-0",
                          active ? "text-primary" : "text-muted-foreground"
                        )}
                      >
                        {fileIconFor(entry.name)}
                      </span>
                      <span className={cn("min-w-0 truncate font-mono text-xs", active && "font-medium")}>
                        {entry.name}
                      </span>
                      {synthTop && (
                        <span
                          className="shrink-0 inline-flex"
                          role="img"
                          aria-label="synth top"
                          title="synth top"
                        >
                          <Crown className="h-3 w-3 text-info" />
                        </span>
                      )}
                      {simTop && (
                        <span
                          className="shrink-0 inline-flex"
                          role="img"
                          aria-label="sim top"
                          title="sim top"
                        >
                          <FlaskConical className="h-3 w-3 text-primary" />
                        </span>
                      )}
                      {role && (
                        <span
                          className={cn(
                            "ml-auto inline-flex shrink-0 items-center justify-center rounded border px-1.5 py-0.5 text-[9px] font-semibold leading-none tracking-wide",
                            ROLE_BADGE[role]
                          )}
                        >
                          {ROLE_LABEL[role]}
                        </span>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer: the design's two anchors, always visible. */}
      <div className="flex h-7 shrink-0 items-center gap-2 overflow-hidden border-t border-border px-2 font-mono text-[10px] text-muted-foreground">
        {manifest ? (
          <>
            <span className="flex min-w-0 items-center gap-1" title="Top module used for synthesis">
              <Crown className="h-3 w-3 shrink-0 text-info" />
              <span className="truncate text-foreground/80">{manifest.synthTop || "—"}</span>
            </span>
            <span className="flex min-w-0 items-center gap-1" title="Testbench top used for simulation">
              <FlaskConical className="h-3 w-3 shrink-0 text-primary" />
              <span className="truncate text-foreground/80">{manifest.simTop || "—"}</span>
            </span>
          </>
        ) : (
          <>
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-3 w-20" />
          </>
        )}
      </div>
    </div>
  );
}

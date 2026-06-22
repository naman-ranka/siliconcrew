"use client";

import { useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PanelHeader } from "./PanelHeader";
import { Upload, FileCode2, FileTerminal, FileClock, FileType2, File as FileIcon, Crown, FlaskConical, Download } from "lucide-react";
import type { FileRole } from "@/types";

const ROLE_LABEL: Record<FileRole, string> = {
  rtl: "RTL",
  tb: "TB",
  sdc: "SDC",
  include: "INC",
  other: "OTHER",
};

/**
 * Role badge palette is deliberately kept OFF the orange brand for status:
 * RTL=info (the DUT, the "blue" anchor), TB=primary-tint (the test side — this
 * is a design distinction, not a status), SDC/INC/OTHER use neutral surface
 * tones. No status-pass/warn/fail tokens here — those stay reserved for run
 * status so the file list reads calm.
 */
const ROLE_BADGE: Record<FileRole, string> = {
  rtl: "bg-info/12 text-info border-info/25",
  tb: "bg-primary/12 text-primary border-primary/25",
  sdc: "bg-surface-3 text-foreground/70 border-border",
  include: "bg-surface-3 text-muted-foreground border-border",
  other: "bg-surface-3 text-muted-foreground border-border",
};

function roleIcon(role: FileRole) {
  switch (role) {
    case "rtl":
      return <FileCode2 className="h-3.5 w-3.5" />;
    case "tb":
      return <FileTerminal className="h-3.5 w-3.5" />;
    case "sdc":
      return <FileClock className="h-3.5 w-3.5" />;
    case "include":
      return <FileType2 className="h-3.5 w-3.5" />;
    default:
      return <FileIcon className="h-3.5 w-3.5" />;
  }
}

const ROLES: FileRole[] = ["rtl", "tb", "sdc", "include", "other"];

/** Small reusable inline role badge. */
function RoleBadge({ role }: { role: FileRole }) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center text-[9px] font-semibold leading-none tracking-wide px-1.5 py-0.5 rounded border shrink-0",
        ROLE_BADGE[role]
      )}
    >
      {ROLE_LABEL[role]}
    </span>
  );
}

/**
 * The file tree is manifest-driven: every file shows its derived role (which
 * decides what reaches each stage) and the role is user-overridable inline.
 * synthTop/simTop are marked so the design's two anchors are always visible.
 * Supports drag-and-drop upload, per-file download (so it's not a black box),
 * and a transient upload confirmation.
 */
export function FileTree() {
  const { manifest, manifestLoading, setFileRole, uploadFiles, selectCodeFile, setArtifactTab, currentSession, uploadNotice, selectedCodeFile, activeArtifactTab } = useStore();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const files = manifest?.files ?? [];

  const onUpload = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setBusy(true);
    try {
      // The confirmation banner is store-driven (uploadNotice) so it shows
      // regardless of which surface triggered the upload.
      await uploadFiles(Array.from(list));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const downloadFile = async (name: string) => {
    if (!currentSession) return;
    try {
      const { content } = await workspaceApi.getFile(currentSession.id, name);
      const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* non-fatal */
    }
  };

  return (
    <div
      className="relative flex flex-col min-h-0"
      onDragOver={(e) => {
        if (!currentSession) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        // Only clear when the pointer actually leaves the container, not when it
        // crosses between child rows.
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
        setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void onUpload(e.dataTransfer.files);
      }}
    >
      <PanelHeader label="Files">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 gap-1 text-xs"
          disabled={!currentSession || busy}
          title="Upload Verilog / SDC files (or drag & drop here)"
          onClick={() => fileInput.current?.click()}
        >
          <Upload className={cn("h-3.5 w-3.5", busy && "animate-pulse")} />
          {busy ? "Uploading…" : "Upload"}
        </Button>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          aria-label="Upload design files"
          onChange={(e) => void onUpload(e.target.files)}
        />
      </PanelHeader>

      {uploadNotice && (
        <div className="px-3 py-1 text-[10px] text-status-pass bg-status-pass/10 border-b border-border" role="status">
          {uploadNotice}
        </div>
      )}

      {/* Drag-and-drop overlay: calm ring + hint, animated in. */}
      {dragging && currentSession && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center animate-fade-in motion-reduce:animate-none">
          <div className="absolute inset-1.5 rounded-lg border-2 border-dashed border-primary/50 bg-primary/5" />
          <div className="relative flex items-center gap-2 rounded-md bg-surface-1 px-3 py-1.5 text-xs font-medium text-foreground shadow-e2 border border-primary/30">
            <Upload className="h-3.5 w-3.5 text-primary" />
            Drop to upload
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto thin-scrollbar py-1">
        {manifestLoading && !manifest ? (
          <div className="px-2 py-1 space-y-1.5" aria-hidden="true">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-2 px-2 py-1">
                <Skeleton className="h-3.5 w-3.5 rounded" />
                <Skeleton className="h-3 flex-1" style={{ maxWidth: `${70 - i * 8}%` }} />
                <Skeleton className="h-3.5 w-7 rounded" />
              </div>
            ))}
          </div>
        ) : files.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            {dragging ? "Drop files to upload" : "No files yet — drag & drop, or use Upload."}
          </div>
        ) : (
          files.map((f) => {
            const isSynthTop = manifest?.synthTop && f.role === "rtl";
            const isSimTop = manifest?.simTop && f.role === "tb";
            const openable = f.name.endsWith(".v") || f.name.endsWith(".sv");
            const isSelected = openable && activeArtifactTab === "code" && selectedCodeFile === f.name;
            return (
              <div
                key={f.name}
                className={cn(
                  "group relative flex items-center gap-1.5 pl-2.5 pr-2 py-1 mx-1 rounded-md transition-colors duration-fast ease-swift",
                  isSelected
                    ? "bg-primary/10 text-foreground"
                    : "hover:bg-surface-2"
                )}
                title={f.path}
              >
                {/* Left accent for the open file. */}
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-full bg-primary transition-opacity duration-fast ease-swift",
                    isSelected ? "opacity-100" : "opacity-0"
                  )}
                />
                <button
                  type="button"
                  aria-label={`Open ${f.name} (${f.role})`}
                  aria-current={isSelected ? "true" : undefined}
                  disabled={!openable}
                  className={cn(
                    "flex items-center gap-2 min-w-0 flex-1 text-left outline-none rounded focus-visible:ring-2 focus-visible:ring-primary/60",
                    openable ? "cursor-pointer" : "cursor-default"
                  )}
                  onClick={() => {
                    if (openable) {
                      selectCodeFile(f.name);
                      setArtifactTab("code");
                    }
                  }}
                >
                  <span className={cn("shrink-0", isSelected ? "text-primary" : "text-muted-foreground")}>
                    {roleIcon(f.role)}
                  </span>
                  <span className={cn("text-xs font-mono truncate", isSelected && "font-medium")}>{f.name}</span>
                  {isSynthTop && (
                    <Crown className="h-3 w-3 text-info shrink-0" aria-label="synthesis top candidate" />
                  )}
                  {isSimTop && (
                    <FlaskConical className="h-3 w-3 text-primary shrink-0" aria-label="simulation top candidate" />
                  )}
                </button>

                <button
                  type="button"
                  aria-label={`Download ${f.name}`}
                  title={`Download ${f.name}`}
                  onClick={() => void downloadFile(f.name)}
                  className={cn(
                    "shrink-0 rounded p-0.5 outline-none transition-all duration-fast ease-swift",
                    "text-muted-foreground/40 hover:text-foreground hover:bg-surface-3",
                    "group-hover:text-muted-foreground/70 group-focus-within:text-muted-foreground/70",
                    "focus-visible:opacity-100 focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-primary/60"
                  )}
                >
                  <Download className="h-3 w-3" />
                </button>

                <RoleBadge role={f.role} />

                <select
                  aria-label={`Role for ${f.name}`}
                  title={`Change role for ${f.name}`}
                  value={f.role}
                  onChange={(e) => void setFileRole(f.name, e.target.value as FileRole)}
                  className={cn(
                    "shrink-0 rounded border text-[10px] px-1 py-0.5 outline-none transition-all duration-fast ease-swift cursor-pointer",
                    "bg-surface-1 border-border text-muted-foreground/50",
                    "group-hover:text-muted-foreground group-hover:border-border",
                    "group-focus-within:text-muted-foreground",
                    "hover:text-foreground focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-primary/60"
                  )}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            );
          })
        )}
      </div>

      {manifest && (
        <div className="px-3 py-2 border-t border-border text-[10px] text-muted-foreground space-y-1 font-mono">
          <div className="flex items-center gap-1.5 min-w-0" title="Top module used for synthesis">
            <Crown className="h-3 w-3 text-info shrink-0" />
            <span className="text-muted-foreground/70">synthTop</span>
            <span className="truncate text-foreground/80">{manifest.synthTop || "—"}</span>
          </div>
          <div className="flex items-center gap-1.5 min-w-0" title="Testbench top used for simulation">
            <FlaskConical className="h-3 w-3 text-primary shrink-0" />
            <span className="text-muted-foreground/70">simTop</span>
            <span className="truncate text-foreground/80">{manifest.simTop || "—"}</span>
          </div>
          <div className="flex items-center gap-1.5 pt-0.5 text-muted-foreground/70">
            <span>clk {manifest.clockPeriodNs}ns</span>
            <span aria-hidden="true">·</span>
            <span>{manifest.platform}</span>
          </div>
        </div>
      )}
    </div>
  );
}

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
  other: "—",
};

const ROLE_BADGE: Record<FileRole, string> = {
  rtl: "bg-info/15 text-info border-info/30",
  tb: "bg-primary/15 text-primary border-primary/30",
  sdc: "bg-status-warn/15 text-status-warn border-status-warn/30",
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

/**
 * The file tree is manifest-driven: every file shows its derived role (which
 * decides what reaches each stage) and the role is user-overridable inline.
 * synthTop/simTop are marked so the design's two anchors are always visible.
 * Supports drag-and-drop upload, per-file download (so it's not a black box),
 * and a transient upload confirmation.
 */
export function FileTree() {
  const { manifest, manifestLoading, setFileRole, uploadFiles, selectCodeFile, setArtifactTab, currentSession, uploadNotice } = useStore();
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
      className={cn("flex flex-col min-h-0", dragging && "ring-2 ring-primary/60 ring-inset")}
      onDragOver={(e) => {
        if (!currentSession) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
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
          <Upload className="h-3.5 w-3.5" />
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
            return (
              <div
                key={f.name}
                className="group flex items-center gap-1.5 px-2 py-1 mx-1 rounded-md hover:bg-surface-2"
                title={f.path}
              >
                <button
                  type="button"
                  aria-label={`Open ${f.name} (${f.role})`}
                  className="flex items-center gap-2 min-w-0 flex-1 text-left outline-none rounded focus-visible:ring-2 focus-visible:ring-primary/60"
                  onClick={() => {
                    if (f.name.endsWith(".v") || f.name.endsWith(".sv")) {
                      selectCodeFile(f.name);
                      setArtifactTab("code");
                    }
                  }}
                >
                  <span className="text-muted-foreground shrink-0">{roleIcon(f.role)}</span>
                  <span className="text-xs font-mono truncate">{f.name}</span>
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
                  className="shrink-0 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 outline-none focus-visible:ring-2 focus-visible:ring-primary/60 rounded"
                >
                  <Download className="h-3 w-3" />
                </button>
                <span
                  className={cn(
                    "text-[9px] font-semibold px-1.5 py-0.5 rounded border shrink-0",
                    ROLE_BADGE[f.role]
                  )}
                >
                  {ROLE_LABEL[f.role]}
                </span>
                <select
                  aria-label={`Role for ${f.name}`}
                  title={`Change role for ${f.name}`}
                  value={f.role}
                  onChange={(e) => void setFileRole(f.name, e.target.value as FileRole)}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity bg-surface-1 border border-border rounded text-[10px] px-1 py-0.5 text-muted-foreground"
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
        <div className="px-3 py-2 border-t border-border text-[10px] text-muted-foreground space-y-0.5 font-mono">
          <div className="flex items-center gap-1" title="Top module used for synthesis">
            <Crown className="h-3 w-3 text-info" /> synthTop: {manifest.synthTop || "—"}
          </div>
          <div className="flex items-center gap-1" title="Testbench top used for simulation">
            <FlaskConical className="h-3 w-3 text-primary" /> simTop: {manifest.simTop || "—"}
          </div>
          <div>clk: {manifest.clockPeriodNs}ns · {manifest.platform}</div>
        </div>
      )}
    </div>
  );
}

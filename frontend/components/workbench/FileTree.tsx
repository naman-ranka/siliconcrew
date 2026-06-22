"use client";

import { useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Upload, FileCode2, FileTerminal, FileClock, FileType2, File as FileIcon, Crown, FlaskConical } from "lucide-react";
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
 */
export function FileTree() {
  const { manifest, setFileRole, uploadFiles, selectCodeFile, setArtifactTab, currentSession } = useStore();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const files = manifest?.files ?? [];

  const onUpload = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setBusy(true);
    try {
      await uploadFiles(Array.from(list));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className="flex flex-col min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Files</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 gap-1 text-xs"
          disabled={!currentSession || busy}
          onClick={() => fileInput.current?.click()}
        >
          <Upload className="h-3.5 w-3.5" />
          Upload
        </Button>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          aria-label="Upload design files"
          onChange={(e) => void onUpload(e.target.files)}
        />
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar py-1">
        {files.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            No files yet. Upload RTL / testbench to begin.
          </div>
        ) : (
          files.map((f) => {
            const isSynthTop = manifest?.synthTop && f.role === "rtl";
            const isSimTop = manifest?.simTop && f.role === "tb";
            return (
              <div
                key={f.name}
                className="group flex items-center gap-2 px-2 py-1 mx-1 rounded-md hover:bg-surface-2"
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
                  value={f.role}
                  onChange={(e) => void setFileRole(f.name, e.target.value as FileRole)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity bg-surface-1 border border-border rounded text-[10px] px-1 py-0.5 text-muted-foreground"
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
          <div className="flex items-center gap-1">
            <Crown className="h-3 w-3 text-info" /> synthTop: {manifest.synthTop || "—"}
          </div>
          <div className="flex items-center gap-1">
            <FlaskConical className="h-3 w-3 text-primary" /> simTop: {manifest.simTop || "—"}
          </div>
          <div>clk: {manifest.clockPeriodNs}ns · {manifest.platform}</div>
        </div>
      )}
    </div>
  );
}

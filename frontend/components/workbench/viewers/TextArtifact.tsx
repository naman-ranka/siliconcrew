"use client";

import { useEffect } from "react";
import { Download } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ViewerError, ViewerSkeleton } from "./panels";

/**
 * v2 tab wrapper for `text:<path>` — plain monospace rendering of a workspace
 * text file (txt/log/rpt) through the store's smart file cache. The smart-file
 * reader already caps size and returns null content for binary/oversized files,
 * which we surface honestly rather than dumping garbage.
 */
export function TextArtifact({ path }: { path: string }) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const slice = useStore((s) => s.fileCache[path]);
  const loadFile = useStore((s) => s.loadFile);

  useEffect(() => {
    if (sessionId) void loadFile(path);
  }, [sessionId, path, loadFile]);

  const file = slice?.file;
  const content = file?.content ?? null;
  const fileName = path.split("/").pop() || path;
  const download = () => {
    if (sessionId) void workspaceApi.downloadRawFile(sessionId, path);
  };

  if (!slice || (slice.status === "loading" && !file)) return <ViewerSkeleton />;
  if (slice.status === "error" && !file) {
    return <ViewerError title="Couldn't load this file" detail={slice.error} onRetry={() => void loadFile(path)} />;
  }
  if (!file) return <ViewerSkeleton />;
  if (file.binary || file.tooLarge || content == null) {
    return (
      <ViewerError
        title={fileName}
        detail={file.binary ? "Binary file — download to view" : "Too large to display — download to view"}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="text-artifact">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-surface-1 px-3 text-xs font-mono">
        <span className="truncate text-foreground">{fileName}</span>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto h-6 gap-1 px-2 text-[11px] font-sans"
          onClick={download}
        >
          <Download className="h-3 w-3" /> Download
        </Button>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-3 text-[12px] font-mono leading-relaxed text-foreground">
        {content}
      </pre>
    </div>
  );
}

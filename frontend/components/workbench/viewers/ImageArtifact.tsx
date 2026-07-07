"use client";

import { useEffect, useState } from "react";
import { Download, ImageOff } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ViewerError, ViewerSkeleton } from "./panels";

// Checkerboard so transparent PNGs read clearly in either theme (subtle in
// both — a neutral 50% grey at low alpha).
const CHECKER: React.CSSProperties = {
  backgroundImage:
    "linear-gradient(45deg, rgba(128,128,128,0.18) 25%, transparent 25%)," +
    "linear-gradient(-45deg, rgba(128,128,128,0.18) 25%, transparent 25%)," +
    "linear-gradient(45deg, transparent 75%, rgba(128,128,128,0.18) 75%)," +
    "linear-gradient(-45deg, transparent 75%, rgba(128,128,128,0.18) 75%)",
  backgroundSize: "16px 16px",
  backgroundPosition: "0 0, 0 8px, 8px -8px, -8px 0px",
};

/**
 * v2 tab wrapper for `image:<path>` — renders a workspace image (png/jpg/webp/
 * gif/svg) from an AUTHED blob URL. `/file?raw=1` needs a Bearer header, so a
 * bare `<img src=…?raw=1>` 401s and the download helper force-downloads;
 * neither is renderable. We fetch → blob → objectURL and revoke on unmount /
 * path change. SVG renders via `<img>` (never inline HTML) so it can't script.
 */
export function ImageArtifact({ path }: { path: string }) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    workspaceApi
      .fetchRawObjectUrl(sessionId, path)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load image");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sessionId, path]);

  const fileName = path.split("/").pop() || path;
  const download = () => {
    if (sessionId) void workspaceApi.downloadRawFile(sessionId, path);
  };

  if (loading && !url) return <ViewerSkeleton />;
  if (error && !url) return <ViewerError title="Couldn't load image" detail={error} />;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="image-artifact">
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
      <div className="flex flex-1 min-h-0 items-center justify-center overflow-auto p-4" style={CHECKER}>
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={fileName} className="max-h-full max-w-full object-contain" />
        ) : (
          <ImageOff className="h-6 w-6 text-muted-foreground" aria-hidden />
        )}
      </div>
    </div>
  );
}

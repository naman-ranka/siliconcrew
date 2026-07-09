"use client";

import { useEffect, useMemo } from "react";
import { Download } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ViewerError, ViewerSkeleton } from "./panels";

// Caps keep the DOM (and the parse) bounded — an engineering vector file can be
// huge. The header note stays honest: "showing N of M".
const MAX_ROWS = 500;
const MAX_COLS = 40;

function ext(path: string): string {
  const base = path.split("/").pop() ?? path;
  const i = base.lastIndexOf(".");
  return i >= 0 ? base.slice(i + 1).toLowerCase() : "";
}

/**
 * Minimal delimited parser — handles simple double-quoted fields (escaped `""`,
 * embedded delimiters and newlines). Not a full RFC-4180 implementation; enough
 * for the .csv/.tsv vectors this viewer targets. Parses the WHOLE buffer by
 * default (the smart-file reader already caps content at ~1MB, so counts stay
 * honest); callers can pass `maxRows` to bound it explicitly.
 */
export function parseDelimited(text: string, delim: string, maxRows = Number.MAX_SAFE_INTEGER): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === delim) {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      if (rows.length >= maxRows) return rows;
    } else if (c !== "\r") field += c;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/** Pretty-print JSON; on parse failure return the raw text (never throw). */
function prettyJson(text: string): { text: string; ok: boolean } {
  try {
    return { text: JSON.stringify(JSON.parse(text), null, 2), ok: true };
  } catch {
    return { text, ok: false };
  }
}

/**
 * v2 tab wrapper for `data:<path>` — CSV/TSV render as a capped table; JSON is
 * pretty-printed; YAML (and anything else) shows as monospace (already
 * human-readable, and we ship no YAML parser). Loads through the store's smart
 * file cache, same as the code viewer.
 */
export function DataArtifact({ path }: { path: string }) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const slice = useStore((s) => s.fileCache[path]);
  const loadFile = useStore((s) => s.loadFile);

  useEffect(() => {
    if (sessionId) void loadFile(path);
  }, [sessionId, path, loadFile]);

  const kind = ext(path);
  const file = slice?.file;
  const content = file?.content ?? null;

  const parsed = useMemo(() => {
    if (content == null) return null;
    if (kind === "csv" || kind === "tsv") {
      const rows = parseDelimited(content, kind === "tsv" ? "\t" : ",");
      const totalCols = rows.reduce((m, r) => Math.max(m, r.length), 0);
      return { type: "table" as const, rows, totalCols };
    }
    if (kind === "json") return { type: "text" as const, ...prettyJson(content) };
    return { type: "text" as const, text: content, ok: true };
  }, [content, kind]);

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
        onRetry={undefined}
      />
    );
  }

  const header = (note?: string) => (
    <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-surface-1 px-3 text-xs font-mono">
      <span className="truncate text-foreground">{fileName}</span>
      {note && <span className="shrink-0 text-[10px] text-muted-foreground">{note}</span>}
      <Button
        size="sm"
        variant="ghost"
        className="ml-auto h-6 gap-1 px-2 text-[11px] font-sans"
        onClick={download}
      >
        <Download className="h-3 w-3" /> Download
      </Button>
    </div>
  );

  if (parsed?.type === "table") {
    const rows = parsed.rows;
    const bodyRows = rows.slice(1, MAX_ROWS + 1);
    const dataRowCount = Math.max(rows.length - 1, 0);
    const clippedCols = parsed.totalCols > MAX_COLS;
    const clippedRows = dataRowCount > bodyRows.length;
    const note =
      clippedRows || clippedCols
        ? `showing ${bodyRows.length} of ${dataRowCount} rows${clippedCols ? `, ${MAX_COLS} of ${parsed.totalCols} cols` : ""}`
        : `${dataRowCount} rows`;
    const head = (rows[0] ?? []).slice(0, MAX_COLS);
    return (
      <div className="flex h-full min-h-0 flex-col" data-testid="data-artifact">
        {header(note)}
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-[11px] font-mono">
            <thead className="sticky top-0 bg-surface-1">
              <tr>
                {head.map((h, i) => (
                  <th
                    key={i}
                    className="border-b border-border px-2 py-1 text-left font-semibold text-foreground"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((r, ri) => (
                <tr key={ri} className="hover:bg-surface-2/50">
                  {head.map((_, ci) => (
                    <td key={ci} className="border-b border-border/50 px-2 py-1 text-muted-foreground">
                      {r[ci] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="data-artifact">
      {header(kind === "json" && parsed && !parsed.ok ? "invalid JSON — raw" : undefined)}
      <pre className="min-h-0 flex-1 overflow-auto whitespace-pre p-3 text-[12px] font-mono text-foreground">
        {parsed?.text ?? ""}
      </pre>
    </div>
  );
}

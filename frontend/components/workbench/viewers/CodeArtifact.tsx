"use client";

import { useEffect, useMemo, useState } from "react";
import Editor, { loader } from "@monaco-editor/react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Download, FileCode, Lock, Save } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ViewerError, ViewerSkeleton } from "./panels";

// Build outputs are read-only; only source files (workspace root & friends)
// are editable through the same store save path the v1 CodeViewer uses.
const READ_ONLY_PAT = /^(sim_runs|synth_runs)\//;

// Monaco language per extension (fallback: plaintext).
const LANG_BY_EXT: Record<string, string> = {
  v: "systemverilog",
  sv: "systemverilog",
  vh: "systemverilog",
  svh: "systemverilog",
  yaml: "yaml",
  yml: "yaml",
  json: "json",
  md: "markdown",
  py: "python",
  tcl: "tcl",
  sdc: "tcl",
  sh: "shell",
};

// Prism language for the no-Monaco fallback view.
const PRISM_BY_EXT: Record<string, string> = {
  v: "verilog",
  sv: "verilog",
  vh: "verilog",
  svh: "verilog",
  yaml: "yaml",
  yml: "yaml",
  json: "json",
  md: "markdown",
  py: "python",
};

function ext(path: string): string {
  const base = path.split("/").pop() ?? path;
  const i = base.lastIndexOf(".");
  return i >= 0 ? base.slice(i + 1).toLowerCase() : "";
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * v2 tab wrapper for `code:<path>` — loads through the store's smart file
 * cache, renders binary/oversized files honestly, and edits root source files
 * through the same `saveCodeFile` path the v1 CodeViewer uses.
 */
export function CodeArtifact({ path, forceReadOnly = false }: { path: string; forceReadOnly?: boolean }) {
  const currentSession = useStore((s) => s.currentSession);
  const slice = useStore((s) => s.fileCache[path]);
  const loadFile = useStore((s) => s.loadFile);
  const saveCodeFile = useStore((s) => s.saveCodeFile);
  const pushToast = useStore((s) => s.pushToast);

  // Build outputs are always read-only; the agent posture (prompt + view
  // only) forces read-only for EVERY file — editing is IDE-posture power.
  const readOnly = forceReadOnly || READ_ONLY_PAT.test(path);
  const sessionId = currentSession?.id ?? null;

  useEffect(() => {
    if (sessionId) void loadFile(path);
  }, [sessionId, path, loadFile]);

  // Monaco loads its workers from a CDN; on restricted networks fall back to a
  // highlighted read view / plain textarea (same pattern as the v1 CodeViewer).
  const [editorMode, setEditorMode] = useState<"loading" | "monaco" | "fallback">("loading");
  useEffect(() => {
    let done = false;
    const timer = setTimeout(() => {
      if (!done) setEditorMode((m) => (m === "loading" ? "fallback" : m));
    }, 4000);
    loader
      .init()
      .then(() => {
        done = true;
        setEditorMode("monaco");
      })
      .catch(() => {
        done = true;
        setEditorMode("fallback");
      });
    return () => clearTimeout(timer);
  }, []);

  // Draft/baseline for the edit loop. Adopt fresh server content whenever the
  // buffer isn't dirty (so a revalidate never clobbers in-progress edits).
  const [draft, setDraft] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const content = slice?.file?.content ?? null;
  const dirty = draft != null && baseline != null && draft !== baseline;
  useEffect(() => {
    if (content == null) return;
    if (draft == null || draft === baseline) {
      // Clean buffer (or first load) → adopt the fresh server content.
      setDraft(content);
      setBaseline(content);
    }
    // Dirty buffer → keep the user's edits; baseline stays put so the dirty
    // dot survives a background revalidate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content]);

  const language = LANG_BY_EXT[ext(path)] ?? "plaintext";
  const segments = path.split("/");
  const fileName = segments[segments.length - 1];

  const handleSave = async () => {
    if (readOnly || draft == null || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      await saveCodeFile(path, draft);
      setBaseline(draft);
      pushToast({ kind: "success", title: "Saved", detail: fileName });
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  // Ctrl/Cmd+S inside this tab only (keep-alive tabs each own their buffer).
  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      void handleSave();
    }
  };

  const download = async () => {
    if (!sessionId) return;
    try {
      await workspaceApi.downloadRawFile(sessionId, path);
    } catch (e) {
      pushToast({ kind: "error", title: "Download failed", detail: e instanceof Error ? e.message : undefined });
    }
  };

  const breadcrumb = useMemo(
    () =>
      segments.map((seg, i) => (
        <span key={i} className="flex items-center gap-1 min-w-0">
          {i > 0 && <span className="text-muted-foreground/50">›</span>}
          <span className={cn("truncate", i === segments.length - 1 ? "text-foreground" : "text-muted-foreground")}>
            {seg}
          </span>
        </span>
      )),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [path]
  );

  // ---- honest states ---------------------------------------------------
  if (!slice || (slice.status === "loading" && !slice.file)) {
    return <ViewerSkeleton />;
  }
  if (slice.status === "error" && !slice.file) {
    return (
      <ViewerError
        title="Couldn't load this file"
        detail={slice.error}
        onRetry={() => void loadFile(path)}
      />
    );
  }
  const file = slice.file;
  if (!file) return <ViewerSkeleton />;

  if (file.binary || file.tooLarge || file.content == null) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <div className="h-10 w-10 rounded-lg bg-surface-2 flex items-center justify-center mb-3">
          <FileCode className="h-5 w-5 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium text-foreground font-mono">{fileName}</p>
        <p className="text-xs mt-1 text-muted-foreground">
          {humanSize(file.size)} ·{" "}
          {file.binary ? "Binary file — not rendered" : "Too large to display"}
        </p>
        <Button size="sm" className="mt-4 gap-2" onClick={download}>
          <Download className="h-4 w-4" /> Download
        </Button>
      </div>
    );
  }

  const value = readOnly ? file.content : draft ?? file.content;

  return (
    <div className="flex flex-col h-full" onKeyDown={onKeyDown} data-testid="code-artifact">
      {/* Mini header: breadcrumb + dirty dot + save */}
      <div className="flex items-center gap-2 h-9 px-3 border-b border-border bg-surface-1 shrink-0 text-xs font-mono">
        <FileCode className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <div className="flex items-center gap-1 min-w-0">{breadcrumb}</div>
        {dirty && (
          <span
            className="h-1.5 w-1.5 rounded-full bg-status-warn shrink-0"
            title="Unsaved changes"
            data-testid="dirty-dot"
          />
        )}
        {saveError && <span className="text-[11px] text-destructive truncate">{saveError}</span>}
        <div className="ml-auto flex items-center gap-1 font-sans">
          {readOnly ? (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider">
              <Lock className="h-3 w-3" /> read-only
            </span>
          ) : (
            <Button
              size="sm"
              variant={dirty ? "default" : "ghost"}
              className="h-6 gap-1 text-[11px] px-2"
              onClick={() => void handleSave()}
              disabled={saving || !dirty}
              title="Save (Ctrl/Cmd+S)"
            >
              <Save className="h-3 w-3" /> {saving ? "Saving…" : "Save"}
            </Button>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 min-h-0 overflow-auto">
        {editorMode === "monaco" ? (
          <Editor
            height="100%"
            language={language}
            theme="vs-dark"
            value={value}
            onChange={readOnly ? undefined : (v) => setDraft(v ?? "")}
            options={{
              readOnly,
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: readOnly ? "on" : "off",
              automaticLayout: true,
            }}
          />
        ) : editorMode === "fallback" ? (
          readOnly ? (
            <SyntaxHighlighter
              language={PRISM_BY_EXT[ext(path)] ?? "text"}
              style={oneDark}
              showLineNumbers
              customStyle={{ margin: 0, minHeight: "100%", background: "transparent", fontSize: 13 }}
              codeTagProps={{ style: { fontFamily: "JetBrains Mono, monospace" } }}
            >
              {value}
            </SyntaxHighlighter>
          ) : (
            <textarea
              value={value}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              aria-label="Code editor"
              className="w-full h-full bg-surface-0 text-foreground font-mono text-[13px] p-4 resize-none outline-none"
            />
          )
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Loading editor…</div>
        )}
      </div>
    </div>
  );
}

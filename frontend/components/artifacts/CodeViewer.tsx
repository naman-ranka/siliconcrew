"use client";

import { useEffect, useState } from "react";
import { Code, RefreshCw, Copy, Check, Download, FileCode, Pencil, Save, X, FilePlus } from "lucide-react";
import Editor, { loader } from "@monaco-editor/react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/workbench/EmptyState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NEW_TEMPLATE = "module new_module (\n    input  clk,\n    input  rst\n);\n\nendmodule\n";

export function CodeViewer() {
  const {
    codeFiles,
    selectedCodeFile,
    loadCodeFiles,
    selectCodeFile,
    saveCodeFile,
    currentSession,
    codeLoading,
  } = useStore();
  const [copied, setCopied] = useState(false);
  // Monaco loads its worker bundle from a CDN; on restricted networks that is
  // blocked and the editor hangs forever on "Loading…". Fall back to a
  // syntax-highlighted view / plain textarea so the code tab always works.
  const [editorMode, setEditorMode] = useState<"loading" | "monaco" | "fallback">("loading");

  // In-app edit / create — the human "update code → re-run" loop.
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState("");
  const [baseline, setBaseline] = useState("");   // content at edit start (dirty tracking)
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const dirty = editing && draft !== baseline;

  useEffect(() => {
    if (currentSession) loadCodeFiles();
  }, [currentSession, loadCodeFiles]);

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

  const currentFile = codeFiles.find((f) => f.filename === selectedCodeFile);

  const handleCopy = () => {
    if (currentFile?.content) {
      navigator.clipboard.writeText(currentFile.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    if (currentFile) {
      const blob = new Blob([currentFile.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = currentFile.filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const startEdit = () => {
    setCreating(false);
    setDraft(currentFile?.content ?? "");
    setBaseline(currentFile?.content ?? "");
    setEditingFile(selectedCodeFile);
    setSaveError(null);
    setEditing(true);
  };

  const startNew = () => {
    setCreating(true);
    setNewName("");
    setDraft(NEW_TEMPLATE);
    setBaseline(NEW_TEMPLATE);
    setEditingFile(null);
    setSaveError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    if (dirty && !window.confirm("Discard unsaved changes?")) return;
    setEditing(false);
    setCreating(false);
    setSaveError(null);
  };

  // Ctrl/Cmd+S saves while editing.
  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void handleSave();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, draft, creating, newName, selectedCodeFile]);

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // Guard the data-loss trap: selecting another file in the tree while editing
  // with unsaved changes prompts instead of silently dropping the edit.
  useEffect(() => {
    if (!editing || creating) return;
    if (editingFile && selectedCodeFile !== editingFile) {
      if (dirty && !window.confirm(`Discard unsaved changes to ${editingFile}?`)) {
        selectCodeFile(editingFile); // restore the file being edited
      } else {
        setEditing(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCodeFile]);

  const handleSave = async () => {
    const name = creating ? newName.trim() : selectedCodeFile;
    if (!name) {
      setSaveError("Enter a filename (e.g. alu.v)");
      return;
    }
    if (!/\.(v|sv|vh|svh)$/i.test(name)) {
      setSaveError("Filename must end in .v / .sv / .vh / .svh");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await saveCodeFile(name, draft);
      selectCodeFile(name);
      setEditing(false);
      setCreating(false);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (codeFiles.length === 0 && !editing && codeLoading) {
    return (
      <div className="flex flex-col h-full" aria-hidden="true">
        <div className="flex items-center justify-between p-3 border-b border-border gap-2">
          <Skeleton className="h-8 w-[200px]" />
          <div className="flex items-center gap-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-7" />
            ))}
          </div>
        </div>
        <div className="flex-1 p-4 space-y-2">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-3" style={{ width: `${40 + ((i * 13) % 55)}%` }} />
          ))}
        </div>
      </div>
    );
  }

  if (codeFiles.length === 0 && !editing) {
    return (
      <EmptyState
        icon={<Code />}
        headline="No Verilog files yet"
        assistantHint="…or ask the assistant to implement a design for you."
        cta={
          <Button size="sm" variant="outline" className="gap-1.5" onClick={startNew} disabled={!currentSession}>
            <FilePlus className="h-4 w-4" /> New file
          </Button>
        }
      >
        Create a new file or upload existing Verilog to get started.
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {creating ? (
            <div className="flex flex-col">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="filename.v"
                aria-label="New filename"
                className="h-8 w-[200px] bg-surface-1 border border-border rounded px-2 text-xs font-mono outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              />
              <span className="text-[9px] text-muted-foreground mt-0.5">ends in .v · .sv · .vh · .svh</span>
            </div>
          ) : (
            <Select value={selectedCodeFile || ""} onValueChange={selectCodeFile} disabled={editing}>
              <SelectTrigger className="h-8 w-[200px]">
                <FileCode className="h-4 w-4 mr-2" />
                <SelectValue placeholder="Select file" />
              </SelectTrigger>
              <SelectContent>
                {codeFiles.map((file) => (
                  <SelectItem key={file.filename} value={file.filename}>
                    {file.filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {editing ? (
            <span className="text-[11px] flex items-center gap-1">
              <span className="text-primary">{creating ? "new file" : "editing"}</span>
              {dirty && (
                <span className="flex items-center gap-1 text-status-warn" title="Unsaved changes">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-warn" />
                  unsaved
                </span>
              )}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">
              {codeFiles.length} file{codeFiles.length !== 1 ? "s" : ""}
            </span>
          )}
          {saveError && <span className="text-[11px] text-destructive">{saveError}</span>}
        </div>
        <div className="flex items-center gap-1">
          {editing ? (
            <>
              <Button size="sm" className="h-7 gap-1 text-xs" onClick={handleSave} disabled={saving} title="Save (Ctrl/Cmd+S)">
                <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : dirty ? "Save •" : "Save"}
              </Button>
              <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={cancelEdit} disabled={saving}>
                <X className="h-3.5 w-3.5" /> Cancel
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="New file" onClick={startNew}>
                <FilePlus className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="Edit" onClick={startEdit} disabled={!currentFile}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="Refresh" onClick={() => loadCodeFiles()}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="Copy" onClick={handleCopy}>
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="Download" onClick={handleDownload} disabled={!currentFile}>
                <Download className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Editor / viewer */}
      <div className="flex-1 min-h-0 overflow-auto">
        {editing ? (
          editorMode === "monaco" ? (
            <Editor
              height="100%"
              language="systemverilog"
              theme="vs-dark"
              value={draft}
              onChange={(v) => setDraft(v ?? "")}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: "JetBrains Mono, monospace",
                lineNumbers: "on",
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          ) : (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              aria-label="Code editor"
              className="w-full h-full bg-surface-0 text-foreground font-mono text-[13px] p-4 resize-none outline-none"
            />
          )
        ) : currentFile && editorMode === "monaco" ? (
          <Editor
            height="100%"
            language="systemverilog"
            theme="vs-dark"
            value={currentFile.content}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
            }}
          />
        ) : currentFile && editorMode === "fallback" ? (
          <SyntaxHighlighter
            language="verilog"
            style={oneDark}
            showLineNumbers
            customStyle={{ margin: 0, height: "100%", background: "transparent", fontSize: 13 }}
            codeTagProps={{ style: { fontFamily: "JetBrains Mono, monospace" } }}
          >
            {currentFile.content}
          </SyntaxHighlighter>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Loading editor…</div>
        )}
      </div>
    </div>
  );
}

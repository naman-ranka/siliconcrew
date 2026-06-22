"use client";

import { useEffect, useState } from "react";
import { Code, RefreshCw, Copy, Check, Download, FileCode, Pencil, Save, X, FilePlus } from "lucide-react";
import Editor, { loader } from "@monaco-editor/react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
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
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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
    setSaveError(null);
    setEditing(true);
  };

  const startNew = () => {
    setCreating(true);
    setNewName("");
    setDraft(NEW_TEMPLATE);
    setSaveError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setCreating(false);
    setSaveError(null);
  };

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

  if (codeFiles.length === 0 && !editing) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <Code className="h-12 w-12 mb-4" />
        <p className="text-sm">No Verilog files yet</p>
        <p className="text-xs mt-1 mb-4">Upload, write, or ask the agent to implement a design</p>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={startNew} disabled={!currentSession}>
          <FilePlus className="h-4 w-4" /> New file
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {creating ? (
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="filename.v"
              aria-label="New filename"
              className="h-8 w-[200px] bg-surface-1 border border-border rounded px-2 text-xs font-mono"
            />
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
            <span className="text-[11px] text-primary">{creating ? "new file" : "editing"}</span>
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
              <Button size="sm" className="h-7 gap-1 text-xs" onClick={handleSave} disabled={saving}>
                <Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save"}
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

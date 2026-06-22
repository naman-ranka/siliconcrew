"use client";

import { useEffect, useState } from "react";
import { Code, RefreshCw, Copy, Check, Download, FileCode } from "lucide-react";
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

export function CodeViewer() {
  const {
    codeFiles,
    selectedCodeFile,
    loadCodeFiles,
    selectCodeFile,
    currentSession,
  } = useStore();
  const [copied, setCopied] = useState(false);
  // Monaco loads its worker bundle from a CDN; on restricted networks that is
  // blocked and the editor hangs forever on "Loading…". Fall back to a
  // read-only syntax-highlighted view so the (secondary) code tab always works.
  const [editorMode, setEditorMode] = useState<"loading" | "monaco" | "fallback">("loading");

  useEffect(() => {
    if (currentSession) {
      loadCodeFiles();
    }
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

  const handleDownloadAll = () => {
    // Simple concatenation for now
    const allContent = codeFiles
      .map((f) => `// === ${f.filename} ===\n${f.content}`)
      .join("\n\n");
    const blob = new Blob([allContent], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "all_files.v";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (codeFiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <Code className="h-12 w-12 mb-4" />
        <p className="text-sm">No Verilog files yet</p>
        <p className="text-xs mt-1">
          Ask the agent to implement a design to see code here
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Select value={selectedCodeFile || ""} onValueChange={selectCodeFile}>
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
          <span className="text-xs text-muted-foreground">
            {codeFiles.length} file{codeFiles.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => loadCodeFiles()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleCopy}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleDownload}
          >
            <Download className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Editor (Monaco when available; highlighted fallback otherwise) */}
      <div className="flex-1 min-h-0 overflow-auto">
        {currentFile && editorMode === "monaco" && (
          <Editor
            height="100%"
            language="systemverilog"
            theme="vs-dark"
            value={currentFile.content}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, Fira Code, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
            }}
          />
        )}
        {currentFile && editorMode === "fallback" && (
          <SyntaxHighlighter
            language="verilog"
            style={oneDark}
            showLineNumbers
            customStyle={{ margin: 0, height: "100%", background: "transparent", fontSize: 13 }}
            codeTagProps={{ style: { fontFamily: "JetBrains Mono, monospace" } }}
          >
            {currentFile.content}
          </SyntaxHighlighter>
        )}
        {currentFile && editorMode === "loading" && (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            Loading editor…
          </div>
        )}
      </div>
    </div>
  );
}

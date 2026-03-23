"use client";

import { useEffect } from "react";
import { FileText, RefreshCw, Download, FileOutput } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

export function ReportViewer() {
  const {
    report,
    loadReport,
    generateReport,
    currentSession,
    synthesisRuns,
    selectedSynthesisRunId,
    selectSynthesisRun,
    loadSynthesisRuns,
  } = useStore();

  useEffect(() => {
    if (currentSession) {
      loadSynthesisRuns();
      loadReport();
    }
  }, [currentSession, loadReport, loadSynthesisRuns]);

  const handleDownload = () => {
    if (report) {
      const blob = new Blob([report.content], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = report.filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const handleGenerate = async () => {
    try {
      await generateReport(selectedSynthesisRunId);
    } catch (error) {
      console.error("Failed to generate report:", error);
    }
  };

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8">
        <div className="w-16 h-16 rounded-2xl bg-surface-2 flex items-center justify-center mb-4">
          <FileText className="h-8 w-8" />
        </div>
        <p className="text-sm font-medium">No report yet</p>
        <p className="text-xs mt-1 mb-6 text-center max-w-[200px]">
          Generate a report for the latest synthesis run to get a summary with metrics and analysis
        </p>
        {synthesisRuns.length > 0 && (
          <div className="mb-4 w-full max-w-[260px]">
            <Select value={selectedSynthesisRunId || synthesisRuns[0]?.run_id} onValueChange={selectSynthesisRun}>
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder="Select synthesis run" />
              </SelectTrigger>
              <SelectContent>
                {synthesisRuns.map((run) => (
                  <SelectItem key={run.run_id} value={run.run_id} className="text-xs">
                    {run.run_id} · {run.status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <Button onClick={handleGenerate} size="sm" className="gap-2">
          <FileOutput className="h-4 w-4" />
          Generate Report
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-1">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium truncate">{report.filename}</span>
          {report.run_id && (
            <span className="text-[11px] text-muted-foreground bg-surface-2 px-2 py-0.5 rounded-full">
              {report.run_id}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {synthesisRuns.length > 0 && (
            <Select value={selectedSynthesisRunId || synthesisRuns[0]?.run_id} onValueChange={selectSynthesisRun}>
              <SelectTrigger className="h-7 w-[170px] text-xs mr-1">
                <SelectValue placeholder="Select synthesis run" />
              </SelectTrigger>
              <SelectContent>
                {synthesisRuns.map((run) => (
                  <SelectItem key={run.run_id} value={run.run_id} className="text-xs">
                    {run.run_id} · {run.status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 hover:bg-surface-2"
            onClick={() => {
              loadSynthesisRuns();
              loadReport(selectedSynthesisRunId);
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 hover:bg-surface-2"
            onClick={handleDownload}
          >
            <Download className="h-3.5 w-3.5" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleGenerate} className="ml-1 h-7 text-xs">
            <FileOutput className="h-3 w-3 mr-1" />
            Regenerate
          </Button>
        </div>
      </div>

      {/* Content - Using native overflow for better scroll */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <div className="p-6 prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                const isInline = !match;

                if (isInline) {
                  return (
                    <code
                      className="bg-surface-2 text-primary px-1.5 py-0.5 rounded text-sm font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                }

                return (
                  <div className="rounded-lg overflow-hidden border border-border my-4">
                    <div className="flex items-center px-4 py-2 bg-surface-2 border-b border-border">
                      <span className="text-xs text-muted-foreground font-mono">{match[1]}</span>
                    </div>
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        margin: 0,
                        padding: "1rem",
                        background: "hsl(var(--surface-1))",
                        fontSize: "0.8125rem",
                      }}
                    >
                      {String(children).replace(/\n$/, "")}
                    </SyntaxHighlighter>
                  </div>
                );
              },
              table({ children }) {
                return (
                  <div className="overflow-x-auto my-4 rounded-lg border border-border">
                    <table className="min-w-full divide-y divide-border">{children}</table>
                  </div>
                );
              },
              thead({ children }) {
                return <thead className="bg-surface-2">{children}</thead>;
              },
              th({ children }) {
                return (
                  <th className="px-4 py-3 text-left text-xs font-semibold text-foreground uppercase tracking-wider whitespace-nowrap">
                    {children}
                  </th>
                );
              },
              td({ children }) {
                return <td className="px-4 py-3 text-sm whitespace-nowrap">{children}</td>;
              },
              h1({ children }) {
                return (
                  <h1 className="text-xl font-semibold mt-8 mb-4 pb-2 border-b border-border first:mt-0">
                    {children}
                  </h1>
                );
              },
              h2({ children }) {
                return <h2 className="text-lg font-semibold mt-6 mb-3">{children}</h2>;
              },
              h3({ children }) {
                return <h3 className="text-base font-semibold mt-4 mb-2">{children}</h3>;
              },
              p({ children }) {
                return <p className="my-3 leading-relaxed text-foreground">{children}</p>;
              },
              ul({ children }) {
                return <ul className="list-disc pl-6 space-y-1 my-3">{children}</ul>;
              },
              ol({ children }) {
                return <ol className="list-decimal pl-6 space-y-1 my-3">{children}</ol>;
              },
              li({ children }) {
                return <li className="text-foreground">{children}</li>;
              },
              strong({ children }) {
                return <strong className="font-semibold text-foreground">{children}</strong>;
              },
              em({ children }) {
                return <em className="italic text-muted-foreground">{children}</em>;
              },
              blockquote({ children }) {
                return (
                  <blockquote className="border-l-4 border-primary pl-4 my-4 italic text-muted-foreground bg-surface-1 py-2 rounded-r">
                    {children}
                  </blockquote>
                );
              },
              hr() {
                return <hr className="my-6 border-border" />;
              },
              a({ href, children }) {
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {report.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";
import { FileText, RefreshCw, Download, FileOutput } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useStore } from "@/lib/store";
import { PpaHero } from "./PpaHero";
import { EmptyState } from "@/components/workbench/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
    runs,
    selectedRunId,
    reportLoading,
  } = useStore();

  // PPA hero sources the unified run record (has ppa); prefer the report's run.
  const ppaRunId = report?.run_id ?? selectedRunId ?? selectedSynthesisRunId;

  // The run we'd target for (auto-)generation: the selected synth run, else the
  // newest passed synth run.
  const passedSynth = runs.find((r) => r.kind === "synth" && r.status === "passed");
  const targetGenRunId = selectedSynthesisRunId ?? passedSynth?.id ?? null;

  useEffect(() => {
    if (currentSession) {
      loadSynthesisRuns();
      loadReport();
    }
  }, [currentSession, loadReport, loadSynthesisRuns]);

  // Auto-generate the report once when a synth has passed but no markdown report
  // exists yet — a successful tape-out should show its summary without a click.
  const autoGenTriedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!currentSession || report || reportLoading) return;
    if (!passedSynth || !targetGenRunId) return;
    if (autoGenTriedRef.current === targetGenRunId) return;
    autoGenTriedRef.current = targetGenRunId;
    void generateReport(targetGenRunId).catch(() => {
      /* keep the empty state with its manual Generate button as a fallback */
    });
  }, [currentSession, report, reportLoading, passedSynth, targetGenRunId, generateReport]);

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

  if (!report && reportLoading) {
    return (
      <div className="flex flex-col h-full p-6 gap-4" aria-hidden="true">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-11/12" />
        <Skeleton className="h-3 w-4/5" />
        <Skeleton className="h-32 w-full mt-2" />
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    );
  }

  if (!report) {
    const hasPpa = runs.some((r) => r.kind === "synth" && r.ppa);
    // If a synth has passed, the report can be generated *now* — say so, and
    // name the run we'd generate it for (the old copy wrongly told the user to
    // "run synthesis" even after it had succeeded).
    const genRunId = targetGenRunId ?? synthesisRuns[0]?.run_id;
    return (
      <EmptyState
        // Even without a generated markdown report, surface PPA if a synth run exists.
        header={hasPpa ? <PpaHero runs={runs} runId={ppaRunId} /> : undefined}
        icon={<FileText />}
        headline={passedSynth ? "Generating report…" : "No report yet"}
        assistantHint={
          passedSynth ? (
            <>The timing/PPA summary above is live; the full markdown report is being generated.</>
          ) : (
            <>
              Synthesis runs the OpenROAD flow; if ORFS isn&apos;t available the
              synth step reports that in the console.
            </>
          )
        }
        cta={
          <>
            {synthesisRuns.length > 0 && (
              <div className="w-full max-w-[260px]">
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
              {genRunId ? `Generate the report for ${genRunId}` : "Generate Report"}
            </Button>
          </>
        }
      >
        {passedSynth
          ? `Synthesis passed${targetGenRunId ? ` (${targetGenRunId})` : ""} — building the timing/PPA summary and spec-vs-result analysis.`
          : "Run synthesis, then generate a report to get the timing/PPA summary and spec-vs-result analysis."}
      </EmptyState>
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
        {/* Timing-hero + PPA + compare-vs-previous (the artifact-first star) */}
        <PpaHero runs={runs} runId={ppaRunId} />
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

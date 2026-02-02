"use client";

import { useEffect } from "react";
import { FileText, RefreshCw, Download, FileOutput } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

export function ReportViewer() {
  const { report, loadReport, generateReport, currentSession } = useStore();

  useEffect(() => {
    if (currentSession) {
      loadReport();
    }
  }, [currentSession, loadReport]);

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
      await generateReport();
    } catch (error) {
      console.error("Failed to generate report:", error);
    }
  };

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <FileText className="h-12 w-12 mb-4" />
        <p className="text-sm">No report yet</p>
        <p className="text-xs mt-1 mb-4">
          Generate a report to summarize your design
        </p>
        <Button onClick={handleGenerate} size="sm">
          <FileOutput className="h-4 w-4 mr-2" />
          Generate Report
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4" />
          <span className="text-sm font-medium">{report.filename}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => loadReport()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleDownload}
          >
            <Download className="h-3.5 w-3.5" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleGenerate}>
            <FileOutput className="h-3.5 w-3.5 mr-1" />
            Regenerate
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ node, ...props }) => (
                <div className="overflow-x-auto">
                  <table className="min-w-full" {...props} />
                </div>
              ),
              code({ node, className, children, ...props }) {
                return (
                  <code
                    className="bg-muted px-1.5 py-0.5 rounded text-sm"
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
            }}
          >
            {report.content}
          </ReactMarkdown>
        </div>
      </ScrollArea>
    </div>
  );
}

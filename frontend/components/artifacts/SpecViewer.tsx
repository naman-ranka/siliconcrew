"use client";

import { useEffect, useState } from "react";
import { FileText, RefreshCw, Copy, Check, Download, ArrowUpDown, ArrowRightLeft } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export function SpecViewer() {
  const { spec, loadSpec, currentSession } = useStore();
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"formatted" | "raw">("formatted");

  useEffect(() => {
    if (currentSession) {
      loadSpec();
    }
  }, [currentSession, loadSpec]);

  const handleCopy = () => {
    if (spec?.content) {
      navigator.clipboard.writeText(spec.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    if (spec) {
      const blob = new Blob([spec.content], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = spec.filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  if (!spec) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8">
        <div className="w-16 h-16 rounded-2xl bg-surface-2 flex items-center justify-center mb-4">
          <FileText className="h-8 w-8" />
        </div>
        <p className="text-sm font-medium">No specification yet</p>
        <p className="text-xs mt-1 text-center max-w-[200px]">
          Ask the agent to design something to see the hardware specification here
        </p>
      </div>
    );
  }

  const parsed = spec.parsed as Record<string, Record<string, unknown>> | null;
  const moduleName = parsed ? Object.keys(parsed)[0] : "unknown";
  const moduleSpec = parsed ? (parsed[moduleName] as Record<string, unknown>) : null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-1">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{spec.filename}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7 hover:bg-surface-2" onClick={() => loadSpec()}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 hover:bg-surface-2" onClick={handleCopy}>
            {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 hover:bg-surface-2" onClick={handleDownload}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* View toggle */}
      <div className="px-4 py-2 border-b border-border bg-surface-0">
        <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)}>
          <TabsList className="h-8 bg-surface-1">
            <TabsTrigger value="formatted" className="text-xs h-7 px-3">
              Formatted
            </TabsTrigger>
            <TabsTrigger value="raw" className="text-xs h-7 px-3">
              Raw YAML
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Content - Using native overflow for better scroll */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {viewMode === "formatted" && moduleSpec ? (
          <div className="p-4 space-y-6">
            {/* Module header */}
            <div className="p-4 rounded-lg bg-surface-1 border border-border">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">{moduleName}</h2>
                  <p className="text-xs text-muted-foreground">Hardware Module Specification</p>
                </div>
              </div>
              {"description" in moduleSpec && moduleSpec.description ? (
                <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
                  {String(moduleSpec.description)}
                </p>
              ) : null}
            </div>

            {/* Properties grid */}
            <div className="grid grid-cols-2 gap-3">
              {"clock_period" in moduleSpec && moduleSpec.clock_period ? (
                <div className="p-3 rounded-lg bg-surface-1 border border-border">
                  <p className="text-xs text-muted-foreground mb-1">Clock Period</p>
                  <p className="font-semibold text-lg">{String(moduleSpec.clock_period)}<span className="text-sm font-normal text-muted-foreground ml-1">ns</span></p>
                </div>
              ) : null}
              {"tech_node" in moduleSpec && moduleSpec.tech_node ? (
                <div className="p-3 rounded-lg bg-surface-1 border border-border">
                  <p className="text-xs text-muted-foreground mb-1">Tech Node</p>
                  <p className="font-semibold">{String(moduleSpec.tech_node)}</p>
                </div>
              ) : null}
            </div>

            {/* Ports table */}
            {"ports" in moduleSpec && Array.isArray(moduleSpec.ports) && moduleSpec.ports.length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <ArrowRightLeft className="h-4 w-4 text-primary" />
                  Ports
                  <span className="text-xs font-normal text-muted-foreground">({moduleSpec.ports.length} total)</span>
                </h3>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-surface-2">
                      <tr>
                        <th className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider">Name</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider">Direction</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider">Width</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider">Description</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {(moduleSpec.ports as any[]).map((port: any, idx: number) => (
                        <tr key={idx} className="hover:bg-surface-1 transition-colors">
                          <td className="px-4 py-2.5">
                            <code className="text-xs bg-surface-2 text-primary px-1.5 py-0.5 rounded font-mono">
                              {port.name}
                            </code>
                          </td>
                          <td className="px-4 py-2.5">
                            <span
                              className={cn(
                                "inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium",
                                port.direction === "input"
                                  ? "bg-blue-500/10 text-blue-400"
                                  : "bg-green-500/10 text-green-400"
                              )}
                            >
                              {port.direction}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-muted-foreground font-mono text-xs">
                            [{port.width || 1}]
                          </td>
                          <td className="px-4 py-2.5 text-muted-foreground text-xs max-w-[200px] truncate">
                            {port.description || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {/* Module signature */}
            {"module_signature" in moduleSpec && moduleSpec.module_signature ? (
              <div>
                <h3 className="text-sm font-semibold mb-3">Module Signature</h3>
                <div className="rounded-lg overflow-hidden border border-border">
                  <div className="bg-surface-2 px-4 py-2 border-b border-border">
                    <span className="text-xs text-muted-foreground font-mono">verilog</span>
                  </div>
                  <pre className="bg-surface-1 p-4 text-xs font-mono overflow-x-auto">
                    {String(moduleSpec.module_signature)}
                  </pre>
                </div>
              </div>
            ) : null}

            {/* Parameters */}
            {"parameters" in moduleSpec && moduleSpec.parameters && typeof moduleSpec.parameters === "object" && Object.keys(moduleSpec.parameters as object).length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold mb-3">Parameters</h3>
                <div className="rounded-lg overflow-hidden border border-border">
                  <div className="bg-surface-2 px-4 py-2 border-b border-border">
                    <span className="text-xs text-muted-foreground font-mono">json</span>
                  </div>
                  <pre className="bg-surface-1 p-4 text-xs font-mono overflow-x-auto">
                    {JSON.stringify(moduleSpec.parameters, null, 2)}
                  </pre>
                </div>
              </div>
            ) : null}

            {/* Behavioral description */}
            {"behavioral_description" in moduleSpec && moduleSpec.behavioral_description ? (
              <div>
                <h3 className="text-sm font-semibold mb-3">Behavioral Description</h3>
                <div className="p-4 rounded-lg bg-surface-1 border border-border">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                    {String(moduleSpec.behavioral_description)}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="p-4">
            <div className="rounded-lg overflow-hidden border border-border">
              <div className="bg-surface-2 px-4 py-2 border-b border-border">
                <span className="text-xs text-muted-foreground font-mono">yaml</span>
              </div>
              <pre className="bg-surface-1 p-4 text-xs font-mono whitespace-pre-wrap overflow-x-auto">
                {spec.content}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

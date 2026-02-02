"use client";

import { useEffect, useState } from "react";
import { FileText, RefreshCw, Copy, Check, Download } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <FileText className="h-12 w-12 mb-4" />
        <p className="text-sm">No specification yet</p>
        <p className="text-xs mt-1">
          Ask the agent to design something to see specs here
        </p>
      </div>
    );
  }

  const parsed = spec.parsed;
  const moduleName = parsed ? Object.keys(parsed)[0] : "unknown";
  const moduleSpec = parsed ? parsed[moduleName] : null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4" />
          <span className="text-sm font-medium">{spec.filename}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => loadSpec()}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy}>
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleDownload}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* View toggle */}
      <div className="p-2 border-b border-border">
        <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)}>
          <TabsList className="h-8">
            <TabsTrigger value="formatted" className="text-xs h-6">
              Formatted
            </TabsTrigger>
            <TabsTrigger value="raw" className="text-xs h-6">
              Raw YAML
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {viewMode === "formatted" && moduleSpec ? (
          <div className="p-4 space-y-6">
            {/* Module header */}
            <div>
              <h2 className="text-lg font-semibold">{moduleName}</h2>
              {moduleSpec.description && (
                <p className="text-sm text-muted-foreground mt-1">
                  {moduleSpec.description}
                </p>
              )}
            </div>

            {/* Properties */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              {moduleSpec.clock_period && (
                <div>
                  <p className="text-xs text-muted-foreground">Clock Period</p>
                  <p className="font-medium">{moduleSpec.clock_period} ns</p>
                </div>
              )}
              {moduleSpec.tech_node && (
                <div>
                  <p className="text-xs text-muted-foreground">Tech Node</p>
                  <p className="font-medium">{moduleSpec.tech_node}</p>
                </div>
              )}
            </div>

            {/* Ports table */}
            {moduleSpec.ports && moduleSpec.ports.length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2">Ports</h3>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left p-2 font-medium">Name</th>
                        <th className="text-left p-2 font-medium">Dir</th>
                        <th className="text-left p-2 font-medium">Width</th>
                        <th className="text-left p-2 font-medium">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(moduleSpec.ports as any[]).map((port: any, idx: number) => (
                        <tr key={idx} className="border-t border-border">
                          <td className="p-2">
                            <code className="text-xs bg-muted px-1 rounded">
                              {port.name}
                            </code>
                          </td>
                          <td className="p-2">
                            <span
                              className={cn(
                                "text-xs px-1.5 py-0.5 rounded",
                                port.direction === "input"
                                  ? "bg-blue-500/20 text-blue-400"
                                  : "bg-green-500/20 text-green-400"
                              )}
                            >
                              {port.direction}
                            </span>
                          </td>
                          <td className="p-2 text-muted-foreground">
                            {port.width || 1}
                          </td>
                          <td className="p-2 text-muted-foreground text-xs">
                            {port.description || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Module signature */}
            {moduleSpec.module_signature && (
              <div>
                <h3 className="text-sm font-medium mb-2">Module Signature</h3>
                <pre className="bg-muted p-3 rounded-lg text-xs overflow-x-auto">
                  {moduleSpec.module_signature}
                </pre>
              </div>
            )}

            {/* Parameters */}
            {moduleSpec.parameters && Object.keys(moduleSpec.parameters).length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2">Parameters</h3>
                <pre className="bg-muted p-3 rounded-lg text-xs overflow-x-auto">
                  {JSON.stringify(moduleSpec.parameters, null, 2)}
                </pre>
              </div>
            )}

            {/* Behavioral description */}
            {moduleSpec.behavioral_description && (
              <div>
                <h3 className="text-sm font-medium mb-2">Behavior</h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {moduleSpec.behavioral_description}
                </p>
              </div>
            )}
          </div>
        ) : (
          <pre className="p-4 text-xs font-mono whitespace-pre-wrap">
            {spec.content}
          </pre>
        )}
      </ScrollArea>
    </div>
  );
}

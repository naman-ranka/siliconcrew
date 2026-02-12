"use client";

import { X, Minimize2, FileText, Code, Activity, Layout, BarChart3, CircuitBoard, PanelRightClose } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SpecViewer } from "./SpecViewer";
import { CodeViewer } from "./CodeViewer";
import { WaveformViewer } from "./WaveformViewer";
import { SchematicViewer } from "./SchematicViewer";
import { ReportViewer } from "./ReportViewer";
import { LayoutViewer } from "./LayoutViewer";
import { cn } from "@/lib/utils";
import type { ArtifactTab } from "@/types";

export function ArtifactsPanel() {
  const {
    artifactsVisible,
    activeArtifactTab,
    setArtifactTab,
    toggleArtifacts,
    spec,
    codeFiles,
    waveformFiles,
    schematicFiles,
    layoutFiles,
    report,
  } = useStore();

  if (!artifactsVisible) {
    return null;
  }

  const tabs: { id: ArtifactTab; label: string; icon: React.ReactNode; badge?: number }[] = [
    {
      id: "spec",
      label: "Spec",
      icon: <FileText className="h-3.5 w-3.5" />,
      badge: spec ? 1 : 0,
    },
    {
      id: "code",
      label: "Code",
      icon: <Code className="h-3.5 w-3.5" />,
      badge: codeFiles.length,
    },
    {
      id: "waveform",
      label: "Wave",
      icon: <Activity className="h-3.5 w-3.5" />,
      badge: waveformFiles.length,
    },
    {
      id: "schematic",
      label: "Schem",
      icon: <CircuitBoard className="h-3.5 w-3.5" />,
      badge: schematicFiles.length,
    },
    {
      id: "layout",
      label: "Layout",
      icon: <Layout className="h-3.5 w-3.5" />,
      badge: layoutFiles.length,
    },
    {
      id: "report",
      label: "Report",
      icon: <BarChart3 className="h-3.5 w-3.5" />,
      badge: report ? 1 : 0,
    },
  ];

  const totalArtifacts = (spec ? 1 : 0) + codeFiles.length + waveformFiles.length + schematicFiles.length + layoutFiles.length + (report ? 1 : 0);

  return (
    <div className="flex flex-col h-full bg-surface-0 border-l border-border animate-slide-in-right">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border bg-surface-1">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-sm">Artifacts</h2>
          {totalArtifacts > 0 && (
            <span className="text-xs text-muted-foreground bg-surface-2 px-2 py-0.5 rounded-full">
              {totalArtifacts}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 hover:bg-surface-2" onClick={toggleArtifacts}>
                <PanelRightClose className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Hide panel (⌘])</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        value={activeArtifactTab}
        onValueChange={(v) => setArtifactTab(v as ArtifactTab)}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsList className="justify-start rounded-none border-b border-border h-11 px-2 bg-surface-0 gap-1">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className={cn(
                "relative px-2.5 py-1.5 gap-1.5 rounded-md transition-all",
                "data-[state=active]:bg-surface-2 data-[state=active]:shadow-sm",
                "hover:bg-surface-1"
              )}
            >
              <span className={cn(
                activeArtifactTab === tab.id ? "text-primary" : "text-muted-foreground"
              )}>
                {tab.icon}
              </span>
              <span className="text-xs">{tab.label}</span>
              {tab.badge !== undefined && tab.badge > 0 && (
                <span className={cn(
                  "ml-1 h-4 min-w-[16px] px-1 rounded-full text-[10px] font-medium flex items-center justify-center",
                  activeArtifactTab === tab.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-surface-2 text-muted-foreground"
                )}>
                  {tab.badge}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="spec" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <SpecViewer />
        </TabsContent>

        <TabsContent value="code" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <CodeViewer />
        </TabsContent>

        <TabsContent value="waveform" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <WaveformViewer />
        </TabsContent>

        <TabsContent value="schematic" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <SchematicViewer />
        </TabsContent>

        <TabsContent value="layout" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <LayoutViewer />
        </TabsContent>

        <TabsContent value="report" className="flex-1 m-0 data-[state=inactive]:hidden overflow-hidden">
          <ReportViewer />
        </TabsContent>
      </Tabs>
    </div>
  );
}

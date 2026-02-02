"use client";

import { X, Minimize2, FileText, Code, Activity, Layout, BarChart3 } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SpecViewer } from "./SpecViewer";
import { CodeViewer } from "./CodeViewer";
import { WaveformViewer } from "./WaveformViewer";
import { ReportViewer } from "./ReportViewer";
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
    report,
  } = useStore();

  if (!artifactsVisible) {
    return null;
  }

  const tabs: { id: ArtifactTab; label: string; icon: React.ReactNode; badge?: number }[] = [
    {
      id: "spec",
      label: "Spec",
      icon: <FileText className="h-4 w-4" />,
      badge: spec ? 1 : 0,
    },
    {
      id: "code",
      label: "Code",
      icon: <Code className="h-4 w-4" />,
      badge: codeFiles.length,
    },
    {
      id: "waveform",
      label: "Wave",
      icon: <Activity className="h-4 w-4" />,
      badge: waveformFiles.length,
    },
    {
      id: "layout",
      label: "Layout",
      icon: <Layout className="h-4 w-4" />,
    },
    {
      id: "report",
      label: "Report",
      icon: <BarChart3 className="h-4 w-4" />,
      badge: report ? 1 : 0,
    },
  ];

  return (
    <div className="flex flex-col h-full bg-background border-l border-border">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border">
        <h2 className="font-semibold">Artifacts</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggleArtifacts}>
            <Minimize2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggleArtifacts}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        value={activeArtifactTab}
        onValueChange={(v) => setArtifactTab(v as ArtifactTab)}
        className="flex-1 flex flex-col"
      >
        <TabsList className="justify-start rounded-none border-b border-border h-10 px-2 bg-transparent">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className="relative data-[state=active]:bg-muted rounded-t-md rounded-b-none px-3 gap-1.5"
            >
              {tab.icon}
              <span className="text-xs">{tab.label}</span>
              {tab.badge && tab.badge > 0 && (
                <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-primary text-[10px] text-primary-foreground flex items-center justify-center">
                  {tab.badge}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="spec" className="flex-1 m-0 data-[state=inactive]:hidden">
          <SpecViewer />
        </TabsContent>

        <TabsContent value="code" className="flex-1 m-0 data-[state=inactive]:hidden">
          <CodeViewer />
        </TabsContent>

        <TabsContent value="waveform" className="flex-1 m-0 data-[state=inactive]:hidden">
          <WaveformViewer />
        </TabsContent>

        <TabsContent value="layout" className="flex-1 m-0 data-[state=inactive]:hidden">
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <Layout className="h-12 w-12 mb-4" />
            <p className="text-sm">Layout viewer</p>
            <p className="text-xs mt-1">
              GDS files will be displayed here after synthesis
            </p>
          </div>
        </TabsContent>

        <TabsContent value="report" className="flex-1 m-0 data-[state=inactive]:hidden">
          <ReportViewer />
        </TabsContent>
      </Tabs>
    </div>
  );
}

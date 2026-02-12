"use client";

import { useEffect, useState } from "react";
import { Layout as LayoutIcon, Loader2, AlertCircle } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function LayoutViewer() {
  const { currentSession, layoutFiles, selectedLayout, selectLayout } = useStore();
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [cellName, setCellName] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);

  useEffect(() => {
    if (currentSession && selectedLayout) {
      loadLayout(selectedLayout);
    } else if (!selectedLayout && layoutFiles.length > 0) {
      // Auto-select first layout
      selectLayout(layoutFiles[0]);
    }
  }, [selectedLayout, currentSession]);

  const loadLayout = async (filename: string) => {
    if (!currentSession) return;

    setLoading(true);
    setError(null);
    setWarningMessage(null);

    try {
      const data = await workspaceApi.getLayout(currentSession.id, filename);
      
      // Check for size-related errors
      if ((data as any).error) {
        const errorData = data as any;
        if (errorData.error === "too_large" || errorData.error === "svg_too_large") {
          setError(errorData.message);
          setSvgContent(null);
          setCellName(errorData.cell_name || "");
        } else {
          setError(errorData.message || "Unknown error");
        }
        return;
      }
      
      setSvgContent(data.svg);
      setCellName(data.cell_name);
      
      // Show cache indicator if applicable
      if ((data as any).cached) {
        setWarningMessage("Displaying cached layout");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load layout");
      setSvgContent(null);
    } finally {
      setLoading(false);
    }
  };

  const handleLayoutChange = (filename: string) => {
    selectLayout(filename);
  };

  if (layoutFiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8">
        <div className="w-16 h-16 rounded-2xl bg-surface-2 flex items-center justify-center mb-4">
          <LayoutIcon className="h-8 w-8" />
        </div>
        <p className="text-sm font-medium">No Layout Files</p>
        <p className="text-xs mt-1 text-center max-w-[280px]">
          GDS layout files will appear here after synthesis. Ask the agent to run synthesis on your design.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b border-border bg-surface-1">
        <LayoutIcon className="h-4 w-4 text-muted-foreground" />
        <Select value={selectedLayout || layoutFiles[0]} onValueChange={handleLayoutChange}>
          <SelectTrigger className="flex-1 h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {layoutFiles.map((file) => (
              <SelectItem key={file} value={file} className="text-xs">
                {file}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {cellName && (
          <span className="text-xs text-muted-foreground px-2 py-1 bg-surface-2 rounded">
            {cellName}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {warningMessage && !error && (
          <div className="p-2 bg-yellow-500/10 border-b border-yellow-500/20 text-yellow-600 dark:text-yellow-500 text-xs text-center">
            {warningMessage}
          </div>
        )}
        
        {loading && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8">
            <div className="w-16 h-16 rounded-2xl bg-surface-2 flex items-center justify-center mb-4">
              <AlertCircle className="h-8 w-8 text-destructive" />
            </div>
            <p className="text-sm font-medium text-destructive">Cannot Display Layout</p>
            <p className="text-xs mt-1 text-center max-w-[320px]">{error}</p>
            {cellName && (
              <p className="text-xs mt-2 text-muted-foreground">Cell: {cellName}</p>
            )}
            {!error.includes("too large") && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => selectedLayout && loadLayout(selectedLayout)}
              >
                Retry
              </Button>
            )}
          </div>
        )}

        {svgContent && !loading && !error && (
          <div className="p-4 bg-white dark:bg-surface-0">
            <div
              className="w-full h-full flex items-center justify-center"
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

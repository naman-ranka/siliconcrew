"use client";

import { useEffect, useState } from "react";
import { CircuitBoard, RefreshCw, Download, ZoomIn, ZoomOut } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { workspaceApi } from "@/lib/api";

export function SchematicViewer() {
  const { currentSession } = useStore();
  const [schematicFiles, setSchematicFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (currentSession) {
      loadSchematicFiles();
    }
  }, [currentSession]);

  const loadSchematicFiles = async () => {
    if (!currentSession) return;
    try {
      const files = await workspaceApi.listSchematics(currentSession.id);
      setSchematicFiles(files);
      if (files.length > 0 && !selectedFile) {
        setSelectedFile(files[0]);
      }
    } catch {
      setSchematicFiles([]);
    }
  };

  useEffect(() => {
    if (currentSession && selectedFile) {
      loadSchematic(selectedFile);
    }
  }, [currentSession, selectedFile]);

  const loadSchematic = async (filename: string) => {
    if (!currentSession) return;
    setLoading(true);
    try {
      const data = await workspaceApi.getFile(currentSession.id, filename);
      setSvgContent(data.content);
    } catch {
      setSvgContent(null);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (svgContent && selectedFile) {
      const blob = new Blob([svgContent], { type: "image/svg+xml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = selectedFile;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  if (schematicFiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <CircuitBoard className="h-12 w-12 mb-4" />
        <p className="text-sm">No schematics yet</p>
        <p className="text-xs mt-1">
          Ask the agent to generate a schematic for your design
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Select value={selectedFile || ""} onValueChange={setSelectedFile}>
            <SelectTrigger className="h-8 w-[200px]">
              <CircuitBoard className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Select schematic" />
            </SelectTrigger>
            <SelectContent>
              {schematicFiles.map((file) => (
                <SelectItem key={file} value={file}>
                  {file}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground w-12 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => loadSchematicFiles()}
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
        </div>
      </div>

      {/* Schematic display */}
      <ScrollArea className="flex-1">
        <div className="p-4 flex items-center justify-center min-h-full">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading schematic...</p>
          ) : svgContent ? (
            <div
              className="bg-white rounded-lg p-4 overflow-auto"
              style={{
                transform: `scale(${zoom})`,
                transformOrigin: "top left",
              }}
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a schematic to view
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

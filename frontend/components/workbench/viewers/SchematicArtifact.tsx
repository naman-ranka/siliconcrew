"use client";

import { SchematicViewer } from "@/components/artifacts/SchematicViewer";

/**
 * v2 tab wrapper for `schematic:<name>` — renders exactly the named schematic
 * file through the existing SchematicViewer's filename-override prop.
 */
export function SchematicArtifact({ name }: { name: string }) {
  return <SchematicViewer filename={name} />;
}

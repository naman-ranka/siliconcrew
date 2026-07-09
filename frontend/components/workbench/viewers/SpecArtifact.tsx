"use client";

import { SpecViewer } from "@/components/artifacts/SpecViewer";

/**
 * v2 tab wrapper for the `spec` singleton — the SpecViewer already reads
 * store.spec (loaded by the workbench hydrate) and owns its empty state.
 */
export function SpecArtifact() {
  return <SpecViewer />;
}

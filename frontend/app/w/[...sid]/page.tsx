"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Workbench } from "@/components/workbench/Workbench";
import type { ViewMode } from "@/lib/nav";

/**
 * `/w/[...sid]` — the workbench, addressed by URL (S1).
 *
 * Catch-all segment because session ids may contain `/` (project-scoped ids):
 * sessionId = the decoded segments re-joined with `/`. Query params:
 *   chat — thread id to open
 *   view — "agent" | "ide" (S4: only "ide" is real; "agent" renders the IDE
 *          shell until the agent-first shell lands)
 *
 * This page is a thin parser — Workbench itself follows the props.
 */

// Next hands segments through percent-encoded; decode each defensively (a
// malformed sequence falls back to the raw segment rather than crashing).
function decodeSegment(seg: string): string {
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}

function WorkbenchRoute() {
  const params = useParams<{ sid: string | string[] }>();
  const search = useSearchParams();

  const raw = params?.sid;
  const segments = Array.isArray(raw) ? raw : raw ? [raw] : [];
  const sessionId = segments.map(decodeSegment).join("/");

  const chat = search?.get("chat") ?? null;
  const viewParam = search?.get("view");
  // S4: treat "agent" as "ide" for now — the agent-first shell doesn't exist
  // yet; the param is parsed so deep links stay stable when it does.
  const view: ViewMode = viewParam === "agent" ? "agent" : "ide";

  return <Workbench sessionId={sessionId} threadId={chat} view={view} />;
}

export default function Page() {
  // useSearchParams requires a Suspense boundary for static prerendering.
  return (
    <Suspense fallback={null}>
      <WorkbenchRoute />
    </Suspense>
  );
}

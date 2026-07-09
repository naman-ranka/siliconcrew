"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { sessionUrl } from "@/lib/nav";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";

/**
 * Legacy route — kept as a redirect shim only (external links / old
 * bookmarks). The workbench lives at `/w/{sessionId}` (S1); this page sends
 * you to the last session you had open, or home when none is recoverable.
 */
export default function WorkbenchRedirect() {
  const router = useRouter();

  useEffect(() => {
    // lastSessionId is persisted (localStorage) and hydrated synchronously.
    const last = useWorkbenchUiStore.getState().lastSessionId;
    router.replace(last ? sessionUrl(last) : "/");
  }, [router]);

  return null;
}

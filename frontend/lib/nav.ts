/**
 * URL contract for the workbench (S1) — the URL is the source of truth for
 * *where you are*:
 *
 *   /w/{sessionId}?chat={threadId}&view=agent|ide
 *
 * Session ids may contain `/` (project-scoped ids), so the /w route is a
 * catch-all segment and each path segment is percent-encoded individually —
 * the `/` structure survives as real URL segments.
 */

export type ViewMode = "agent" | "ide";

export interface SessionUrlOpts {
  /** Thread id for the `?chat=` param. */
  chat?: string | null;
  /** Shell posture for the `?view=` param. S4: only "ide" is real today. */
  view?: ViewMode | null;
}

/** Build the canonical `/w/…` URL for a session. */
export function sessionUrl(sessionId: string, opts?: SessionUrlOpts): string {
  const path = sessionId.split("/").map(encodeURIComponent).join("/");
  const q = new URLSearchParams();
  if (opts?.chat) q.set("chat", opts.chat);
  if (opts?.view) q.set("view", opts.view);
  const qs = q.toString();
  return `/w/${path}${qs ? `?${qs}` : ""}`;
}

/** Structural subset of Next's app router — keeps this lib testable. */
export interface RouterLike {
  push: (href: string) => void;
}

/** Navigate to a session — switching sessions ROUTES (the /w page effect then
 * drives store selection from the URL); callers must not selectSession directly. */
export function openSession(router: RouterLike, sessionId: string, opts?: SessionUrlOpts): void {
  router.push(sessionUrl(sessionId, opts));
}

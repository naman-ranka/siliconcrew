import type { ActivityEvent } from "@/types";

// Pure merge/dedup logic for the Activity feed. The store keeps two lists:
//   serverEvents — pages from GET /activity (the durable log, newest-first)
//   localEvents  — synthetic events built live from WS tool_call/tool_result
//                  frames (id "ws:<tool_call_id>") so the dock updates without
//                  waiting for the next server refresh.
// A local event is only a bridge until the server log catches up, so merging
// drops any local event the server already knows about.

const NEAR_MS = 15_000;

/** Local WS events are keyed "ws:<tool_call_id>"; the server keys the same
 *  event by the bare tool_call_id. */
function bareId(id: string): string {
  return id.startsWith("ws:") ? id.slice(3) : id;
}

function tsMs(ts: string): number {
  const t = new Date(ts).getTime();
  return Number.isFinite(t) ? t : 0;
}

/** Dedup rule: a local event is a duplicate of a server event when
 *  - same id (including the local "ws:" prefix stripped), OR
 *  - same tool AND same non-null runId, OR
 *  - same tool AND |ts delta| < 15s AND both non-running. */
export function isDuplicateOfServer(local: ActivityEvent, server: ActivityEvent): boolean {
  if (server.id === local.id || server.id === bareId(local.id)) return true;
  if (server.tool !== local.tool) return false;
  if (local.runId !== null && server.runId === local.runId) return true;
  if (
    server.status !== "running" &&
    local.status !== "running" &&
    Math.abs(tsMs(server.ts) - tsMs(local.ts)) < NEAR_MS
  ) {
    return true;
  }
  return false;
}

/** Merge server + local events into one newest-first list, dropping local
 *  events the server log already covers. */
export function mergeActivity(
  serverEvents: ActivityEvent[],
  localEvents: ActivityEvent[]
): ActivityEvent[] {
  const keptLocal = localEvents.filter(
    (l) => !serverEvents.some((s) => isDuplicateOfServer(l, s))
  );
  return [...serverEvents, ...keptLocal].sort((a, b) => tsMs(b.ts) - tsMs(a.ts));
}

/** Insert-or-update by id (used by the WS handlers: a tool_result upgrades the
 *  running event appended by its tool_call). New events go to the front
 *  (newest-first). */
export function upsertActivityEvent(
  events: ActivityEvent[],
  event: ActivityEvent
): ActivityEvent[] {
  const idx = events.findIndex((e) => e.id === event.id);
  if (idx === -1) return [event, ...events];
  const next = [...events];
  next[idx] = { ...next[idx], ...event };
  return next;
}

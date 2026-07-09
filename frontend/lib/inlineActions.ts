import type { ActivityEvent } from "@/types";

// Pure split logic for the agent shell's inline manual-action cards (S5-2).
//
// Foreign-actor activity (source "user" from the IDE, or "mcp" from the user's
// own AI) renders inside the conversation. LIVE events (arrived after the
// shell mounted) interleave exactly at the stream tail — they carry real
// timestamps. HISTORY can't be positioned exactly: thread messages carry no
// timestamps today (plan-documented), so events that happened between the
// thread's last_active and shell mount render as one grouped
// "While you were away" section instead of fake-precise interleaving.

export interface InlineActionSplit {
  /** Arrived after shell mount — render live at the conversation tail. */
  live: ActivityEvent[];
  /** Happened while the user was away (after the active thread's
   * last_active, before mount) — render as one collapsed group. */
  whileAway: ActivityEvent[];
}

function tsMs(ts: string): number {
  const t = new Date(ts).getTime();
  return Number.isFinite(t) ? t : NaN;
}

/**
 * @param events           merged activity feed (any order)
 * @param mountTs          epoch ms of the agent-shell mount
 * @param threadLastActive `last_active` ISO of the active thread (null → no
 *                         while-away section; we can't bound "away" honestly)
 */
export function splitInlineActions(
  events: ActivityEvent[],
  mountTs: number,
  threadLastActive: string | null
): InlineActionSplit {
  const live: ActivityEvent[] = [];
  const whileAway: ActivityEvent[] = [];
  const lastActiveMs = threadLastActive ? tsMs(threadLastActive) : NaN;

  for (const e of events) {
    if (e.source === "agent") continue; // agent calls already live in the messages
    const t = tsMs(e.ts);
    if (Number.isNaN(t)) continue;
    if (t > mountTs) {
      live.push(e);
    } else if (!Number.isNaN(lastActiveMs) && t > lastActiveMs) {
      whileAway.push(e);
    }
  }

  // Chronological (oldest first) — these read as part of the conversation.
  const byTs = (a: ActivityEvent, b: ActivityEvent) => tsMs(a.ts) - tsMs(b.ts);
  live.sort(byTs);
  whileAway.sort(byTs);
  return { live, whileAway };
}

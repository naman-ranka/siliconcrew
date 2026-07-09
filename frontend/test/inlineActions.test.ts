import { describe, it, expect } from "vitest";
import { splitInlineActions } from "@/lib/inlineActions";
import type { ActivityEvent } from "@/types";

// S5-2 split: live (after shell mount) vs "while you were away" (between the
// active thread's last_active and mount) vs dropped (older / agent-sourced).

const MOUNT = Date.parse("2026-07-03T12:00:00Z");
const LAST_ACTIVE = "2026-07-03T11:00:00Z";

function ev(partial: Partial<ActivityEvent> & { id: string; ts: string }): ActivityEvent {
  return {
    source: "user",
    tool: "linter_tool",
    args: {},
    status: "ok",
    resultSummary: "passed",
    durationMs: 100,
    runId: null,
    threadId: null,
    ...partial,
  };
}

describe("splitInlineActions", () => {
  it("events after mount are live; between last_active and mount are while-away", () => {
    const events = [
      ev({ id: "live-1", ts: "2026-07-03T12:00:05Z" }),
      ev({ id: "away-1", ts: "2026-07-03T11:30:00Z", source: "mcp" }),
      ev({ id: "old", ts: "2026-07-03T10:00:00Z" }), // before last_active → dropped
    ];
    const { live, whileAway } = splitInlineActions(events, MOUNT, LAST_ACTIVE);
    expect(live.map((e) => e.id)).toEqual(["live-1"]);
    expect(whileAway.map((e) => e.id)).toEqual(["away-1"]);
  });

  it("agent-sourced events never render inline (they already live in the messages)", () => {
    const events = [
      ev({ id: "a1", ts: "2026-07-03T12:00:05Z", source: "agent" }),
      ev({ id: "a2", ts: "2026-07-03T11:30:00Z", source: "agent" }),
    ];
    const { live, whileAway } = splitInlineActions(events, MOUNT, LAST_ACTIVE);
    expect(live).toEqual([]);
    expect(whileAway).toEqual([]);
  });

  it("no last_active → no while-away section (we can't bound 'away' honestly)", () => {
    const events = [ev({ id: "x", ts: "2026-07-03T11:30:00Z" })];
    const { live, whileAway } = splitInlineActions(events, MOUNT, null);
    expect(live).toEqual([]);
    expect(whileAway).toEqual([]);
  });

  it("both lists come back chronological (oldest first), whatever the feed order", () => {
    const events = [
      ev({ id: "live-2", ts: "2026-07-03T12:02:00Z" }),
      ev({ id: "live-1", ts: "2026-07-03T12:01:00Z" }),
      ev({ id: "away-2", ts: "2026-07-03T11:45:00Z" }),
      ev({ id: "away-1", ts: "2026-07-03T11:15:00Z" }),
    ];
    const { live, whileAway } = splitInlineActions(events, MOUNT, LAST_ACTIVE);
    expect(live.map((e) => e.id)).toEqual(["live-1", "live-2"]);
    expect(whileAway.map((e) => e.id)).toEqual(["away-1", "away-2"]);
  });

  it("none: empty feed / unparseable timestamps → both empty", () => {
    expect(splitInlineActions([], MOUNT, LAST_ACTIVE)).toEqual({ live: [], whileAway: [] });
    const bad = [ev({ id: "b", ts: "not-a-date" })];
    expect(splitInlineActions(bad, MOUNT, LAST_ACTIVE)).toEqual({ live: [], whileAway: [] });
  });
});

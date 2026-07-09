import { describe, it, expect } from "vitest";

import { mergeActivity, upsertActivityEvent, isDuplicateOfServer } from "@/lib/activityMerge";
import type { ActivityEvent } from "@/types";

const ev = (over: Partial<ActivityEvent>): ActivityEvent => ({
  id: "e1",
  ts: "2026-07-01T10:00:00Z",
  source: "agent",
  tool: "write_file",
  args: {},
  status: "ok",
  resultSummary: "",
  durationMs: null,
  runId: null,
  threadId: null,
  ...over,
});

describe("activityMerge: upsertActivityEvent (live WS lifecycle)", () => {
  it("a tool_result upgrades the running event appended by its tool_call", () => {
    const running = ev({ id: "ws:tc1", status: "running", resultSummary: "" });
    let local = upsertActivityEvent([], running);
    expect(local).toHaveLength(1);
    expect(local[0].status).toBe("running");

    const done = ev({ id: "ws:tc1", status: "ok", resultSummary: "wrote counter.v", durationMs: 420 });
    local = upsertActivityEvent(local, done);
    expect(local).toHaveLength(1); // updated in place, not duplicated
    expect(local[0].status).toBe("ok");
    expect(local[0].resultSummary).toBe("wrote counter.v");
    expect(local[0].durationMs).toBe(420);
  });

  it("a new id is prepended (newest-first)", () => {
    const a = ev({ id: "ws:a", ts: "2026-07-01T10:00:00Z" });
    const b = ev({ id: "ws:b", ts: "2026-07-01T10:01:00Z" });
    const out = upsertActivityEvent([a], b);
    expect(out.map((e) => e.id)).toEqual(["ws:b", "ws:a"]);
  });
});

describe("activityMerge: mergeActivity dedup", () => {
  it("drops a local WS event when the server logs the same tool_call_id", () => {
    const local = ev({ id: "ws:tc1", tool: "simulation_tool", status: "ok" });
    const server = ev({ id: "tc1", tool: "simulation_tool", status: "ok", ts: "2026-07-01T11:00:00Z" });
    const merged = mergeActivity([server], [local]);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe("tc1");
  });

  it("drops a local optimistic event when a server event has the same tool + runId", () => {
    const local = ev({ id: "local-1", tool: "simulation_tool", runId: "sim_0007", ts: "2026-07-01T10:00:01Z" });
    const server = ev({ id: "srv-9", tool: "simulation_tool", runId: "sim_0007", ts: "2026-07-01T10:05:00Z" });
    const merged = mergeActivity([server], [local]);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe("srv-9");
  });

  it("null runIds never match each other via the runId rule", () => {
    const local = ev({ id: "local-1", tool: "write_file", runId: null, ts: "2026-07-01T08:00:00Z" });
    const server = ev({ id: "srv-1", tool: "write_file", runId: null, ts: "2026-07-01T09:00:00Z" });
    // Far apart in time, both non-running, null runIds → NOT duplicates.
    expect(isDuplicateOfServer(local, server)).toBe(false);
    expect(mergeActivity([server], [local])).toHaveLength(2);
  });

  it("drops a local event within 15s of a same-tool server event when both are settled", () => {
    const local = ev({ id: "local-1", tool: "write_file", status: "ok", ts: "2026-07-01T10:00:05Z" });
    const server = ev({ id: "srv-1", tool: "write_file", status: "ok", ts: "2026-07-01T10:00:10Z" });
    expect(mergeActivity([server], [local])).toHaveLength(1);

    // …but a still-running local event is kept (it carries live state).
    const running = ev({ id: "local-2", tool: "write_file", status: "running", ts: "2026-07-01T10:00:05Z" });
    expect(mergeActivity([server], [running])).toHaveLength(2);
  });

  it("orders the merged feed newest-first", () => {
    const s1 = ev({ id: "s1", ts: "2026-07-01T10:00:00Z" });
    const s2 = ev({ id: "s2", ts: "2026-07-01T12:00:00Z" });
    const l1 = ev({ id: "ws:x", tool: "start_synthesis", ts: "2026-07-01T11:00:00Z", status: "running" });
    const merged = mergeActivity([s2, s1], [l1]);
    expect(merged.map((e) => e.id)).toEqual(["s2", "ws:x", "s1"]);
  });
});

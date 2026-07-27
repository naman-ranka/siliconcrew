import { describe, it, expect, beforeEach, vi } from "vitest";

// Live WS tool_result frames carry the tool's RAW domain status (the backend
// ships result.status verbatim). The live card classifier must speak the same
// failure vocabulary as the durable log (api.py _TOOL_FAILURE_STATUSES) — a
// live card must never render green and then flip red on reconcile (#31).

const fake: any = { readyState: 0, onopen: null, onmessage: null, onerror: null, onclose: null, send: vi.fn(), close: vi.fn() };

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { list: vi.fn().mockResolvedValue([]), getHistory: vi.fn().mockResolvedValue([]) },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: {
    createConnection: vi.fn(() => fake),
    getHistory: vi.fn().mockResolvedValue([]),
    getThreadHistory: vi.fn().mockResolvedValue([]),
  },
  workspaceApi: {
    listFiles: vi.fn().mockResolvedValue([]),
    listWaveforms: vi.fn().mockResolvedValue([]),
    listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: { getManifest: vi.fn().mockResolvedValue({ files: [] }), listRuns: vi.fn().mockResolvedValue([]) },
  keysApi: {},
}));

import { useStore } from "@/lib/store";

const frame = (obj: unknown) => ({ data: JSON.stringify(obj) });

beforeEach(() => {
  vi.clearAllMocks();
  fake.onopen = fake.onmessage = fake.onerror = fake.onclose = null;
  fake.readyState = 0;
  useStore.setState({
    currentSession: { id: "s1", name: "s1" } as any,
    messages: [], activeThreadId: null,
    ws: null, wsSessionId: null, wsThreadId: null,
    isStreaming: false, streamingMessage: null, chatError: null, chatErrorCode: null,
    activity: { ...useStore.getState().activity, localEvents: [] },
  } as any);
});

function resultStatusOf(rawStatus: string): string | undefined {
  useStore.getState().sendMessage("run it");
  const sock = useStore.getState().ws as any;
  sock.onmessage(frame({ type: "tool_call", tool: { id: "t1", name: "simulation_tool", args: {} } }));
  sock.onmessage(frame({ type: "tool_result", tool_call_id: "t1", status: rawStatus, content: "x" }));
  return useStore.getState().activity.localEvents.find((e) => e.id === "ws:t1")?.status;
}

describe("live tool_result status classification matches the durable log", () => {
  it.each(["test_failed", "sim_failed", "compile_failed", "lint_failed", "timeout", "error", "failed"])(
    "domain failure %s renders as error immediately",
    (s) => {
      expect(resultStatusOf(s)).toBe("error");
    }
  );

  it.each(["test_passed", "passed", "queued", "running", "ok", "success"])(
    "domain success %s renders as ok",
    (s) => {
      expect(resultStatusOf(s)).toBe("ok");
    }
  );
});

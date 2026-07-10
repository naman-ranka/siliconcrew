import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { webcrypto } from "node:crypto";

// jsdom's window.crypto has no subtle — the provenance check hashes with it.
beforeAll(() => {
  if (!globalThis.crypto?.subtle) {
    Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
  }
});

const fetchRawBytes = vi.fn();

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workbenchApi: {},
  workspaceApi: {
    fetchRawBytes: (...a: unknown[]) => fetchRawBytes(...a),
    downloadRawFile: vi.fn(),
  },
}));

// The real engine can't construct in jsdom (jointjs needs real SVG); session
// creation is mocked — engine behavior is covered by websim.engine.test.ts.
const createWebsimSession = vi.fn();
vi.mock("@/lib/websim", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/websim")>();
  return { ...actual, createWebsimSession: (...a: unknown[]) => createWebsimSession(...a) };
});

import { useStore } from "@/lib/store";
import { InteractiveArtifact } from "@/components/workbench/viewers/InteractiveArtifact";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "x",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

function seedFile(path: string, content: string) {
  useStore.setState({
    currentSession: SESSION as never,
    fileCache: {
      [path]: {
        status: "ready",
        file: { filename: path, content, size: content.length, binary: false, tooLarge: false },
      },
    } as never,
  });
}

const PAYLOAD = {
  format: "siliconcrew-websim-v1",
  top: "counter",
  generated_at: "2026-07-10T00:00:00+00:00",
  sources: { "counter.v": "aa".repeat(32) },
  ports: [{ name: "clk", direction: "input", bits: 1 }],
  yosys_netlist: { modules: {} },
};

function fakeSession() {
  return {
    ports: PAYLOAD.ports,
    hasClock: true,
    cycle: 0,
    setInput: vi.fn(),
    readOutputs: () => ({}),
    tickCycle: vi.fn(),
    settle: vi.fn(),
    dispose: vi.fn(),
  };
}

beforeEach(() => {
  fetchRawBytes.mockReset();
  createWebsimSession.mockReset();
  useStore.setState({ currentSession: SESSION as never, fileCache: {} });
});

describe("InteractiveArtifact sandbox discipline", () => {
  it("renders the iframe with EXACTLY sandbox=allow-scripts (never same-origin)", async () => {
    seedFile("demo.dashboard.html", "<html><body>plain</body></html>");
    render(<InteractiveArtifact path="demo.dashboard.html" />);
    const frame = await screen.findByTestId("websim-frame");
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
  });

  it("injects the bridge into the srcdoc", async () => {
    seedFile("demo.dashboard.html", "<html><body>plain</body></html>");
    render(<InteractiveArtifact path="demo.dashboard.html" />);
    const frame = await screen.findByTestId("websim-frame");
    expect(frame.getAttribute("srcdoc")).toContain("window.simBridge");
  });
});

describe("InteractiveArtifact provenance strip (shell-rendered, unspoofable)", () => {
  it("declares a static mockup when no siliconcrew-sim meta is present", async () => {
    seedFile("mock.dashboard.html", "<html><body><h1>Looks alive</h1></body></html>");
    render(<InteractiveArtifact path="mock.dashboard.html" />);
    await waitFor(() =>
      expect(screen.getByTestId("websim-provenance").textContent).toMatch(/static mockup/i)
    );
    expect(fetchRawBytes).not.toHaveBeenCalled();
  });

  it("shows 'simulation unavailable' when the declared netlist can't be loaded", async () => {
    seedFile(
      "broken.dashboard.html",
      '<html><head><meta name="siliconcrew-sim" content="gone.websim.json"></head><body></body></html>'
    );
    fetchRawBytes.mockRejectedValue(new Error("HTTP 404"));
    render(<InteractiveArtifact path="broken.dashboard.html" />);
    await waitFor(() =>
      expect(screen.getByTestId("websim-provenance").textContent).toMatch(/simulation unavailable/i)
    );
  });

  it("shows the live strip (netlist ← sources) once the session exists", async () => {
    seedFile(
      "live.dashboard.html",
      '<html><head><meta name="siliconcrew-sim" content="counter.websim.json"></head><body></body></html>'
    );
    const bytes = new TextEncoder().encode(JSON.stringify(PAYLOAD));
    fetchRawBytes.mockResolvedValue(bytes.buffer);
    createWebsimSession.mockResolvedValue(fakeSession());

    render(<InteractiveArtifact path="live.dashboard.html" />);
    await waitFor(() => {
      const strip = screen.getByTestId("websim-provenance").textContent ?? "";
      expect(strip).toMatch(/live gate-level sim/i);
      expect(strip).toContain("counter.websim.json");
      expect(strip).toContain("counter.v");
    });
    // fidelity line is always present — never pretend timing accuracy
    expect(screen.getByTestId("websim-provenance").textContent).toContain("no timing");
  });

  it("flags STALE when source hashes no longer match the artifact", async () => {
    seedFile(
      "stale.dashboard.html",
      '<html><head><meta name="siliconcrew-sim" content="counter.websim.json"></head><body></body></html>'
    );
    const bytes = new TextEncoder().encode(JSON.stringify(PAYLOAD));
    // first call: the netlist; later calls: source bytes that won't hash to aa…
    fetchRawBytes.mockResolvedValue(bytes.buffer);
    createWebsimSession.mockResolvedValue(fakeSession());

    render(<InteractiveArtifact path="stale.dashboard.html" />);
    await waitFor(() =>
      expect(screen.getByTestId("websim-provenance").textContent).toMatch(/STALE: sources changed/)
    );
  });
});

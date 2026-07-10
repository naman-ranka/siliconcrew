// Interactive web-sim core (Phase 0): loads a `<top>.websim.json` artifact
// (yosys netlist + ports + provenance, built by build_interactive_sim),
// converts it with yosys2digitaljs and simulates it with digitaljs'
// HeadlessCircuit — a real gate-level simulation, entirely client-side.
//
// The engine is imported dynamically so the (heavy) simulator only loads when
// an interactive tab actually opens. `digitaljs` is aliased to its headless
// entry in next.config.mjs / vitest.config.mts — the view half (jointjs SVG
// rendering) is never bundled.
//
// Honesty contracts here:
//   * outputs are null while ANY of their bits is undefined (3-state x) —
//     the dashboard shows "unknown", it never invents a 0;
//   * provenance freshness is judged by sha256 CONTENT hashes of the sources
//     (mtimes lie across template forks — copy2 preserves them).

export interface WebsimPort {
  name: string;
  direction: "input" | "output" | "inout";
  bits: number;
}

export interface WebsimPayload {
  format: string;
  top: string;
  generated_at: string;
  sources: Record<string, string>;
  ports: WebsimPort[];
  yosys_netlist: unknown;
}

export const WEBSIM_FORMAT = "siliconcrew-websim-v1";

/** Parse + validate a websim artifact; null for anything shapeless. */
export function parseWebsimPayload(text: string): WebsimPayload | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  const p = raw as Partial<WebsimPayload> | null;
  if (
    !p ||
    p.format !== WEBSIM_FORMAT ||
    typeof p.top !== "string" ||
    typeof p.sources !== "object" ||
    p.sources === null ||
    !Array.isArray(p.ports) ||
    typeof p.yosys_netlist !== "object" ||
    p.yosys_netlist === null
  ) {
    return null;
  }
  return p as WebsimPayload;
}

/** Netlist file declared by a dashboard's
 *  `<meta name="siliconcrew-sim" content="...">`; null → static mockup. */
export function parseSimMeta(html: string): string | null {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const content = doc.querySelector('meta[name="siliconcrew-sim"]')?.getAttribute("content");
  return content && content.trim() ? content.trim() : null;
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export type Freshness = "fresh" | "stale" | "unknown";

/** Compare the artifact's recorded source hashes against the CURRENT bytes of
 *  those files. Any mismatch or missing source → stale; fetch/hash trouble →
 *  unknown (never claim freshness we can't prove). */
export async function checkProvenance(
  payload: WebsimPayload,
  fetchBytes: (path: string) => Promise<ArrayBuffer>
): Promise<Freshness> {
  try {
    for (const [path, recorded] of Object.entries(payload.sources)) {
      let bytes: ArrayBuffer;
      try {
        bytes = await fetchBytes(path);
      } catch {
        return "stale"; // source gone or unreadable — the netlist outlived it
      }
      // hashing trouble (no crypto.subtle etc.) → outer catch → unknown:
      // never claim stale OR fresh without evidence
      if ((await sha256Hex(bytes)) !== recorded) return "stale";
    }
    return "fresh";
  } catch {
    return "unknown";
  }
}

// --- Simulation session ------------------------------------------------------

export interface WebsimSession {
  ports: WebsimPort[];
  hasClock: boolean;
  /** Cycles ticked so far (0 for clockless designs). */
  cycle: number;
  setInput(name: string, value: number): void;
  /** Output values by port name; null while any bit is undefined (x). */
  readOutputs(): Record<string, number | null>;
  /** One full clock cycle (clk↑ settle, clk↓ settle). No-op when clockless. */
  tickCycle(): void;
  /** Propagate pending combinational events (after setInput on clockless designs). */
  settle(): void;
  dispose(): void;
}

// Iteration cap so a combinational loop in the netlist can't hang the tab.
const SETTLE_CAP = 10_000;

const CLOCK_NAME = /^(clk|clock)/i;

interface EngineDevice {
  type?: string;
  net?: string;
  bits?: number;
}

export async function createWebsimSession(payload: WebsimPayload): Promise<WebsimSession> {
  const [{ yosys2digitaljs }, dj, { Vector3vl }] = await Promise.all([
    import("yosys2digitaljs/core"),
    import("digitaljs"),
    import("3vl"),
  ]);
  const circuitDef = yosys2digitaljs(payload.yosys_netlist as Parameters<typeof yosys2digitaljs>[0]);
  const circuit = new dj.HeadlessCircuit(circuitDef);

  const inputs = new Map<string, { id: string; bits: number }>();
  const outputs = new Map<string, { id: string; bits: number }>();
  for (const [id, dev] of Object.entries(circuitDef.devices as Record<string, EngineDevice>)) {
    if (dev.type === "Input" && dev.net) inputs.set(dev.net, { id, bits: dev.bits ?? 1 });
    if (dev.type === "Output" && dev.net) outputs.set(dev.net, { id, bits: dev.bits ?? 1 });
  }

  const settle = () => {
    let n = 0;
    do {
      circuit.updateGates();
    } while (circuit.hasPendingEvents && ++n < SETTLE_CAP);
  };

  const clockEntry =
    Array.from(inputs.entries()).find(([name, m]) => m.bits === 1 && CLOCK_NAME.test(name)) ?? null;

  // Deterministic start: all inputs low (mirrors a 2-state power-on; the
  // dashboard drives reset explicitly from here).
  inputs.forEach((m) => circuit.setInput(m.id, Vector3vl.zeros(m.bits)));
  settle();

  const session: WebsimSession = {
    ports: payload.ports,
    hasClock: clockEntry !== null,
    cycle: 0,
    setInput(name, value) {
      const m = inputs.get(name);
      if (!m) return;
      circuit.setInput(m.id, Vector3vl.fromNumber(value, m.bits));
      if (!clockEntry) settle();
    },
    readOutputs() {
      const out: Record<string, number | null> = {};
      outputs.forEach((m, name) => {
        const v = circuit.getOutput(m.id);
        out[name] = v.isFullyDefined ? v.toNumber() : null;
      });
      return out;
    },
    tickCycle() {
      if (!clockEntry) return;
      const [, m] = clockEntry;
      circuit.setInput(m.id, Vector3vl.ones(1));
      settle();
      circuit.setInput(m.id, Vector3vl.zeros(1));
      settle();
      session.cycle += 1;
    },
    settle,
    dispose() {
      inputs.clear();
      outputs.clear();
    },
  };
  return session;
}

// --- Dashboard document composition -------------------------------------------

// Injected as the FIRST script of the agent-authored dashboard, inside the
// sandboxed iframe. It is the dashboard's ONLY connection to the simulation:
// a postMessage RPC to the trusted shell (which runs the engine). Agent JS
// never touches the engine — it can only ask for input changes and receive
// output snapshots.
export const BRIDGE_SOURCE = `(function () {
  var readyCbs = [], updateCbs = [], ports = null, connected = false;
  window.simBridge = {
    ready: function (cb) { if (ports) { cb(ports); } else { readyCbs.push(cb); } },
    setInput: function (name, value) { window.parent.postMessage({ type: "websim:setInput", name: name, value: value }, "*"); },
    setClockHz: function (hz) { window.parent.postMessage({ type: "websim:setClockHz", hz: hz }, "*"); },
    onUpdate: function (cb) { updateCbs.push(cb); },
    isConnected: function () { return connected; }
  };
  window.addEventListener("message", function (ev) {
    if (ev.source !== window.parent || !ev.data || typeof ev.data.type !== "string") return;
    if (ev.data.type === "websim:init") {
      ports = ev.data.ports || [];
      connected = !!ev.data.connected;
      var cbs = readyCbs.splice(0);
      for (var i = 0; i < cbs.length; i++) cbs[i](ports);
    } else if (ev.data.type === "websim:update") {
      for (var j = 0; j < updateCbs.length; j++) updateCbs[j]({ outputs: ev.data.outputs, cycle: ev.data.cycle });
    }
  });
  window.parent.postMessage({ type: "websim:hello" }, "*");
})();
`;

/** Agent dashboard HTML → iframe srcdoc with the bridge injected as the first
 *  head script. DOMParser normalizes whatever fragment/document the agent
 *  wrote into a full document. */
export function composeSrcdoc(agentHtml: string): string {
  const doc = new DOMParser().parseFromString(agentHtml, "text/html");
  const script = doc.createElement("script");
  script.textContent = BRIDGE_SOURCE;
  doc.head.insertBefore(script, doc.head.firstChild);
  return `<!doctype html>${doc.documentElement.outerHTML}`;
}

// --- postMessage protocol types shared with the viewer -------------------------

export interface BridgeInbound {
  type: "websim:hello" | "websim:setInput" | "websim:setClockHz";
  name?: string;
  value?: number;
  hz?: number;
}

export const DEFAULT_CLOCK_HZ = 25;
/** Ceiling on simulated cycles per real second — batching stays bounded even
 *  if a dashboard asks for something silly. */
export const MAX_CLOCK_HZ = 100_000;
/** Hard per-frame batch cap (a long GC pause must not trigger a huge catch-up). */
export const MAX_CYCLES_PER_FRAME = 5_000;

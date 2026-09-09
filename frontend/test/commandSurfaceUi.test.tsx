import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

// Command Surface COMPONENT tests (command-surface-simplification v2): the
// file-override box (L1/FA1) and its per-command React key (F4). Later items
// add the rail filter/Esc discipline, the sign-in CTA + replay host, the
// async/sync affordances and the F1/F3 guards to this file.

const signIn = vi.fn();
let authState: Record<string, unknown>;

vi.mock("@/lib/auth", () => ({ useAuth: () => authState }));
vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {
    getDirPaths: vi.fn().mockResolvedValue({ ok: true, paths: [], truncated: false }),
  },
  // Mirrors the real detection: by CODE, never by message (W4/A17).
  isSignInRequired: (e: unknown) =>
    (e as { code?: string } | null)?.code === "signin_required",
  workbenchApi: {
    invokeTool: vi.fn(),
    updateManifest: vi.fn(),
    getManifest: vi.fn(),
    getToolCatalog: vi.fn().mockResolvedValue([]),
    getActivity: vi.fn().mockResolvedValue({ ok: true, events: [], nextBefore: null }),
    lint: vi.fn(),
    simulate: vi.fn(),
    synthesize: vi.fn(),
    retryRun: vi.fn(),
    listRuns: vi.fn().mockResolvedValue([]),
  },
}));

import { CommandSurface } from "@/components/workbench/CommandSurface";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { workbenchApi } from "@/lib/api";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "m",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const MANIFEST = {
  sessionId: "s1",
  files: [
    { name: "alu.v", role: "rtl" as const, path: "alu.v" },
    { name: "tb.v", role: "tb" as const, path: "tb.v" },
  ],
  synthTop: "alu",
  simTop: "tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
};

const KEY = "sc-auth-intent";

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  authState = { enabled: true, status: "anonymous", signIn };
  useStore.setState({
    currentSession: SESSION as never,
    manifest: MANIFEST,
    runs: [],
    // Populated slices → the open effects are cache no-ops.
    pathIndex: { status: "ready", paths: ["alu.v", "tb.v"], truncated: false, error: null },
    toolCatalog: { tools: [], status: "ready", error: null },
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
  });
  useWorkbenchUiStore.setState({ commandSurfaceOpen: true });
});

const filter = () => screen.getByTestId("command-surface-filter");
const railButton = (label: string) =>
  screen
    .getAllByRole("button")
    .find((b) => b.textContent === label || b.textContent === `${label}async`);

const payloadText = () => screen.getByLabelText("tool call payload").textContent ?? "";

describe("CommandSurface — rail filter + keyboard (W6)", () => {
  it("filters the rail over label/tool/category and shows an honest empty state", () => {
    render(<CommandSurface />);
    expect(filter()).toHaveFocus(); // type-to-filter, mirroring ⌘K
    fireEvent.change(filter(), { target: { value: "retry p" } });
    expect(railButton("Retry P&R")).toBeTruthy();
    expect(railButton("Lint")).toBeUndefined();
    // Tool-name match: "retry_pd" is Retry P&R's tool.
    fireEvent.change(filter(), { target: { value: "retry_pd" } });
    expect(railButton("Retry P&R")).toBeTruthy();
    // Category match: "flow" keeps all four.
    fireEvent.change(filter(), { target: { value: "flow" } });
    for (const label of ["Lint", "Simulate", "Synthesize", "Retry P&R"]) {
      expect(railButton(label)).toBeTruthy();
    }
    fireEvent.change(filter(), { target: { value: "zzz-nothing" } });
    expect(screen.getByText("No matching commands.")).toBeInTheDocument();
    // The selection is not forced into the filtered set — the form stays.
    expect(screen.getByLabelText("tool call payload")).toBeInTheDocument();
  });

  it("↑/↓ move the selection through the filtered list (wrapping); Enter snaps to the first match", () => {
    render(<CommandSurface />);
    // Initial selection is synth.
    expect(railButton("Synthesize")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(filter(), { key: "ArrowDown" });
    expect(railButton("Retry P&R")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(filter(), { key: "ArrowDown" }); // wraps
    expect(railButton("Lint")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(filter(), { key: "ArrowUp" });
    expect(railButton("Retry P&R")).toHaveAttribute("aria-current", "true");
    // Filter away the selection, Enter selects the first visible match.
    fireEvent.change(filter(), { target: { value: "lint" } });
    fireEvent.keyDown(filter(), { key: "Enter" });
    expect(railButton("Lint")).toHaveAttribute("aria-current", "true");
  });

  it("Esc discipline (A23): a consumed Esc clears the filter WITHOUT closing; a bare Esc closes", () => {
    render(<CommandSurface />);
    fireEvent.change(filter(), { target: { value: "sim" } });
    // The filter consumes Esc (preventDefault) — the Surface's window
    // listener must check defaultPrevented FIRST and stay open.
    fireEvent.keyDown(filter(), { key: "Escape" });
    expect(filter()).toHaveValue("");
    expect(screen.getByTestId("command-surface")).toBeInTheDocument();
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(true);
    // Empty filter: Esc is unconsumed → the Surface closes.
    fireEvent.keyDown(filter(), { key: "Escape" });
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(false);
  });

  it("R69: an Esc some OTHER consumer already cancelled (preventDefault, no stopPropagation) never closes the Surface", () => {
    // The house discipline: consumers preventDefault(); global listeners check
    // defaultPrevented. The rail filter and the combo also stopPropagation,
    // which shields the window listener by accident — this test removes that
    // accident and pins the check itself.
    render(<CommandSurface />);
    const ev = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    ev.preventDefault();
    act(() => {
      window.dispatchEvent(ev);
    });
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(true);
    // A bare Esc at the window still closes.
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(false);
  });

  it("a combo dropdown's consumed Esc no longer closes the Surface by accident either", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Simulate")!);
    const tb = screen.getByRole("combobox", { name: "Testbench (module)" });
    fireEvent.focus(tb);
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(tb, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(true);
  });
});

describe("CommandSurface — form clarity (W7)", () => {
  it("sim's testbench field is labeled as a MODULE with a module tag and file subtitles (R70)", () => {
    useStore.setState({
      manifest: { ...MANIFEST, testbenches: [{ file: "tb.v", module: "tb" }] },
    });
    render(<CommandSurface />);
    fireEvent.click(railButton("Simulate")!);
    const tb = screen.getByRole("combobox", { name: "Testbench (module)" });
    fireEvent.focus(tb);
    const row = screen.getByRole("option", { name: "tb" });
    expect(row.textContent).toBe("tbtb.v"); // module + its defining file
  });

  it("dict / list[dict] catalog params render a JSON textarea; invalid JSON is blocked with a field error", async () => {
    useStore.setState({
      toolCatalog: {
        status: "ready",
        error: null,
        tools: [
          {
            name: "write_spec",
            description: "Writes a spec.",
            category: "essential",
            requiresSignIn: false,
            async: false,
            mutates: true,
            argsSchema: {
              type: "object",
              properties: {
                module_name: { type: "string" },
                ports: { type: "array", items: { type: "object" } },
                parameters: { anyOf: [{ type: "object" }, { type: "null" }], default: null },
              },
              required: ["module_name", "ports"],
            },
          },
        ],
      },
    });
    render(<CommandSurface />);
    fireEvent.click(railButton("Write Spec")!);
    const ports = screen.getByRole("textbox", { name: "ports" });
    expect(ports.tagName).toBe("TEXTAREA");
    expect(ports).toHaveAttribute("placeholder", '[{ "name": "clk", "dir": "input" }]');
    // Optional dict → advanced (collapsed); expand to see its object placeholder.
    fireEvent.click(screen.getByRole("button", { name: /Advanced \(1\)/ }));
    expect(screen.getByRole("textbox", { name: "parameters" })).toHaveAttribute(
      "placeholder",
      '{ "WIDTH": 8 }'
    );
    fireEvent.change(ports, { target: { value: "{not json" } });
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByText("not valid JSON");
    expect(workbenchApi.invokeTool).not.toHaveBeenCalled();
    // Valid text parses into the live payload as a real array.
    fireEvent.change(ports, { target: { value: '[{ "name": "clk" }]' } });
    expect(payloadText()).toContain('"name": "clk"');
  });
});

describe("CommandSurface — no needs-login badge (L2/A19)", () => {
  it("renders the four Flow commands and NO sign-in (KeyRound) badges", () => {
    render(<CommandSurface />);
    for (const label of ["Lint", "Simulate", "Synthesize", "Retry P&R"]) {
      expect(railButton(label)).toBeTruthy();
    }
    // The badge render sites are deleted — nothing advertises sign-in.
    expect(document.querySelector('[title="requires sign-in"]')).toBeNull();
  });
});

describe("CommandSurface — sign-in CTA + form-state restore (W4/L2)", () => {
  it("a signin_required dispatch renders the CTA; clicking stashes the form state and signs in", async () => {
    vi.mocked(workbenchApi.synthesize).mockRejectedValue(
      Object.assign(new Error("Sign in to run synthesis."), {
        code: "signin_required",
        status: 403,
      })
    );
    render(<CommandSurface />);
    // Fill something first so the stash carries real form state (synth's one
    // basic number input is the clock period).
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "8" } });
    fireEvent.click(screen.getByTestId("command-surface-invoke")); // synth is the default selection
    const cta = await screen.findByTestId("command-surface-signin-cta");
    // The CTA replaces the raw error string.
    expect(cta).toHaveTextContent("Sign in to run this");
    expect(screen.queryByText("Sign in to run synthesis.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Sign in to run this/ }));
    expect(signIn).toHaveBeenCalledTimes(1);
    const stashed = JSON.parse(sessionStorage.getItem(KEY)!);
    expect(stashed.intent).toEqual({
      kind: "surfaceCommand",
      sessionId: "s1",
      commandId: "synth",
      values: { clockPeriodNs: 8 },
    });
  });

  it("ordinary failures keep the raw error — no CTA", async () => {
    vi.mocked(workbenchApi.synthesize).mockRejectedValue(new Error("Quota exceeded."));
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByText("Quota exceeded.");
    expect(screen.queryByTestId("command-surface-signin-cta")).toBeNull();
  });

  it("replay host: a stashed surfaceCommand intent reopens the Surface with the form restored", async () => {
    authState = { enabled: true, status: "signed_in", signIn };
    useWorkbenchUiStore.setState({ commandSurfaceOpen: false });
    sessionStorage.setItem(
      KEY,
      JSON.stringify({
        intent: {
          kind: "surfaceCommand",
          sessionId: "s1",
          commandId: "lint",
          values: { engine: "verilator" },
        },
        at: Date.now(),
      })
    );
    render(<CommandSurface />);
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(true)
    );
    expect(railButton("Lint")).toHaveAttribute("aria-current", "true");
    // The restored value rides the live payload pane.
    expect(payloadText()).toContain("verilator");
    expect(sessionStorage.getItem(KEY)).toBeNull(); // consumed
  });

  it("replay host drops an intent for a DIFFERENT session (cleared, never misapplied)", async () => {
    authState = { enabled: true, status: "signed_in", signIn };
    useWorkbenchUiStore.setState({ commandSurfaceOpen: false });
    sessionStorage.setItem(
      KEY,
      JSON.stringify({
        intent: { kind: "surfaceCommand", sessionId: "OTHER", commandId: "lint", values: {} },
        at: Date.now(),
      })
    );
    render(<CommandSurface />);
    await waitFor(() => expect(sessionStorage.getItem(KEY)).toBeNull());
    expect(useWorkbenchUiStore.getState().commandSurfaceOpen).toBe(false);
  });
});

describe("CommandSurface — file-override box (L1/FA1)", () => {
  it("collapsed by default: manifest chips + an Override… affordance, nothing in the payload", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    const box = screen.getByTestId("command-surface-override-files");
    expect(box).toHaveTextContent("Supplied by manifest");
    expect(box).toHaveTextContent("alu.v"); // the manifest rtl chip
    // Empty override → the payload stays manifest-driven (no `files` key).
    expect(payloadText()).not.toContain('"files"');
  });

  it("Override… swaps in the multi-combo; picked files land in the live payload; reset clears", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "Override…" }));
    const input = screen.getByRole("combobox", { name: "Override files" });
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "alu.v" }));
    expect(payloadText()).toContain('"files"');
    expect(payloadText()).toContain('"alu.v"');
    // Free entry stays allowed — type a path the suggestions missed.
    fireEvent.change(input, { target: { value: "rtl/custom.v" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(payloadText()).toContain("rtl/custom.v");
    // "Use manifest set" clears the override → payload back to manifest-driven.
    fireEvent.click(screen.getByRole("button", { name: "Use manifest set" }));
    expect(payloadText()).not.toContain('"files"');
    expect(screen.getByTestId("command-surface-override-files")).toHaveTextContent(
      "Supplied by manifest"
    );
  });

  it("typed-but-unentered override text reaches the payload on blur (PR #90 review)", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "Override…" }));
    const input = screen.getByRole("combobox", { name: "Override files" });
    // The user types a path and goes straight for Dispatch — no Enter. Until
    // the field loses focus the draft is invisible to the payload pane…
    fireEvent.change(input, { target: { value: "rtl/alu_v2.v" } });
    expect(payloadText()).not.toContain("rtl/alu_v2.v");
    // …and on blur it must become a real value, not vanish.
    fireEvent.blur(input);
    expect(payloadText()).toContain("rtl/alu_v2.v");
  });

  it("the override rides the dispatch: lint POSTs files when set", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({
      ok: true,
      status: "passed",
      warnings: [],
      errors: [],
      byFile: {},
      command: "iverilog tb.v",
      files: ["tb.v"],
      engine: "iverilog",
    } as never);
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "Override…" }));
    const input = screen.getByRole("combobox", { name: "Override files" });
    fireEvent.change(input, { target: { value: "tb.v" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await waitFor(() =>
      expect(workbenchApi.lint).toHaveBeenCalledWith("s1", { engine: "auto", files: ["tb.v"] })
    );
  });

  it("the facts box keeps the NON-file facts; the file set lives in the override box only (FA22)", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Simulate")!);
    expect(screen.getByText("default tb")).toBeInTheDocument();
    expect(screen.queryByText("files", { selector: "span.w-28" })).toBeNull();
  });
});

describe("CommandSurface — override editors are per command (F4)", () => {
  it("Lint's open override editor does not follow the switch to Simulate", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "Override…" }));
    expect(screen.getByRole("button", { name: "Use manifest set" })).toBeInTheDocument();

    // Both commands name their override param `files` — the box must not be
    // the SAME React instance carrying `editing` across.
    fireEvent.click(railButton("Simulate")!);
    expect(screen.getByTestId("command-surface-override-files")).toHaveTextContent(
      "Supplied by manifest"
    );
    expect(screen.queryByRole("button", { name: "Use manifest set" })).toBeNull();
    expect(screen.getByRole("button", { name: "Override…" })).toBeInTheDocument();
  });
});

// ---- W5: honest async/sync affordances ----------------------------------------

describe("CommandSurface — honest async/sync affordances (W5)", () => {
  afterEach(() => vi.useRealTimers());

  it("a sync run shows the live 'Running — Ns' client clock, then the inline result", async () => {
    vi.useFakeTimers();
    let resolveLint!: (v: unknown) => void;
    vi.mocked(workbenchApi.lint).mockReturnValue(
      new Promise((r) => {
        resolveLint = r;
      }) as never
    );
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    // The counter appears immediately (running state is synchronous)…
    expect(screen.getByTestId("command-surface-elapsed")).toHaveTextContent("Running — 0s");
    // …and advances on the CLIENT clock alone — no fetches involved.
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(screen.getByTestId("command-surface-elapsed")).toHaveTextContent("Running — 2s");
    await act(async () => {
      resolveLint({
        ok: true,
        status: "passed",
        warnings: [],
        errors: [],
        byFile: {},
        command: "iverilog alu.v",
        files: ["alu.v"],
        engine: "iverilog",
      });
    });
    expect(screen.queryByTestId("command-surface-elapsed")).toBeNull();
    expect(screen.getByText(/passed \(iverilog\)/)).toBeInTheDocument();
  });

  it("async dispatch note names the run id; 'View in Runs' opens the dock Runs tab and closes (A22)", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue({
      ok: true,
      runId: "synth_0042",
      pollAfterSec: 5,
    } as never);
    // Prove the gesture EXPANDS a collapsed dock, not just switches tabs.
    useWorkbenchUiStore.getState().setDockTab("s1", "activity");
    useWorkbenchUiStore.getState().setDockCollapsed("s1", true);
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke")); // synth is the default selection
    const note = await screen.findByTestId("command-surface-dispatch-note");
    expect(note).toHaveTextContent("synth_0042");
    fireEvent.click(screen.getByRole("button", { name: "View in Runs" }));
    const ui = useWorkbenchUiStore.getState();
    expect(ui.commandSurfaceOpen).toBe(false); // explicit user gesture closed it
    expect(ui.perSession["s1"].dockTab).toBe("runs");
    expect(ui.perSession["s1"].dockCollapsed).toBe(false);
  });

  it("a failed async dispatch renders the error inline — no dispatch note", async () => {
    vi.mocked(workbenchApi.synthesize).mockRejectedValue(new Error("Quota exceeded."));
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByText("Quota exceeded.");
    expect(screen.queryByTestId("command-surface-dispatch-note")).toBeNull();
  });
});

// ---- adversarial-review findings F1/F3 -----------------------------------------

const SYNTH_DISPATCH = { ok: true, runId: "synth_0042", pollAfterSec: 5 };

const runningSynth = (id: string) => ({
  id,
  kind: "synth" as const,
  status: "running" as const,
  createdAt: null,
  top: "alu",
  pinned: false,
});

describe("CommandSurface — the Dispatch button never silently re-arms (F1)", () => {
  it("after a dispatch the button is disarmed; only an explicit re-arm brings it back", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue(SYNTH_DISPATCH as never);
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke")); // synth is default
    await screen.findByTestId("command-surface-dispatch-note");

    // A second click on a still-live job must not fire.
    expect(screen.getByTestId("command-surface-invoke")).toBeDisabled();
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    expect(workbenchApi.synthesize).toHaveBeenCalledTimes(1);

    // The re-arm is an explicit, honest gesture.
    expect(screen.getByTestId("command-surface-rearm")).toHaveTextContent("synth_0042");
    fireEvent.click(screen.getByRole("button", { name: "Dispatch again?" }));
    expect(screen.getByTestId("command-surface-invoke")).not.toBeDisabled();
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await waitFor(() => expect(workbenchApi.synthesize).toHaveBeenCalledTimes(2));
  });

  it("close → reopen drops the stale note but NOT the guard while the run is live", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue(SYNTH_DISPATCH as never);
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByTestId("command-surface-dispatch-note");
    // The runs refresh lands: the dispatched job is running.
    act(() => {
      useStore.setState({ runs: [runningSynth("synth_0042")] as never });
    });

    act(() => useWorkbenchUiStore.setState({ commandSurfaceOpen: false }));
    act(() => useWorkbenchUiStore.setState({ commandSurfaceOpen: true }));

    // Stale "Dispatched — synth_0042" is gone…
    expect(screen.queryByTestId("command-surface-dispatch-note")).toBeNull();
    // …and the button is NOT silently re-armed under the live run.
    expect(screen.getByTestId("command-surface-invoke")).toBeDisabled();
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    expect(workbenchApi.synthesize).toHaveBeenCalledTimes(1);
  });

  it("a finished run leaves the button armed — the guard is live state, not a lock", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue(SYNTH_DISPATCH as never);
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByTestId("command-surface-dispatch-note");
    act(() => {
      useStore.setState({
        runs: [{ ...runningSynth("synth_0042"), status: "passed" }] as never,
      });
    });
    act(() => useWorkbenchUiStore.setState({ commandSurfaceOpen: false }));
    act(() => useWorkbenchUiStore.setState({ commandSurfaceOpen: true }));
    expect(screen.getByTestId("command-surface-invoke")).not.toBeDisabled();
    expect(screen.queryByTestId("command-surface-rearm")).toBeNull();
  });

  it("sync commands are never gated by a live synth run; the guard reads the registry's producesRun", async () => {
    useStore.setState({ runs: [runningSynth("synth_0007")] as never });
    render(<CommandSurface />);
    // Lint: no producesRun → never gated. Simulate: producesRun "sim" but sync
    // (its inFlight guard is the honest one) → never gated either.
    fireEvent.click(railButton("Lint")!);
    expect(screen.getByTestId("command-surface-invoke")).not.toBeDisabled();
    fireEvent.click(railButton("Simulate")!);
    expect(screen.getByTestId("command-surface-invoke")).not.toBeDisabled();
    // Retry P&R produces synth runs too → gated by the same live read.
    fireEvent.click(railButton("Retry P&R")!);
    expect(screen.getByTestId("command-surface-rearm")).toHaveTextContent(
      "A run of this kind is still running as far as this view knows."
    );
  });
});

describe("CommandSurface — session switch resets the form (F3)", () => {
  it("values, selection and dispatch state do not leak into the next workspace", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue(SYNTH_DISPATCH as never);
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    await screen.findByTestId("command-surface-dispatch-note");
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "verilator" }));
    expect(payloadText()).toContain("verilator");

    act(() => {
      useStore.setState({ currentSession: { ...SESSION, id: "s2", name: "s2" } as never });
    });

    // Back to the default command, with nothing carried over.
    expect(railButton("Synthesize")).toHaveAttribute("aria-current", "true");
    expect(screen.queryByTestId("command-surface-dispatch-note")).toBeNull();
    fireEvent.click(railButton("Lint")!);
    expect(payloadText()).not.toContain("verilator");
  });
});

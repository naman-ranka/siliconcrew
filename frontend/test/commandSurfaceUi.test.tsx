import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

// Command Surface COMPONENT tests (W4+W6, command-surface-simplification):
// the hand-rolled rail filter + keyboard nav, the A23 Esc discipline, the
// KeyRound badge removal (L2), and the sign-in CTA with form-state restore.

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

describe("CommandSurface — rail filter + keyboard (W6)", () => {
  it("renders the four Flow commands and NO sign-in (KeyRound) badges (L2/A19)", () => {
    render(<CommandSurface />);
    for (const label of ["Lint", "Simulate", "Synthesize", "Place & Route"]) {
      expect(railButton(label)).toBeTruthy();
    }
    // The badge render sites are deleted — nothing advertises sign-in.
    expect(document.querySelector('[title="requires sign-in"]')).toBeNull();
  });

  it("filters the rail over label/tool/category and shows an honest empty state", () => {
    render(<CommandSurface />);
    fireEvent.change(filter(), { target: { value: "route" } });
    expect(railButton("Place & Route")).toBeTruthy();
    expect(railButton("Lint")).toBeUndefined();
    // Tool-name match: "retry_pd" is Place & Route's tool.
    fireEvent.change(filter(), { target: { value: "retry_pd" } });
    expect(railButton("Place & Route")).toBeTruthy();
    fireEvent.change(filter(), { target: { value: "zzz-nothing" } });
    expect(screen.getByText("No matching commands.")).toBeInTheDocument();
  });

  it("↑/↓ move the selection through the filtered list; Enter snaps to the first match", () => {
    render(<CommandSurface />);
    // Initial selection is synth.
    expect(railButton("Synthesize")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(filter(), { key: "ArrowDown" });
    expect(railButton("Place & Route")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(filter(), { key: "ArrowUp" });
    expect(railButton("Synthesize")).toHaveAttribute("aria-current", "true");
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
});

describe("CommandSurface — file-override box (W3/A16)", () => {
  it("collapsed by default: manifest chips + an Override… affordance, nothing in the payload", () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    const box = screen.getByTestId("command-surface-override-files");
    expect(box).toHaveTextContent("Supplied by manifest");
    expect(box).toHaveTextContent("alu.v"); // the manifest rtl chip
    // Empty override → the payload stays manifest-driven (no `files` key).
    expect(screen.getByLabelText("tool call payload").textContent).not.toContain('"files"');
  });

  it("Override… swaps in the multi-combo; picked files land in the live payload; reset clears", async () => {
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    fireEvent.click(screen.getByRole("button", { name: "Override…" }));
    const input = screen.getByRole("combobox", { name: "Override files" });
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "alu.v" }));
    expect(screen.getByLabelText("tool call payload").textContent).toContain('"files"');
    expect(screen.getByLabelText("tool call payload").textContent).toContain('"alu.v"');
    // Free entry stays allowed — type a path the suggestions missed.
    fireEvent.change(input, { target: { value: "rtl/custom.v" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByLabelText("tool call payload").textContent).toContain("rtl/custom.v");
    // "Use manifest set" clears the override → payload back to manifest-driven.
    fireEvent.click(screen.getByRole("button", { name: "Use manifest set" }));
    expect(screen.getByLabelText("tool call payload").textContent).not.toContain('"files"');
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
    expect(screen.getByLabelText("tool call payload").textContent).not.toContain(
      "rtl/alu_v2.v"
    );
    // …and on blur it must become a real value, not vanish.
    fireEvent.blur(input);
    expect(screen.getByLabelText("tool call payload").textContent).toContain(
      "rtl/alu_v2.v"
    );
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
});

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

describe("CommandSurface — sign-in CTA + form-state restore (W4/L2)", () => {
  it("a signin_required dispatch renders the CTA; clicking stashes the form state and signs in", async () => {
    vi.mocked(workbenchApi.synthesize).mockRejectedValue(
      Object.assign(new Error("Sign in to run synthesis."), {
        code: "signin_required",
        status: 403,
      })
    );
    render(<CommandSurface />);
    fireEvent.click(screen.getByTestId("command-surface-invoke"));
    const cta = await screen.findByTestId("command-surface-signin-cta");
    // The CTA replaces the raw error string.
    expect(cta).toHaveTextContent("Sign in to run this");
    expect(screen.queryByText("Sign in to run synthesis.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Sign in to run this/ }));
    expect(signIn).toHaveBeenCalledTimes(1);
    const stashed = JSON.parse(sessionStorage.getItem(KEY)!);
    expect(stashed.intent).toMatchObject({
      kind: "surfaceCommand",
      sessionId: "s1",
      commandId: "synth",
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
    expect(screen.getByLabelText("tool call payload").textContent).toContain("verilator");
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

// ---- adversarial-review findings F1/F3/F4 -------------------------------------

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

    // A second click on a still-live PAID job must not fire.
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

  it("sync commands are never gated by a live synth run", async () => {
    useStore.setState({ runs: [runningSynth("synth_0007")] as never });
    render(<CommandSurface />);
    fireEvent.click(railButton("Lint")!);
    expect(screen.getByTestId("command-surface-invoke")).not.toBeDisabled();
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
    expect(screen.getByLabelText("tool call payload").textContent).toContain("verilator");

    act(() => {
      useStore.setState({ currentSession: { ...SESSION, id: "s2", name: "s2" } as never });
    });

    // Back to the default command, with nothing carried over.
    expect(railButton("Synthesize")).toHaveAttribute("aria-current", "true");
    expect(screen.queryByTestId("command-surface-dispatch-note")).toBeNull();
    fireEvent.click(railButton("Lint")!);
    expect(screen.getByLabelText("tool call payload").textContent).not.toContain("verilator");
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

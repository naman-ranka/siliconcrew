import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

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

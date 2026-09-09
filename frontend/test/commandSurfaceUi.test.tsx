import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

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

const railButton = (label: string) =>
  screen
    .getAllByRole("button")
    .find((b) => b.textContent === label || b.textContent === `${label}async`);

const payloadText = () => screen.getByLabelText("tool call payload").textContent ?? "";

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

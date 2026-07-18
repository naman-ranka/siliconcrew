import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { TemplateSummary } from "@/types";

// Launcher-level sign-in-on-intent (component test ported from PR #38's
// harness, adapted to this branch's flow): signed-out New session gates
// BEFORE the modal; stashed intents replay once on the signed_in transition;
// self-host (auth disabled) is never gated.

const signIn = vi.fn();
let authState: Record<string, unknown>;
let storeState: Record<string, unknown>;

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => authState }));
vi.mock("@/lib/store", () => ({
  useStore: Object.assign((sel?: (s: unknown) => unknown) => (sel ? sel(storeState) : storeState), {
    getState: () => storeState,
    setState: (p: Record<string, unknown>) => Object.assign(storeState, p),
  }),
}));
vi.mock("@/lib/workbenchUiStore", () => ({
  useWorkbenchUiStore: Object.assign(() => ({}), {
    getState: () => ({ perSession: {}, setShell: vi.fn() }),
  }),
}));
vi.mock("@/components/branding/Hero", () => ({ Hero: () => <div /> }));
vi.mock("@/components/branding/LandingFooter", () => ({ LandingFooter: () => <div /> }));
vi.mock("@/components/branding/Logo", () => ({ Logo: () => <div /> }));
vi.mock("@/components/auth/AccountChip", () => ({ AccountChip: () => <div /> }));
vi.mock("@/components/workbench/ThemeToggle", () => ({ ThemeToggle: () => <div /> }));
vi.mock("@/components/launcher/CreateSessionModal", () => ({
  CreateSessionModal: () => <div data-testid="create-modal" />,
}));

import { Launcher } from "@/components/launcher/Launcher";

const BASE = {
  sessions: [] as unknown[],
  projects: [] as unknown[],
  sessionsLoading: false,
  sessionsError: null,
  loadSessions: vi.fn(),
  loadProjects: vi.fn(),
  deleteSession: vi.fn(),
  deleteProject: vi.fn(),
  renameSession: vi.fn(),
  renameProject: vi.fn(),
  createProject: vi.fn().mockResolvedValue({ id: "g1" }),
  moveSession: vi.fn(),
  templates: [] as TemplateSummary[],
  templatesError: null as string | null,
  loadTemplates: vi.fn(),
  forkTemplate: vi.fn().mockResolvedValue("forked-id"),
  pushToast: vi.fn(),
};

const KEY = "sc-auth-intent";
const stash = (intent: unknown) =>
  sessionStorage.setItem(KEY, JSON.stringify({ intent, at: Date.now() }));

beforeEach(() => {
  signIn.mockReset();
  sessionStorage.clear();
  storeState = { ...BASE };
  authState = { enabled: true, status: "anonymous", signIn };
});

describe("Launcher — sign-in on intent", () => {
  it("signed-out New session gates BEFORE the modal: sign-in + openCreate stash, no form", () => {
    render(<Launcher />);
    fireEvent.click(screen.getAllByRole("button", { name: /New session/i })[0]);
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(KEY)).toContain("openCreate");
    expect(screen.queryByTestId("create-modal")).not.toBeInTheDocument();
  });

  it("replays a stashed openCreate after sign-in: modal opens, intent cleared", () => {
    stash({ kind: "openCreate", group: null });
    authState = { enabled: true, status: "signed_in", signIn };
    render(<Launcher />);
    expect(screen.getByTestId("create-modal")).toBeInTheDocument();
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("replays a stashed fork after sign-in", async () => {
    const forkTemplate = vi.fn().mockResolvedValue("new-session-id");
    storeState = { ...BASE, forkTemplate };
    stash({ kind: "fork", templateId: "alu4" });
    authState = { enabled: true, status: "signed_in", signIn };
    render(<Launcher />);
    await waitFor(() => expect(forkTemplate).toHaveBeenCalledWith("alu4"));
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("surfaces a failed fork replay instead of a silent dead-end", async () => {
    const forkTemplate = vi.fn().mockRejectedValue(new Error("fork failed"));
    storeState = { ...BASE, forkTemplate };
    stash({ kind: "fork", templateId: "alu4" });
    authState = { enabled: true, status: "signed_in", signIn };
    render(<Launcher />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("fork failed"));
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("does not gate when auth is disabled (self-host): modal opens directly", () => {
    authState = { enabled: false, status: "anonymous", signIn };
    render(<Launcher />);
    fireEvent.click(screen.getAllByRole("button", { name: /New session/i })[0]);
    expect(signIn).not.toHaveBeenCalled();
    expect(screen.getByTestId("create-modal")).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { TemplateSummary } from "@/types";

// Sign-in on intent: a signed-out user who clicks New session (or Fork) triggers
// sign-in with the intent stashed, and it resumes automatically after auth —
// never the doomed 401/403 that used to render "[object Object]".

const signIn = vi.fn();
let authState: Record<string, unknown>;
let storeState: Record<string, unknown>;

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => authState }));
vi.mock("@/lib/store", () => ({ useStore: () => storeState }));
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
  createProject: vi.fn(),
  moveSession: vi.fn(),
  templates: [] as TemplateSummary[],
  templatesError: null as string | null,
  loadTemplates: vi.fn(),
  forkTemplate: vi.fn(),
};

const KEY = "sc-pending-intent";

beforeEach(() => {
  signIn.mockReset();
  sessionStorage.clear();
  storeState = { ...BASE };
  authState = { enabled: true, status: "anonymous", signIn };
});

describe("Launcher — sign-in on intent", () => {
  it("signed-out New session triggers sign-in + stashes intent, and does NOT open the modal", () => {
    render(<Launcher />);
    fireEvent.click(screen.getAllByRole("button", { name: /New session/i })[0]);
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(KEY)).toContain("new_session");
    expect(screen.queryByTestId("create-modal")).not.toBeInTheDocument();
  });

  it("resumes a stashed new_session intent after sign-in (opens modal, clears intent)", () => {
    sessionStorage.setItem(KEY, JSON.stringify({ kind: "new_session", groupName: null }));
    authState = { enabled: true, status: "signed_in", signIn };
    render(<Launcher />);
    expect(screen.getByTestId("create-modal")).toBeInTheDocument();
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("resumes a stashed fork intent after sign-in (forks the template)", () => {
    const forkTemplate = vi.fn().mockResolvedValue("new-session-id");
    storeState = { ...BASE, forkTemplate };
    sessionStorage.setItem(KEY, JSON.stringify({ kind: "fork", templateId: "sync_fifo" }));
    authState = { enabled: true, status: "signed_in", signIn };
    render(<Launcher />);
    expect(forkTemplate).toHaveBeenCalledWith("sync_fifo");
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("does not gate when auth is disabled (self-host): opens the modal directly", () => {
    authState = { enabled: false, status: "anonymous", signIn };
    render(<Launcher />);
    fireEvent.click(screen.getAllByRole("button", { name: /New session/i })[0]);
    expect(signIn).not.toHaveBeenCalled();
    expect(screen.getByTestId("create-modal")).toBeInTheDocument();
  });
});

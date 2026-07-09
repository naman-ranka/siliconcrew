import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { TemplateSummary } from "@/types";

// Item 2 (honest offline): the Launcher renders an "unable to connect" + Retry
// panel when the gallery errored with nothing cached, and keeps cached
// templates visible when a refresh errors (SWR last-good).

const loadTemplates = vi.fn();

// A mutable store snapshot the mocked useStore returns; each test sets the
// template slice it needs.
let storeState: Record<string, unknown>;

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ status: "authenticated" }) }));
vi.mock("@/lib/store", () => ({ useStore: () => storeState }));
vi.mock("@/lib/workbenchUiStore", () => ({
  useWorkbenchUiStore: Object.assign(() => ({}), { getState: () => ({ perSession: {} }) }),
}));

// Stub heavy/irrelevant children so the test isolates the gallery slot.
vi.mock("@/components/branding/Hero", () => ({ Hero: () => <div /> }));
vi.mock("@/components/branding/LandingFooter", () => ({ LandingFooter: () => <div /> }));
vi.mock("@/components/branding/Logo", () => ({ Logo: () => <div /> }));
vi.mock("@/components/auth/AccountChip", () => ({ AccountChip: () => <div /> }));
vi.mock("@/components/workbench/ThemeToggle", () => ({ ThemeToggle: () => <div /> }));
vi.mock("@/components/launcher/ExampleCard", () => ({
  ExampleCard: ({ template }: { template: TemplateSummary }) => (
    <div data-testid={`example-card-${template.id}`}>{template.name}</div>
  ),
}));

import { Launcher } from "@/components/launcher/Launcher";

const BASE = {
  sessions: [],
  projects: [],
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
  loadTemplates,
  forkTemplate: vi.fn(),
};

const TEMPLATE: TemplateSummary = {
  id: "sync_fifo",
  name: "Synchronous FIFO",
  description: "d",
  highlights: ["h"],
  top_module: "sync_fifo",
  platform: "sky130hd",
  source_note: null,
  file_count: 12,
  run_count: 2,
};

beforeEach(() => {
  loadTemplates.mockReset();
  storeState = { ...BASE };
});

describe("Launcher — templates honest offline", () => {
  it("shows the unable-to-connect panel when the gallery errored with nothing cached", () => {
    storeState = { ...BASE, templates: [], templatesError: "Template gallery is unreachable" };
    render(<Launcher />);
    expect(screen.getByTestId("examples-unavailable")).toBeInTheDocument();
    // NOT the populated gallery.
    expect(screen.queryByTestId("examples-section")).not.toBeInTheDocument();
  });

  it("Retry re-triggers loadTemplates", () => {
    storeState = { ...BASE, templates: [], templatesError: "unreachable" };
    render(<Launcher />);
    fireEvent.click(screen.getByTestId("retry-templates"));
    expect(loadTemplates).toHaveBeenCalled();
  });

  it("keeps the cached gallery (not the panel) when a refresh errors", () => {
    storeState = { ...BASE, templates: [TEMPLATE], templatesError: "unreachable" };
    render(<Launcher />);
    // Cached templates win: the populated section shows, the panel does not.
    expect(screen.getByTestId("examples-section")).toBeInTheDocument();
    expect(screen.getByTestId("example-card-sync_fifo")).toBeInTheDocument();
    expect(screen.queryByTestId("examples-unavailable")).not.toBeInTheDocument();
  });

  it("shows no gallery slot when there is no error and no templates", () => {
    storeState = { ...BASE, templates: [], templatesError: null };
    render(<Launcher />);
    expect(screen.queryByTestId("examples-unavailable")).not.toBeInTheDocument();
    expect(screen.queryByTestId("examples-section")).not.toBeInTheDocument();
  });
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { useState } from "react";

// Regression test for a production bug found via Cloud Run access-log
// analysis: opening the "New session" modal fired a tight, self-sustaining
// burst of duplicate GET /api/projects calls (~28 calls / 6s) until the
// modal closed. Root cause: CreateSessionModal's data-fetch effect depended
// on `onClose`, and every parent host of the modal (NavRail, Launcher)
// subscribes to the WHOLE Zustand store with no selector — so the instant
// `loadProjects()` resolved and updated the store, the host re-rendered,
// handed the modal a brand-new inline `onClose` closure, and the effect's
// changed dependency re-fired it, calling `loadProjects()` again, forever.
//
// This harness reproduces the loop's two necessary ingredients without
// needing the full NavRail tree:
//   1. A host component that re-renders on every store change (mirrors
//      NavRail's/Launcher's unscoped `useStore()` destructuring).
//   2. A fresh inline `onClose` closure created on each of the host's
//      renders (mirrors `<CreateSessionModal onClose={() => setX(false)} />`
//      at the NavRail/Launcher call sites).

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn() },
  modelsApi: { list: vi.fn() },
  sessionsApi: {},
  threadsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { useStore } from "@/lib/store";
import { projectsApi, modelsApi } from "@/lib/api";
import { CreateSessionModal } from "@/components/launcher/CreateSessionModal";

function Host() {
  // Mirrors NavRail/Launcher: an UNSCOPED store subscription, so this host
  // re-renders on every `set()` call anywhere in the store (e.g. the
  // `set({ projects })` inside loadProjects).
  useStore();
  const [open, setOpen] = useState(true);
  if (!open) return null;
  // A NEW arrow function every render — the reproduction's second ingredient.
  return <CreateSessionModal onClose={() => setOpen(false)} />;
}

describe("CreateSessionModal — no self-sustaining refetch loop", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStore.setState({
      projects: [],
      models: [],
      modelsLoaded: false,
      defaultModel: null,
    } as any);
  });

  it("calls projectsApi.list / modelsApi.list a small, bounded number of times even while the host re-renders with a fresh onClose on every store update", async () => {
    (projectsApi.list as any).mockResolvedValue([{ id: "p1", name: "Demo" }]);
    (modelsApi.list as any).mockResolvedValue({ models: [], default: "gemini-3.5-flash" });

    await act(async () => {
      render(<Host />);
      // Give any pending promise chains / re-renders room to run. If the
      // loop is present, this window is enough for it to fire many times
      // (production observed ~5 calls/sec); if fixed, nothing further
      // happens after the initial mount fetch.
      await new Promise((r) => setTimeout(r, 300));
    });

    expect((projectsApi.list as any).mock.calls.length).toBeLessThanOrEqual(2);
    expect((modelsApi.list as any).mock.calls.length).toBeLessThanOrEqual(2);
  });
});

import { describe, it, expect } from "vitest";
import { shouldShowOnboarding } from "@/components/workbench/Workbench";

const base = {
  currentSession: { id: "s1" },
  manifest: { files: [] as unknown[] },
  runs: [] as unknown[],
  manifestLoading: false,
  runsLoading: false,
  activeArtifactTab: "spec",
};

describe("shouldShowOnboarding", () => {
  it("shows onboarding once a session's empty workbench has loaded", () => {
    expect(shouldShowOnboarding(base)).toBe(true);
  });

  it("does NOT show during initial load (manifest still null) — fixes the flash", () => {
    expect(shouldShowOnboarding({ ...base, manifest: null })).toBe(false);
  });

  it("does NOT show while manifest/runs are mid-fetch", () => {
    expect(shouldShowOnboarding({ ...base, manifestLoading: true })).toBe(false);
    expect(shouldShowOnboarding({ ...base, runsLoading: true })).toBe(false);
  });

  it("does NOT show when the workspace has files", () => {
    expect(shouldShowOnboarding({ ...base, manifest: { files: [{}] } })).toBe(false);
  });

  it("does NOT show when there are runs", () => {
    expect(shouldShowOnboarding({ ...base, runs: [{}] })).toBe(false);
  });

  it("does NOT show without a session, or while editing code", () => {
    expect(shouldShowOnboarding({ ...base, currentSession: null })).toBe(false);
    expect(shouldShowOnboarding({ ...base, activeArtifactTab: "code" })).toBe(false);
  });
});

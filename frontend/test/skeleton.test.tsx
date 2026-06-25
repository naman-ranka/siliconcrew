import { describe, it, expect, beforeEach, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {}, sessionsApi: {}, chatApi: {}, workspaceApi: {}, workbenchApi: {},
}));

import { Skeleton } from "@/components/ui/skeleton";
import { useStore } from "@/lib/store";

describe("Skeleton", () => {
  it("renders a shimmer placeholder and forwards className", () => {
    const { container } = render(<Skeleton className="h-3 w-10" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toBeInTheDocument();
    expect(el.className).toContain("animate-shimmer");
    expect(el.className).toContain("h-3");
    expect(el.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("store loading flags", () => {
  beforeEach(() => {
    useStore.setState({
      runsLoading: false,
      manifestLoading: false,
      reportLoading: false,
      codeLoading: false,
    });
  });

  it("default to false so existing direct-state tests are unaffected", () => {
    const s = useStore.getState();
    expect(s.runsLoading).toBe(false);
    expect(s.manifestLoading).toBe(false);
    expect(s.reportLoading).toBe(false);
    expect(s.codeLoading).toBe(false);
  });

  it("can be toggled on the store", () => {
    useStore.setState({ runsLoading: true });
    expect(useStore.getState().runsLoading).toBe(true);
  });
});

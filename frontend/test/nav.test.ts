import { describe, it, expect } from "vitest";
import { openSession, sessionUrl } from "@/lib/nav";

// S1 URL contract: /w/{sessionId}?chat={threadId}&view=agent|ide, with each
// path segment encoded individually so project-scoped ids (containing `/`)
// keep their segment structure.
describe("sessionUrl", () => {
  it("builds the plain session URL", () => {
    expect(sessionUrl("demo")).toBe("/w/demo");
  });

  it("preserves `/` structure in project-scoped ids, encoding each segment", () => {
    expect(sessionUrl("proj a/blk#1")).toBe("/w/proj%20a/blk%231");
  });

  it("appends chat and view query params when given", () => {
    expect(sessionUrl("demo", { chat: "t2", view: "ide" })).toBe("/w/demo?chat=t2&view=ide");
    expect(sessionUrl("demo", { chat: "t2" })).toBe("/w/demo?chat=t2");
    expect(sessionUrl("demo", { view: "agent" })).toBe("/w/demo?view=agent");
  });

  it("omits empty/null opts entirely", () => {
    expect(sessionUrl("demo", { chat: null, view: null })).toBe("/w/demo");
  });
});

describe("openSession", () => {
  it("pushes the built URL onto the router", () => {
    const pushed: string[] = [];
    openSession({ push: (href) => void pushed.push(href) }, "demo", { chat: "t1" });
    expect(pushed).toEqual(["/w/demo?chat=t1"]);
  });
});

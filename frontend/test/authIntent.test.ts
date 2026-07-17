import { beforeEach, describe, expect, it } from "vitest";
import { stashAuthIntent, takeAuthIntent } from "@/lib/authIntent";

// E2 (onboarding wave): the signed-out intent stash. take() must clear before
// returning so a failed replay can never loop, and malformed storage must
// never throw into the replay effect.
describe("authIntent", () => {
  beforeEach(() => sessionStorage.clear());

  it("round-trips a create intent and clears on take", () => {
    stashAuthIntent({ kind: "create", name: "my fifo", posture: "ide", group: "demos" });
    expect(takeAuthIntent()).toEqual({ kind: "create", name: "my fifo", posture: "ide", group: "demos" });
    expect(takeAuthIntent()).toBeNull(); // read-and-clear: second take is empty
  });

  it("round-trips fork and createGroup intents", () => {
    stashAuthIntent({ kind: "fork", templateId: "alu4" });
    expect(takeAuthIntent()).toEqual({ kind: "fork", templateId: "alu4" });
    stashAuthIntent({ kind: "createGroup", name: "uni" });
    expect(takeAuthIntent()).toEqual({ kind: "createGroup", name: "uni" });
  });

  it("returns null with nothing stashed", () => {
    expect(takeAuthIntent()).toBeNull();
  });

  it("clears and returns null on malformed or unknown-kind payloads", () => {
    sessionStorage.setItem("sc-auth-intent", "{not json");
    expect(takeAuthIntent()).toBeNull();
    expect(sessionStorage.getItem("sc-auth-intent")).toBeNull();

    sessionStorage.setItem("sc-auth-intent", JSON.stringify({ kind: "evil" }));
    expect(takeAuthIntent()).toBeNull();
    expect(sessionStorage.getItem("sc-auth-intent")).toBeNull();
  });
});

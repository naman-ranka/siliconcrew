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

  it("expires abandoned intents instead of replaying them later", () => {
    // Adversarial-review finding: an abandoned sign-in must not leave a
    // landmine that fires (with navigation) on a voluntary sign-in later.
    sessionStorage.setItem(
      "sc-auth-intent",
      JSON.stringify({ intent: { kind: "fork", templateId: "alu4" }, at: Date.now() - 16 * 60 * 1000 })
    );
    expect(takeAuthIntent()).toBeNull();
    expect(sessionStorage.getItem("sc-auth-intent")).toBeNull();
  });

  it("kind filter takes only matching intents and leaves others in place", () => {
    stashAuthIntent({ kind: "fork", templateId: "alu4" });
    expect(takeAuthIntent("create")).toBeNull(); // not ours — left stashed
    expect(takeAuthIntent()).toEqual({ kind: "fork", templateId: "alu4" });
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

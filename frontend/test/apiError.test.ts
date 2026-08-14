import { describe, expect, it } from "vitest";
import { extractErrorCode, extractErrorMessage, isSignInRequired } from "@/lib/api";

// E1 (onboarding wave): every backend error shape must reduce to a readable
// string — the signed-out create/fork regression rendered "[object Object]"
// because Error() stringified the auth dep's {code, message} detail object.
describe("extractErrorMessage", () => {
  it("passes through a plain-string detail", () => {
    expect(extractErrorMessage({ detail: "Session not found" }, "x")).toBe("Session not found");
  });

  it("extracts the auth-dep {code, message} detail (the [object Object] case)", () => {
    const body = { detail: { code: "signin_required", message: "Sign in to continue." } };
    expect(extractErrorMessage(body, "x")).toBe("Sign in to continue.");
  });

  it("extracts an envelope-in-HTTPException detail", () => {
    const body = { detail: { error: { code: "no_rtl", message: "No RTL files to lint." } } };
    expect(extractErrorMessage(body, "x")).toBe("No RTL files to lint.");
  });

  it("joins pydantic-422 array details instead of stringifying", () => {
    const body = { detail: [{ loc: ["body", "name"], msg: "field required" }, { msg: "value error" }] };
    expect(extractErrorMessage(body, "x")).toBe("field required; value error");
  });

  it("extracts top-level envelope errors", () => {
    expect(extractErrorMessage({ ok: false, error: { message: "Quota exceeded." } }, "x")).toBe("Quota exceeded.");
    expect(extractErrorMessage({ error: "boom" }, "x")).toBe("boom");
    expect(extractErrorMessage({ message: "plain" }, "x")).toBe("plain");
  });

  it("falls back on null, non-objects, and empty shapes", () => {
    expect(extractErrorMessage(null, "fallback")).toBe("fallback");
    expect(extractErrorMessage(undefined, "fallback")).toBe("fallback");
    expect(extractErrorMessage({}, "fallback")).toBe("fallback");
    expect(extractErrorMessage({ detail: {} }, "fallback")).toBe("fallback");
    expect(extractErrorMessage({ detail: [] }, "fallback")).toBe("fallback");
    expect(extractErrorMessage(42, "fallback")).toBe("fallback");
  });

  it("never returns [object Object] for any nested-object shape", () => {
    const shapes = [
      { detail: { code: "x", message: "m" } },
      { detail: { weird: true } },
      { detail: [{ loc: [] }] },
      { error: { nested: {} } },
    ];
    for (const s of shapes) {
      expect(extractErrorMessage(s, "fallback")).not.toContain("object Object");
    }
  });
});

// W4/A17: the CTA is detected by CODE — across the core twins' 403 detail
// shape AND /invoke's 401 _err envelope — never by message text.
describe("extractErrorCode", () => {
  it("reads the auth-dep detail {code} (core twins' 403)", () => {
    expect(
      extractErrorCode({ detail: { code: "signin_required", message: "Sign in." } })
    ).toBe("signin_required");
  });

  it("reads the _err envelope-in-HTTPException (/invoke's 401)", () => {
    expect(
      extractErrorCode({
        detail: {
          ok: false,
          error: { code: "signin_required", message: "'start_synthesis' requires signing in.", details: {} },
        },
      })
    ).toBe("signin_required");
  });

  it("reads a top-level { ok:false, error:{code} } envelope", () => {
    expect(extractErrorCode({ ok: false, error: { code: "no_rtl", message: "x" } })).toBe("no_rtl");
  });

  it("returns undefined for codeless shapes", () => {
    expect(extractErrorCode({ detail: "plain string" })).toBeUndefined();
    expect(extractErrorCode({ detail: [{ msg: "field required" }] })).toBeUndefined();
    expect(extractErrorCode(null)).toBeUndefined();
    expect(extractErrorCode({})).toBeUndefined();
  });
});

describe("isSignInRequired", () => {
  it("matches only errors carrying code=signin_required", () => {
    expect(isSignInRequired(Object.assign(new Error("x"), { code: "signin_required" }))).toBe(true);
    expect(isSignInRequired(Object.assign(new Error("x"), { code: "no_rtl" }))).toBe(false);
    // Message text alone must NOT trigger the CTA.
    expect(isSignInRequired(new Error("'start_synthesis' requires signing in."))).toBe(false);
    expect(isSignInRequired(null)).toBe(false);
  });
});

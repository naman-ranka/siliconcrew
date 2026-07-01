import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getAuthToken,
  authHeader,
  setAuthTokenGetter,
  setOnAuthExpired,
  notifyAuthExpired,
  recoverAuthExpired,
} from "@/lib/authToken";
import { sessionsApi, workbenchApi } from "@/lib/api";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "x",
    json: async () => body,
  });
}

function lastHeaders(f: ReturnType<typeof vi.fn>): Record<string, string> {
  return (f.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
}

function nthHeaders(f: ReturnType<typeof vi.fn>, index: number): Record<string, string> {
  return (f.mock.calls[index][1] as RequestInit).headers as Record<string, string>;
}

beforeEach(() => {
  setAuthTokenGetter(() => null);
  setOnAuthExpired(null);
  vi.restoreAllMocks();
});

describe("authToken seam", () => {
  it("defaults to no token and an empty header (unconfigured/self-host path)", () => {
    expect(getAuthToken()).toBeNull();
    expect(authHeader()).toEqual({});
  });

  it("returns the registered token + Bearer header", () => {
    setAuthTokenGetter(() => "abc");
    expect(getAuthToken()).toBe("abc");
    expect(authHeader()).toEqual({ Authorization: "Bearer abc" });
  });

  it("notifyAuthExpired invokes the registered handler", () => {
    const spy = vi.fn();
    setOnAuthExpired(spy);
    notifyAuthExpired();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("recoverAuthExpired awaits the registered async handler", async () => {
    const spy = vi.fn(async () => {});
    setOnAuthExpired(spy);
    await recoverAuthExpired();
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("api.ts token attachment", () => {
  it("apiFetch omits Authorization when no token", async () => {
    const f = mockFetch(200, []);
    global.fetch = f as unknown as typeof fetch;
    await sessionsApi.list();
    expect(lastHeaders(f).Authorization).toBeUndefined();
  });

  it("apiFetch attaches Bearer when a token is present", async () => {
    setAuthTokenGetter(() => "tok123");
    const f = mockFetch(200, []);
    global.fetch = f as unknown as typeof fetch;
    await sessionsApi.list();
    expect(lastHeaders(f).Authorization).toBe("Bearer tok123");
  });

  it("actionFetch attaches Bearer when a token is present", async () => {
    setAuthTokenGetter(() => "tok123");
    const f = mockFetch(200, { ok: true, runs: [] });
    global.fetch = f as unknown as typeof fetch;
    await workbenchApi.listRuns("s1");
    expect(lastHeaders(f).Authorization).toBe("Bearer tok123");
  });

  it("uploadFiles attaches Bearer and never sets Content-Type", async () => {
    setAuthTokenGetter(() => "tok123");
    const f = mockFetch(200, { ok: true, uploaded: [], manifest: {} });
    global.fetch = f as unknown as typeof fetch;
    await workbenchApi.uploadFiles("s1", []);
    const h = lastHeaders(f);
    expect(h.Authorization).toBe("Bearer tok123");
    expect(h["Content-Type"]).toBeUndefined();
  });

  it("a 401 response notifies the auth layer (drop to anonymous)", async () => {
    const spy = vi.fn();
    setOnAuthExpired(spy);
    const f = mockFetch(401, { detail: "invalid token" });
    global.fetch = f as unknown as typeof fetch;
    await expect(sessionsApi.list()).rejects.toThrow();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("retries once after auth recovery swaps in a fresh token", async () => {
    let token = "old-token";
    setAuthTokenGetter(() => token);
    setOnAuthExpired(async () => {
      token = "new-token";
    });
    const f = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: async () => ({ detail: "invalid token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => [],
      });
    global.fetch = f as unknown as typeof fetch;

    await expect(sessionsApi.list()).resolves.toEqual([]);
    expect(f).toHaveBeenCalledTimes(2);
    expect(nthHeaders(f, 0).Authorization).toBe("Bearer old-token");
    expect(nthHeaders(f, 1).Authorization).toBe("Bearer new-token");
  });
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { keysApi } from "@/lib/api";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "x",
    json: async () => body,
  });
}

beforeEach(() => vi.restoreAllMocks());

describe("keysApi contract", () => {
  it("list GETs /api/keys and returns providers", async () => {
    const f = mockFetch(200, { providers: ["anthropic"] });
    global.fetch = f as unknown as typeof fetch;
    const r = await keysApi.list();
    expect(r.providers).toEqual(["anthropic"]);
    const [url, opts] = f.mock.calls[0];
    expect(String(url)).toContain("/api/keys");
    expect((opts as RequestInit | undefined)?.method ?? "GET").toBe("GET");
  });

  it("save PUTs /api/keys/{provider} with { api_key } (never logs/returns the key)", async () => {
    const f = mockFetch(200, { ok: true, provider: "openai", stored: true });
    global.fetch = f as unknown as typeof fetch;
    await keysApi.save("openai", "sk-secret");
    const [url, opts] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/keys/openai");
    expect(opts.method).toBe("PUT");
    expect(JSON.parse(opts.body as string)).toEqual({ api_key: "sk-secret" });
  });

  it("remove DELETEs /api/keys/{provider}", async () => {
    const f = mockFetch(200, { ok: true, provider: "gemini", deleted: true });
    global.fetch = f as unknown as typeof fetch;
    await keysApi.remove("gemini");
    const [url, opts] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/keys/gemini");
    expect(opts.method).toBe("DELETE");
  });

  it("attaches the HTTP status on error (so callers branch on 400/503)", async () => {
    const f = mockFetch(503, { detail: "BYOK key storage is not configured on this server." });
    global.fetch = f as unknown as typeof fetch;
    await expect(keysApi.list()).rejects.toMatchObject({ status: 503 });
  });
});

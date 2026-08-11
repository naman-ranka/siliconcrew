// @vitest-environment node
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { NextRequest } from "next/server";

// Issue #93 Bug 4: the Next `/api/*` proxy 502'd on every hosted request
// because it read NEXT_PUBLIC_API_URL — inlined at BUILD time, and never set —
// so it always dialled http://localhost:8000. It also gave up after one
// attempt on a transport failure that is safe to replay for reads.

import { GET, POST } from "@/app/api/[...path]/route";

const params = (path: string[]) => ({ params: { path } });
const req = (url: string, init?: RequestInit) => new NextRequest(new Request(url, init));

const OLD_ENV = { ...process.env };

beforeEach(() => {
  vi.restoreAllMocks();
  process.env.API_URL = "https://backend.example";
  delete process.env.NEXT_PUBLIC_API_URL;
});

afterEach(() => {
  process.env = { ...OLD_ENV };
});

describe("Next API proxy", () => {
  it("targets the RUNTIME backend origin (API_URL), not the build-time one", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/health?x=1"), params(["health"]));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("https://backend.example/api/health?x=1");
    expect(res.status).toBe(200);
  });

  it("falls back to NEXT_PUBLIC_API_URL only when API_URL is unset", async () => {
    delete process.env.API_URL;
    process.env.NEXT_PUBLIC_API_URL = "https://legacy.example";
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await GET(req("http://localhost:3000/api/health"), params(["health"]));

    expect(fetchMock.mock.calls[0][0]).toBe("https://legacy.example/api/health");
  });

  it("retries a transport failure for a safe read, then succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/sessions"), params(["sessions"]));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(res.status).toBe(200);
  });

  it("NEVER retries a mutating request", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(
      req("http://localhost:3000/api/sessions", { method: "POST", body: '{"name":"a"}' }),
      params(["sessions"])
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(502);
  });

  it("does not retry a TIMEOUT — a slow backend must not be hit again", async () => {
    // AbortSignal.timeout rejects with a TimeoutError; retrying it would hold
    // the caller for another full ceiling against a backend that is alive.
    const fetchMock = vi
      .fn()
      .mockRejectedValue(Object.assign(new Error("timed out"), { name: "TimeoutError" }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/sessions"), params(["sessions"]));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(502);
  });

  it("does not retry a received HTTP status — the backend answered", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/sessions"), params(["sessions"]));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(500);
  });

  it("surfaces the real cause but NEVER the internal backend origin", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/health"), params(["health"]));
    const body = await res.json();

    expect(res.status).toBe(502);
    expect(body.detail).toContain("fetch failed");
    // This body reaches any anonymous caller of the public frontend origin.
    expect(body.detail).not.toContain("backend.example");
  });

  it("passes a 304 through instead of throwing on its null-body status", async () => {
    // `new Response(blob, {status: 304})` throws; that TypeError used to be
    // caught by the transport handler and misreported as an unreachable
    // backend — a correct answer turned into a 502 that blamed the network.
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 304 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/health"), params(["health"]));

    expect(res.status).toBe(304);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps request content-encoding but re-frames content-length", async () => {
    // undici decodes responses, not requests: stripping the request's
    // content-encoding would forward still-encoded bytes as if they were plain.
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await POST(
      req("http://localhost:3000/api/sessions", {
        method: "POST",
        body: "gzipped-bytes",
        headers: { "content-encoding": "gzip", "content-length": "13", "x-keep": "1" },
      }),
      params(["sessions"])
    );

    const sent = fetchMock.mock.calls[0][1].headers as Headers;
    expect(sent.get("content-encoding")).toBe("gzip");
    expect(sent.get("content-length")).toBeNull();
    expect(sent.get("x-keep")).toBe("1");
  });

  it("drops hop-by-hop response headers (undici already decoded the body)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-encoding": "gzip", "x-trace": "abc" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(req("http://localhost:3000/api/health"), params(["health"]));

    expect(res.headers.get("content-encoding")).toBeNull();
    expect(res.headers.get("x-trace")).toBe("abc");
  });
});

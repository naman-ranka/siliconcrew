import { describe, it, expect, afterEach, vi } from "vitest";
import { getApiBase, getWsBase, getRuntimeEnv, readServerEnv } from "@/lib/runtime-config";

afterEach(() => {
  delete (window as any).__SC_ENV__;
  vi.unstubAllEnvs();
});

describe("runtime-config (client)", () => {
  it("reads URLs injected into window.__SC_ENV__", () => {
    (window as any).__SC_ENV__ = {
      apiUrl: "https://api.example.run.app",
      wsUrl: "wss://api.example.run.app",
    };
    expect(getApiBase()).toBe("https://api.example.run.app");
    expect(getWsBase()).toBe("wss://api.example.run.app");
  });

  it("falls back to local dev defaults when nothing is injected", () => {
    expect(getRuntimeEnv()).toEqual({
      apiUrl: "http://localhost:8000",
      wsUrl: "ws://localhost:8000",
    });
  });
});

describe("runtime-config (server)", () => {
  it("reads API_URL/WS_URL at request time", () => {
    vi.stubEnv("API_URL", "https://backend.run.app");
    vi.stubEnv("WS_URL", "wss://backend.run.app");
    expect(readServerEnv()).toEqual({
      apiUrl: "https://backend.run.app",
      wsUrl: "wss://backend.run.app",
    });
  });

  it("derives the ws(s) URL from API_URL when WS_URL is unset", () => {
    vi.stubEnv("API_URL", "https://backend.run.app");
    vi.stubEnv("WS_URL", "");
    expect(readServerEnv().wsUrl).toBe("wss://backend.run.app");
  });

  it("defaults to localhost when no env is set", () => {
    vi.stubEnv("API_URL", "");
    vi.stubEnv("WS_URL", "");
    expect(readServerEnv()).toEqual({
      apiUrl: "http://localhost:8000",
      wsUrl: "ws://localhost:8000",
    });
  });
});

import { describe, it, expect, afterEach, vi } from "vitest";
import {
  getApiBase,
  getWsBase,
  getGoogleClientId,
  getRuntimeEnv,
  readServerEnv,
} from "@/lib/runtime-config";

afterEach(() => {
  delete (window as any).__SC_ENV__;
  vi.unstubAllEnvs();
});

describe("runtime-config (client)", () => {
  it("reads values injected into window.__SC_ENV__", () => {
    (window as any).__SC_ENV__ = {
      apiUrl: "https://api.example.run.app",
      wsUrl: "wss://api.example.run.app",
      googleClientId: "cid.apps.googleusercontent.com",
    };
    expect(getApiBase()).toBe("https://api.example.run.app");
    expect(getWsBase()).toBe("wss://api.example.run.app");
    expect(getGoogleClientId()).toBe("cid.apps.googleusercontent.com");
  });

  it("falls back to local dev defaults when nothing is injected", () => {
    expect(getRuntimeEnv()).toEqual({
      apiUrl: "http://localhost:8000",
      wsUrl: "ws://localhost:8000",
      googleClientId: "",
      workosClientId: "",
      workosRedirectUri: "",
    });
  });
});

describe("runtime-config (server)", () => {
  it("reads API_URL/WS_URL/GOOGLE_CLIENT_ID at request time", () => {
    vi.stubEnv("API_URL", "https://backend.run.app");
    vi.stubEnv("WS_URL", "wss://backend.run.app");
    vi.stubEnv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com");
    expect(readServerEnv()).toEqual({
      apiUrl: "https://backend.run.app",
      wsUrl: "wss://backend.run.app",
      googleClientId: "cid.apps.googleusercontent.com",
      workosClientId: "",
      workosRedirectUri: "",
    });
  });

  it("derives the ws(s) URL from API_URL when WS_URL is unset", () => {
    vi.stubEnv("API_URL", "https://backend.run.app");
    vi.stubEnv("WS_URL", "");
    expect(readServerEnv().wsUrl).toBe("wss://backend.run.app");
  });

  it("falls back to NEXT_PUBLIC_GOOGLE_CLIENT_ID for back-compat", () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "legacy.apps.googleusercontent.com");
    expect(readServerEnv().googleClientId).toBe("legacy.apps.googleusercontent.com");
  });

  it("defaults to localhost + no OAuth when no env is set", () => {
    vi.stubEnv("API_URL", "");
    vi.stubEnv("WS_URL", "");
    vi.stubEnv("GOOGLE_CLIENT_ID", "");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "");
    expect(readServerEnv()).toEqual({
      apiUrl: "http://localhost:8000",
      wsUrl: "ws://localhost:8000",
      googleClientId: "",
      workosClientId: "",
      workosRedirectUri: "",
    });
  });

  it("reads WORKOS_CLIENT_ID / WORKOS_REDIRECT_URI at request time", () => {
    vi.stubEnv("WORKOS_CLIENT_ID", "client_01HX");
    vi.stubEnv("WORKOS_REDIRECT_URI", "https://app.example.run.app/");
    const env = readServerEnv();
    expect(env.workosClientId).toBe("client_01HX");
    expect(env.workosRedirectUri).toBe("https://app.example.run.app/");
  });
});

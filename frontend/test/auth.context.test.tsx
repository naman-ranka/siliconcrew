import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import {
  AuthProvider,
  useAuth,
  decodeJwt,
  jwtExpired,
  userFromToken,
  authEnabled,
} from "@/lib/auth";
import { notifyAuthExpired } from "@/lib/authToken";

const STORAGE_KEY = "sc-auth-token";

// Build an unpadded base64url JWT (header.payload.sig), like a real Google token.
function makeJwt(payload: Record<string, unknown>): string {
  const b64url = (o: unknown) =>
    Buffer.from(JSON.stringify(o))
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
  return `${b64url({ alg: "none" })}.${b64url(payload)}.sig`;
}
const future = () => Math.floor(Date.now() / 1000) + 3600;

function Probe() {
  const a = useAuth();
  return (
    <div>
      <span data-testid="enabled">{String(a.enabled)}</span>
      <span data-testid="status">{a.status}</span>
      <span data-testid="email">{a.user?.email ?? "none"}</span>
      <span data-testid="token">{a.token ?? "none"}</span>
    </div>
  );
}

beforeEach(() => {
  vi.unstubAllEnvs();
  sessionStorage.clear();
  document.querySelectorAll('script[src*="gsi/client"]').forEach((s) => s.remove());
});
afterEach(() => vi.unstubAllEnvs());

describe("jwt helpers (display only)", () => {
  it("decodes the payload and builds a display user", () => {
    const t = makeJwt({ email: "a@b.com", name: "A", picture: "p", exp: future() });
    expect(decodeJwt(t)?.email).toBe("a@b.com");
    expect(userFromToken(t)).toEqual({ email: "a@b.com", name: "A", picture: "p" });
  });

  it("jwtExpired: true for past exp, false for future", () => {
    expect(jwtExpired(makeJwt({ exp: 1 }))).toBe(true);
    expect(jwtExpired(makeJwt({ exp: future() }))).toBe(false);
  });

  it("decodeJwt returns null on garbage (never throws)", () => {
    expect(decodeJwt("not-a-jwt")).toBeNull();
    expect(decodeJwt("")).toBeNull();
  });
});

describe("config gating", () => {
  it("UNSET client id → disabled: no token, no GIS script, anonymous", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    expect(authEnabled()).toBe(false);
    expect(screen.getByTestId("enabled").textContent).toBe("false");
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(screen.getByTestId("token").textContent).toBe("none");
    expect(document.querySelector('script[src*="gsi/client"]')).toBeNull();
  });

  it("SET client id → enabled: loads GIS script and restores a valid stored token", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com");
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", name: "U", exp: future() }));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    expect(authEnabled()).toBe(true);
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));
    expect(screen.getByTestId("email").textContent).toBe("u@x.com");
    expect(document.querySelector('script[src*="gsi/client"]')).not.toBeNull();
  });

  it("expired stored token → anonymous and cleared from storage", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "test-client");
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", exp: 1 }));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("a 401 (notifyAuthExpired) clears the token → anonymous", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "test-client");
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", exp: future() }));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));
    act(() => notifyAuthExpired());
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(screen.getByTestId("token").textContent).toBe("none");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

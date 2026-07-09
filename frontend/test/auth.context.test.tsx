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
import { notifyAuthExpired, authHeader } from "@/lib/authToken";

// Mock the WorkOS AuthKit SDK (dynamically imported by the WorkOS path). The
// Google-path tests never trigger the dynamic import, so this is inert for them.
const workosMocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  getAccessToken: vi.fn(),
  getUser: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  dispose: vi.fn(),
}));
vi.mock("@workos-inc/authkit-js", () => ({
  createClient: workosMocks.createClient,
}));

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
  localStorage.clear();
  document.cookie = "workos-has-session=; Max-Age=0; path=/";
  document.querySelectorAll('script[src*="gsi/client"]').forEach((s) => s.remove());
  workosMocks.createClient.mockReset();
  workosMocks.getAccessToken.mockReset();
  workosMocks.getUser.mockReset();
  workosMocks.signIn.mockReset();
  workosMocks.signOut.mockReset();
  workosMocks.dispose.mockReset();
  workosMocks.getAccessToken.mockResolvedValue("workos-access-token");
  workosMocks.getUser.mockReturnValue({
    email: "w@x.io",
    firstName: "Wanda",
    lastName: "OS",
    profilePictureUrl: "pic",
  });
  workosMocks.signIn.mockResolvedValue(undefined);
  workosMocks.signOut.mockResolvedValue(undefined);
  workosMocks.createClient.mockResolvedValue({
    getAccessToken: workosMocks.getAccessToken,
    getUser: workosMocks.getUser,
    signIn: workosMocks.signIn,
    signOut: workosMocks.signOut,
    dispose: workosMocks.dispose,
  });
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
    render(
      <AuthProvider clientId="">
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
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", name: "U", exp: future() }));
    render(
      <AuthProvider clientId="test-client.apps.googleusercontent.com">
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));
    expect(screen.getByTestId("email").textContent).toBe("u@x.com");
    expect(document.querySelector('script[src*="gsi/client"]')).not.toBeNull();
  });

  it("client id via injected window.__SC_ENV__ (no prop) also enables", async () => {
    (window as any).__SC_ENV__ = { apiUrl: "", wsUrl: "", googleClientId: "runtime-client" };
    try {
      expect(authEnabled()).toBe(true);
      render(
        <AuthProvider>
          <Probe />
        </AuthProvider>
      );
      expect(screen.getByTestId("enabled").textContent).toBe("true");
    } finally {
      delete (window as any).__SC_ENV__;
    }
  });

  it("expired stored token → anonymous and cleared from storage", async () => {
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", exp: 1 }));
    render(
      <AuthProvider clientId="test-client">
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("a 401 (notifyAuthExpired) clears the token → anonymous", async () => {
    sessionStorage.setItem(STORAGE_KEY, makeJwt({ email: "u@x.com", exp: future() }));
    render(
      <AuthProvider clientId="test-client">
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

describe("WorkOS AuthKit path", () => {
  it("WorkOS client id → enabled: seeds token + user from the SDK, no GIS", async () => {
    render(
      <AuthProvider workosClientId="client_01HX" workosRedirectUri="https://app.example/">
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));
    // Display user comes from getUser(); the bearer is the WorkOS access token.
    expect(screen.getByTestId("email").textContent).toBe("w@x.io");
    expect(screen.getByTestId("token").textContent).toBe("workos-access-token");
    // The API layer sends the WorkOS bearer via the registered token getter.
    expect(authHeader()).toEqual({ Authorization: "Bearer workos-access-token" });
    // WorkOS path must NOT load the Google Identity Services script.
    expect(document.querySelector('script[src*="gsi/client"]')).toBeNull();
  });

  it("WorkOS takes precedence when both client ids are configured", async () => {
    render(
      <AuthProvider clientId="google-cid" workosClientId="client_01HX">
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("workos-access-token"));
    expect(document.querySelector('script[src*="gsi/client"]')).toBeNull();
  });

  it("passes the local-storage refresh toggle through to AuthKit", async () => {
    (window as any).__SC_ENV__ = {
      apiUrl: "https://api.example",
      wsUrl: "wss://api.example",
      googleClientId: "",
      workosClientId: "client_01HX",
      workosRedirectUri: "https://app.example/",
      workosUseLocalStorageRefresh: true,
    };

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));
    expect(workosMocks.createClient).toHaveBeenCalledWith(
      "client_01HX",
      expect.objectContaining({
        redirectUri: "https://app.example/",
        devMode: true,
      })
    );
  });

  it("clears stale WorkOS browser session hints when bootstrap refresh fails", async () => {
    sessionStorage.setItem("workos:code-verifier", "stale-code-verifier");
    sessionStorage.setItem("workos-org-id:client_01HX", "org_123");
    localStorage.setItem("workos:refresh-token:client_01HX", "stale-refresh");
    document.cookie = "workos-has-session=client_01HX; path=/";
    workosMocks.getAccessToken.mockRejectedValueOnce(new Error("No access token available"));

    render(
      <AuthProvider workosClientId="client_01HX" workosRedirectUri="https://app.example/">
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(screen.getByTestId("token").textContent).toBe("none");
    expect(sessionStorage.getItem("workos:code-verifier")).toBeNull();
    expect(sessionStorage.getItem("workos-org-id:client_01HX")).toBeNull();
    expect(localStorage.getItem("workos:refresh-token:client_01HX")).toBeNull();
    expect(document.cookie).not.toContain("workos-has-session");
    expect(workosMocks.signOut).toHaveBeenCalledWith({ navigate: false });
  });

  it("forces WorkOS refresh on 401 recovery and clears session hints if refresh fails", async () => {
    render(
      <AuthProvider workosClientId="client_01HX" workosRedirectUri="https://app.example/">
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("signed_in"));

    workosMocks.getAccessToken.mockRejectedValueOnce(new Error("refresh failed"));
    await act(async () => {
      notifyAuthExpired();
    });

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(workosMocks.getAccessToken).toHaveBeenLastCalledWith({ forceRefresh: true });
    expect(workosMocks.signOut).toHaveBeenCalledWith({ navigate: false });
  });
});

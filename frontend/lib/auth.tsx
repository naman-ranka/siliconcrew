"use client";

// Hosted sign-in. Two interchangeable providers, selected by which client id is
// configured at runtime; the backend already verifies the bearer token either
// way (api.py::get_identity → authenticate), so there's no server callback here.
//
//   * WorkOS AuthKit  (NEXT_PUBLIC_WORKOS / WORKOS_CLIENT_ID) — the unified path:
//     web + remote-MCP share one WorkOS identity / user_id, so a session started
//     in an AI client shows up on the website and vice-versa. "Sign in with
//     Google" is configured as the upstream connection, so the button is
//     unchanged. The SDK manages the redirect handshake, the access token, and
//     refresh; we hold the latest token and send it as `Authorization: Bearer`.
//   * Google Identity Services (GOOGLE_CLIENT_ID) — today's direct sign-in, kept
//     verbatim as the fallback so existing deployments are unaffected.
//
// CONFIG GATING (make-or-break): when neither client id is set, `enabled` is
// false — no auth UI, no SDK/script load, no token getter, no header. Self-host
// / contributor zero-config stays bit-for-bit identical to today. WorkOS takes
// precedence when both are set. Decoded JWT claims are DISPLAY ONLY; the backend
// is the sole authority for authorization.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  setAuthTokenGetter,
  setOnAuthExpired,
} from "./authToken";
import {
  getGoogleClientId,
  getWorkosClientId,
  getWorkosRedirectUri,
} from "./runtime-config";
import { useStore } from "./store";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const STORAGE_KEY = "sc-auth-token";

export type AuthUser = { email: string | null; name?: string; picture?: string };
export type AuthStatus = "loading" | "anonymous" | "signed_in";
type AuthMode = "workos" | "google" | "off";

export type AuthState = {
  enabled: boolean;
  status: AuthStatus;
  user: AuthUser | null;
  token: string | null;
  signIn: () => void;
  signOut: () => void;
};

// ---------------------------------------------------------------------------
// Pure helpers (exported for unit tests)
// ---------------------------------------------------------------------------

/** The configured Google OAuth client id (runtime; see lib/runtime-config). */
export function authClientId(): string {
  return getGoogleClientId().trim();
}

/** The configured WorkOS AuthKit client id (runtime). */
export function workosClientId(): string {
  return getWorkosClientId().trim();
}

/** OAuth is configured iff a WorkOS or Google client id is present. */
export function authEnabled(): boolean {
  return workosClientId().length > 0 || authClientId().length > 0;
}

/** Decode a JWT payload for DISPLAY ONLY (never for authz). Returns null on any
 *  malformed input — we never throw on a bad token. */
export function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    let b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    // Google ID tokens are unpadded base64url — restore padding for atob/Buffer.
    b64 += "=".repeat((4 - (b64.length % 4)) % 4);
    const json =
      typeof atob === "function"
        ? decodeURIComponent(
            atob(b64)
              .split("")
              .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
              .join("")
          )
        : Buffer.from(b64, "base64").toString("utf-8");
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/** True if the token's `exp` (seconds) is in the past (or missing). */
export function jwtExpired(token: string, nowMs: number = Date.now()): boolean {
  const payload = decodeJwt(token);
  const exp = payload && typeof payload.exp === "number" ? payload.exp : 0;
  return exp * 1000 <= nowMs;
}

/** Build the display user from a (valid) Google ID token. */
export function userFromToken(token: string): AuthUser | null {
  const p = decodeJwt(token);
  if (!p) return null;
  return {
    email: (p.email as string) ?? null,
    name: p.name as string | undefined,
    picture: p.picture as string | undefined,
  };
}

// ---------------------------------------------------------------------------
// GIS types (minimal)
// ---------------------------------------------------------------------------

type GisCredentialResponse = { credential: string };
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: {
            client_id: string;
            callback: (resp: GisCredentialResponse) => void;
            auto_select?: boolean;
          }) => void;
          prompt: () => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}

// ---------------------------------------------------------------------------
// WorkOS AuthKit types (minimal — the SDK is dynamically imported)
// ---------------------------------------------------------------------------

type WorkosUser = {
  email?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  profilePictureUrl?: string | null;
};

type WorkosClient = {
  getAccessToken: (opts?: { forceRefresh?: boolean }) => Promise<string>;
  getUser: () => WorkosUser | null;
  signIn: (opts?: unknown) => Promise<void>;
  signOut: (opts?: { returnTo?: string; navigate?: boolean }) => unknown;
  dispose?: () => void;
};

/** Build the display user from a WorkOS user object (email/name/picture). */
function userFromWorkos(u: WorkosUser | null): AuthUser | null {
  if (!u) return null;
  const name = [u.firstName, u.lastName].filter(Boolean).join(" ") || undefined;
  return { email: u.email ?? null, name, picture: u.profilePictureUrl ?? undefined };
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // Defensive: if a component reads auth outside the provider (shouldn't
    // happen — it wraps the app), behave as unconfigured rather than crash.
    return {
      enabled: false,
      status: "anonymous",
      user: null,
      token: null,
      signIn: () => {},
      signOut: () => {},
    };
  }
  return ctx;
}

export function AuthProvider({
  children,
  clientId,
  workosClientId: workosClientIdProp,
  workosRedirectUri: workosRedirectUriProp,
}: {
  children: React.ReactNode;
  clientId?: string;
  workosClientId?: string;
  workosRedirectUri?: string;
}) {
  // Prefer explicit props (passed by the server layout from the runtime env) so
  // SSR and the first client render agree; fall back to the runtime helpers.
  const resolvedGoogleClientId = (clientId ?? authClientId()).trim();
  const resolvedWorkosClientId = (workosClientIdProp ?? workosClientId()).trim();
  const resolvedRedirectUri =
    (workosRedirectUriProp ?? getWorkosRedirectUri() ?? "").trim() ||
    (typeof window !== "undefined" ? window.location.origin + "/" : "");

  // WorkOS wins when both are configured (the unified path).
  const mode: AuthMode = resolvedWorkosClientId
    ? "workos"
    : resolvedGoogleClientId
    ? "google"
    : "off";
  const enabled = mode !== "off";

  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>(enabled ? "loading" : "anonymous");
  const tokenRef = useRef<string | null>(null);
  const gisReady = useRef(false);
  const workosClient = useRef<WorkosClient | null>(null);
  const workosClientReady = useRef<Promise<WorkosClient | null> | null>(null);
  const workosRecovery = useRef<Promise<void> | null>(null);

  // Keep a ref in sync so the token getter seam always reads the latest value.
  const applyToken = useCallback((t: string | null, displayUser?: AuthUser | null) => {
    tokenRef.current = t;
    setToken(t);
    if (t) {
      setUser(displayUser !== undefined ? displayUser : userFromToken(t));
      setStatus("signed_in");
    } else {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  // --- Google (GIS) path ----------------------------------------------------

  const signOutGoogle = useCallback(() => {
    try { window.google?.accounts.id.disableAutoSelect(); } catch { /* ignore */ }
    applyToken(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, [applyToken]);

  const handleCredential = useCallback(
    (resp: GisCredentialResponse) => {
      const t = resp?.credential;
      if (t && !jwtExpired(t)) {
        applyToken(t);
        try { sessionStorage.setItem(STORAGE_KEY, t); } catch { /* ignore */ }
      }
    },
    [applyToken]
  );

  // Register the API-layer seam for the GIS path: token getter + 401 handler.
  useEffect(() => {
    if (mode !== "google") return;
    setAuthTokenGetter(() => tokenRef.current);
    setOnAuthExpired(() => {
      if (tokenRef.current) {
        applyToken(null);
        try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
        try {
          useStore.getState().pushToast({
            kind: "info",
            title: "Session expired — sign in again",
            detail: "Your Google session timed out. Sign in to keep synthesizing & saving.",
          });
        } catch { /* store not ready — silent drop to anonymous is still fine */ }
      }
    });
    return () => {
      setAuthTokenGetter(() => null);
      setOnAuthExpired(null);
    };
  }, [mode, applyToken]);

  // Restore a still-valid token from sessionStorage (survives refresh, dies with
  // the tab). GIS only — WorkOS manages its own session.
  useEffect(() => {
    if (mode !== "google") return;
    let restored: string | null = null;
    try { restored = sessionStorage.getItem(STORAGE_KEY); } catch { /* ignore */ }
    if (restored && !jwtExpired(restored)) applyToken(restored);
    else {
      if (restored) { try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ } }
      setStatus("anonymous");
    }
  }, [mode, applyToken]);

  // Load the GIS script + initialize (GIS only).
  useEffect(() => {
    if (mode !== "google" || typeof document === "undefined") return;
    const init = () => {
      if (gisReady.current || !window.google) return;
      gisReady.current = true;
      try {
        window.google.accounts.id.initialize({
          client_id: resolvedGoogleClientId,
          callback: handleCredential,
          auto_select: false,
        });
      } catch { /* ignore init errors — sign-in button simply won't prompt */ }
    };
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GIS_SRC}"]`);
    if (existing) {
      if (window.google) init();
      else existing.addEventListener("load", init, { once: true });
      return;
    }
    const s = document.createElement("script");
    s.src = GIS_SRC;
    s.async = true;
    s.defer = true;
    s.addEventListener("load", init, { once: true });
    document.head.appendChild(s);
  }, [mode, handleCredential, resolvedGoogleClientId]);

  // --- WorkOS AuthKit path --------------------------------------------------

  useEffect(() => {
    if (mode !== "workos" || typeof window === "undefined") return;
    let disposed = false;

    const toAnonymous = (toast: boolean) => {
      tokenRef.current = null;
      setToken(null);
      setUser(null);
      setStatus("anonymous");
      if (toast) {
        try {
          useStore.getState().pushToast({
            kind: "info",
            title: "Session expired — sign in again",
            detail: "Your session timed out. Sign in to keep synthesizing & saving.",
          });
        } catch { /* store not ready — silent drop is fine */ }
      }
    };
    const apply = (accessToken: string, u: WorkosUser | null) => {
      tokenRef.current = accessToken;
      setToken(accessToken);
      setUser(userFromWorkos(u));
      setStatus("signed_in");
    };

    workosClientReady.current = (async () => {
      try {
        const { createClient } = await import("@workos-inc/authkit-js");
        const client = (await createClient(resolvedWorkosClientId, {
          redirectUri: resolvedRedirectUri,
          // The SDK refreshes proactively; mirror the new token into our ref so
          // the (sync) token getter seam always returns a fresh bearer.
          onRefresh: ({ accessToken, user: u }: { accessToken: string; user: WorkosUser }) => {
            if (!disposed) apply(accessToken, u);
          },
          onRefreshFailure: () => {
            if (!disposed) toAnonymous(true);
          },
        })) as unknown as WorkosClient;
        if (disposed) { client.dispose?.(); return null; }
        workosClient.current = client;
        // Seed the current session if the user is already signed in.
        try {
          const accessToken = await client.getAccessToken();
          apply(accessToken, client.getUser());
        } catch {
          toAnonymous(false); // not signed in yet — anonymous, not an error
        }
        return client;
      } catch (err) {
        try {
          useStore.getState().pushToast({
            kind: "error",
            title: "WorkOS Init Failed",
            detail: String(err),
          });
        } catch { /* store not ready */ }
        // SDK failed to load/init — never crash the app; behave as anonymous.
        if (!disposed) toAnonymous(false);
        return null;
      }
    })();

    // API-layer seam: sync getter (reads the SDK-refreshed ref) + 401 handler
    // that forces a refresh before dropping to anonymous.
    setAuthTokenGetter(() => tokenRef.current);
    setOnAuthExpired(() => {
      const c = workosClient.current;
      if (!c) { toAnonymous(true); return; }
      if (!workosRecovery.current) {
        workosRecovery.current = c.getAccessToken()
          .then((t) => apply(t, c.getUser()))
          .catch(() => {
            toAnonymous(true);
          })
          .finally(() => {
            workosRecovery.current = null;
          });
      }
      return workosRecovery.current;
    });

    return () => {
      disposed = true;
      setAuthTokenGetter(() => null);
      setOnAuthExpired(null);
      try { workosClient.current?.dispose?.(); } catch { /* ignore */ }
      workosClient.current = null;
      workosClientReady.current = null;
      workosRecovery.current = null;
    };
  }, [mode, resolvedWorkosClientId, resolvedRedirectUri]);

  // --- dispatch -------------------------------------------------------------

  const signIn = useCallback(() => {
    if (mode === "workos") {
      void (async () => {
        try {
          let client = workosClient.current;
          if (!client && workosClientReady.current) {
            client = await workosClientReady.current;
          }
          if (!client) {
            const { createClient } = await import("@workos-inc/authkit-js");
            client = (await createClient(resolvedWorkosClientId, {
              redirectUri: resolvedRedirectUri,
            })) as unknown as WorkosClient;
            workosClient.current = client;
          }
          await client.signIn();
        } catch (err) {
          try {
            useStore.getState().pushToast({
              kind: "error",
              title: "Sign-in failed",
              detail: err instanceof Error ? err.message : String(err),
            });
          } catch { /* store not ready */ }
        }
      })();
      return;
    }
    if (mode === "google") {
      try { window.google?.accounts.id.prompt(); } catch { /* GIS not ready yet */ }
    }
  }, [mode, resolvedRedirectUri, resolvedWorkosClientId]);

  const signOut = useCallback(() => {
    if (mode === "workos") {
      tokenRef.current = null;
      setToken(null);
      setUser(null);
      setStatus("anonymous");
      // navigate:false → clear the WorkOS session without a full-page redirect.
      try { workosClient.current?.signOut({ navigate: false }); } catch { /* ignore */ }
      return;
    }
    signOutGoogle();
  }, [mode, signOutGoogle]);

  const value: AuthState = { enabled, status, user, token, signIn, signOut };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

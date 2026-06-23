"use client";

// Google sign-in for hosted mode, via Google Identity Services (GIS).
//
// Why GIS (not next-auth): the backend already verifies the Google ID token
// itself (api.py::get_identity → authenticate), so there is no need for a
// server-side callback/session. GIS hands us exactly an ID token from one
// script tag. We hold it client-side and attach it as `Authorization: Bearer`
// on every request (see lib/api.ts + lib/authToken.ts).
//
// CONFIG GATING (make-or-break): when NEXT_PUBLIC_GOOGLE_CLIENT_ID is unset,
// `enabled` is false — we render no auth UI, load no GIS script, register no
// token getter, and send no header. Self-host / contributor zero-config stays
// bit-for-bit identical to today. The decoded JWT is used for DISPLAY ONLY;
// the backend is the sole authority for authorization.

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
import { getGoogleClientId } from "./runtime-config";
import { useStore } from "./store";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const STORAGE_KEY = "sc-auth-token";

export type AuthUser = { email: string | null; name?: string; picture?: string };
export type AuthStatus = "loading" | "anonymous" | "signed_in";

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

/** The configured OAuth client id, injected at runtime via window.__SC_ENV__
 *  (see lib/runtime-config.ts). Public value; kept runtime so one image serves
 *  every environment. AuthProvider prefers an explicit prop (so the value is
 *  identical on the SSR and client renders, avoiding a hydration mismatch). */
export function authClientId(): string {
  return getGoogleClientId().trim();
}

/** OAuth is configured iff a client id is present. */
export function authEnabled(): boolean {
  return authClientId().length > 0;
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

/** Build the display user from a (valid) ID token. */
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
}: {
  children: React.ReactNode;
  clientId?: string;
}) {
  // Prefer the explicit prop (passed by the server layout from the runtime env)
  // so SSR and the first client render agree; fall back to the runtime helper.
  const resolvedClientId = (clientId ?? authClientId()).trim();
  const enabled = resolvedClientId.length > 0;
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>(enabled ? "loading" : "anonymous");
  const tokenRef = useRef<string | null>(null);
  const gisReady = useRef(false);

  // Keep a ref in sync so the token getter seam always reads the latest value.
  const applyToken = useCallback((t: string | null) => {
    tokenRef.current = t;
    setToken(t);
    if (t) {
      setUser(userFromToken(t));
      setStatus("signed_in");
      try { sessionStorage.setItem(STORAGE_KEY, t); } catch { /* ignore */ }
    } else {
      setUser(null);
      setStatus("anonymous");
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    }
  }, []);

  const signOut = useCallback(() => {
    try { window.google?.accounts.id.disableAutoSelect(); } catch { /* ignore */ }
    applyToken(null);
  }, [applyToken]);

  const handleCredential = useCallback(
    (resp: GisCredentialResponse) => {
      const t = resp?.credential;
      if (t && !jwtExpired(t)) applyToken(t);
    },
    [applyToken]
  );

  const signIn = useCallback(() => {
    if (!enabled) return;
    try {
      window.google?.accounts.id.prompt();
    } catch { /* GIS not ready yet — the button stays; user can retry */ }
  }, [enabled]);

  // Register the API-layer seam: token getter + 401 handler. Only when enabled,
  // so the unconfigured path never attaches a header or reacts to 401s.
  useEffect(() => {
    if (!enabled) return;
    setAuthTokenGetter(() => tokenRef.current);
    setOnAuthExpired(() => {
      // Expired/invalid token → drop to anonymous and prompt re-sign-in (a toast,
      // never a raw error). The sign-in button reappears via the account chip.
      if (tokenRef.current) {
        applyToken(null);
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
  }, [enabled, applyToken]);

  // Restore a still-valid token from sessionStorage (survives refresh, dies
  // with the tab).
  useEffect(() => {
    if (!enabled) return;
    let restored: string | null = null;
    try { restored = sessionStorage.getItem(STORAGE_KEY); } catch { /* ignore */ }
    if (restored && !jwtExpired(restored)) applyToken(restored);
    else {
      if (restored) { try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ } }
      setStatus("anonymous");
    }
  }, [enabled, applyToken]);

  // Load the GIS script + initialize (only when enabled).
  useEffect(() => {
    if (!enabled || typeof document === "undefined") return;
    const init = () => {
      if (gisReady.current || !window.google) return;
      gisReady.current = true;
      try {
        window.google.accounts.id.initialize({
          client_id: resolvedClientId,
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
  }, [enabled, handleCredential, resolvedClientId]);

  const value: AuthState = { enabled, status, user, token, signIn, signOut };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

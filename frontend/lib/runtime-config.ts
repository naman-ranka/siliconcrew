// Runtime (NOT build-time) backend configuration.
//
// Next.js inlines every `NEXT_PUBLIC_*` env var at *build* time, so a Docker
// image built without the backend URL bakes in a wrong fallback (the classic
// `localhost:8000` -> ECONNREFUSED on Cloud Run). To keep the image 100%
// environment-agnostic ("build once, run anywhere"), the server layout reads
// plain (non-public) env vars *per request* and injects them into
// `window.__SC_ENV__`; the browser reads that for both REST and WebSocket URLs.

export type RuntimeEnv = { apiUrl: string; wsUrl: string; googleClientId: string };

declare global {
  interface Window {
    __SC_ENV__?: RuntimeEnv;
  }
}

// Global name shared between the server injector and the client reader.
export const SC_ENV_GLOBAL = "__SC_ENV__";

// Local-dev defaults: a backend on :8000, same host, and no OAuth (self-host /
// zero-config). Production never relies on these — Terraform sets the env and
// the layout injects them.
const DEV_DEFAULT: RuntimeEnv = {
  apiUrl: "http://localhost:8000",
  wsUrl: "ws://localhost:8000",
  googleClientId: "",
};

// Derive the ws(s):// origin from an http(s):// origin when WS_URL is unset.
function deriveWsUrl(apiUrl: string): string {
  return apiUrl.replace(/^http/, "ws");
}

// Server-side: read runtime env (NOT NEXT_PUBLIC_, so it is read at request
// time, not inlined at build). Called by the root layout to inject __SC_ENV__.
// GOOGLE_CLIENT_ID is public but kept runtime so a single image serves every
// environment (self-host with no auth, hosted with auth) without rebuilding.
export function readServerEnv(): RuntimeEnv {
  const apiUrl = process.env.API_URL || DEV_DEFAULT.apiUrl;
  const wsUrl = process.env.WS_URL || deriveWsUrl(apiUrl);
  const googleClientId =
    process.env.GOOGLE_CLIENT_ID || process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
  return { apiUrl, wsUrl, googleClientId };
}

// Client-side: read the env injected by the layout. Falls back to the dev
// default (used by `next dev` without injection and by unit tests).
export function getRuntimeEnv(): RuntimeEnv {
  if (typeof window !== "undefined" && window.__SC_ENV__) {
    return window.__SC_ENV__;
  }
  return DEV_DEFAULT;
}

export const getApiBase = (): string => getRuntimeEnv().apiUrl;
export const getWsBase = (): string => getRuntimeEnv().wsUrl;
export const getGoogleClientId = (): string => getRuntimeEnv().googleClientId;

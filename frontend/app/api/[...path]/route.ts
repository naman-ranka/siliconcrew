import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy to the FastAPI backend for anything that hits the Next
 * origin under `/api/*` (health probes, curl/CI checks, self-host setups that
 * front both services with one hostname). The browser app itself talks to the
 * backend directly using the runtime-injected origin (lib/runtime-config.ts).
 */

// Never prerender or cache: the backend origin is read per request.
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function HEAD(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

// Methods with no body, and the only ones a transport failure may be replayed
// for: a `fetch` rejection means no response was ever received, but only reads
// are safe to send twice (POST /threads, /invoke, /simulate all mutate).
const BODYLESS_METHODS = ["GET", "HEAD", "OPTIONS"];

const RETRY_ATTEMPTS = 3; // 1 try + 2 retries, safe methods only
const RETRY_BACKOFF_MS = [150, 500];
// One request must never outlive the platform's own ceiling. Not configurable:
// a knob on a route with this little traffic is a setting nobody would tune.
const REQUEST_TIMEOUT_MS = 60_000;

// Hop-by-hop headers belong to one connection, never to the proxied one.
const HOP_BY_HOP = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

// On the REQUEST side only `content-length` goes: the body is re-buffered, so
// the incoming length no longer frames it. `content-encoding` must survive —
// undici decodes responses, not requests, so the bytes we forward are still
// encoded and stripping the header would hand the backend garbage.
const DROP_FROM_REQUEST = new Set([...HOP_BY_HOP, "host", "content-length"]);

// On the RESPONSE side `content-encoding`/`content-length` also go: undici has
// already decoded the body, so copying them makes it unreadable downstream.
const DROP_FROM_RESPONSE = new Set([...HOP_BY_HOP, "content-encoding", "content-length"]);

// Statuses whose response MUST have a null body — `new Response(blob, {status})`
// throws for these, and that TypeError would be caught below and misreported as
// an unreachable backend.
const NULL_BODY_STATUS = new Set([204, 205, 304]);

/**
 * Backend origin, read at REQUEST time. `API_URL` is the runtime variable the
 * deployment sets (see lib/runtime-config.ts + deploy/terraform/frontend.tf);
 * `NEXT_PUBLIC_API_URL` is inlined at BUILD time, so it is only a legacy
 * fallback — relying on it baked `http://localhost:8000` into every image and
 * made this route fail with a blanket 502 in the hosted deployment.
 */
function backendOrigin(): string {
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function handleProxy(request: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const searchParams = new URL(request.url).search;
  const targetUrl = `${backendOrigin()}/api/${path}${searchParams}`;

  // Forward incoming headers (except hop-by-hop ones, which belong to this
  // connection, not to the proxied one).
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!DROP_FROM_REQUEST.has(key.toLowerCase())) headers.set(key, value);
  });

  const bodyless = BODYLESS_METHODS.includes(request.method);
  // Buffer once, outside the retry loop — a stream body cannot be replayed.
  const body = bodyless ? undefined : await request.blob();

  const attempts = bodyless ? RETRY_ATTEMPTS : 1;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });

      // A received status is the backend's answer, never ours to retry.
      const responseBody = await response.blob();
      const responseHeaders = new Headers();
      response.headers.forEach((value, key) => {
        if (!DROP_FROM_RESPONSE.has(key.toLowerCase())) responseHeaders.set(key, value);
      });

      return new NextResponse(NULL_BODY_STATUS.has(response.status) ? null : responseBody, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (error: unknown) {
      lastError = error;
      // A timeout is not a transport failure: the backend may well be alive
      // and slow, so replaying would just hold the caller for another full
      // ceiling. Only a connection that never landed is retried.
      const timedOut = error instanceof Error && error.name === "TimeoutError";
      if (timedOut || attempt >= attempts - 1) break;
      await sleep(RETRY_BACKOFF_MS[Math.min(attempt, RETRY_BACKOFF_MS.length - 1)]);
    }
  }

  const message = lastError instanceof Error ? lastError.message : String(lastError);
  // The origin we dialled goes to the server log ONLY — echoing it would
  // publish the internal backend host to any anonymous caller of the public
  // frontend origin.
  console.error(
    `Next.js proxy error for ${request.method} /api/${path} → ${backendOrigin()}:`,
    lastError
  );
  return NextResponse.json(
    { detail: `Failed to proxy request to backend after ${attempts} attempt(s): ${message}` },
    { status: 502 }
  );
}

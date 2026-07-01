// Framework-agnostic auth seam.
//
// The non-React API layer (`lib/api.ts`) needs to read the current Google ID
// token and report auth failures, but it must NOT import the React auth context
// (that would couple a plain module to React and risk import cycles). So the
// `AuthProvider` *registers* its token getter + 401 handler here on mount, and
// `api.ts` reads through these module-level seams.
//
// When OAuth is unconfigured (self-host / zero-config), nothing registers a
// getter, so `getAuthToken()` returns null and no Authorization header is ever
// sent — behavior stays bit-for-bit identical to today.

let _getToken: () => string | null = () => null;
let _onAuthExpired: (() => void | Promise<void>) | null = null;

/** Registered by AuthProvider so the API layer can read the live token. */
export function setAuthTokenGetter(fn: () => string | null): void {
  _getToken = fn;
}

/** Current Google ID token, or null when signed-out / unconfigured. */
export function getAuthToken(): string | null {
  return _getToken();
}

/** Registered by AuthProvider; invoked by the API layer on a 401. */
export function setOnAuthExpired(fn: (() => void | Promise<void>) | null): void {
  _onAuthExpired = fn;
}

/** Called by the API layer when a request 401s (expired/invalid token). */
export function notifyAuthExpired(): void {
  void _onAuthExpired?.();
}

/** Async variant used by fetch wrappers that can retry after token recovery. */
export async function recoverAuthExpired(): Promise<void> {
  await _onAuthExpired?.();
}

/** Authorization header for the current token, or {} when none. Conditional so
 *  the unconfigured/self-host path sends no header at all. */
export function authHeader(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Signed-out intent stash (E2, onboarding wave).
//
// When a signed-out user commits to a mutating action (create a workspace,
// fork an example, create a group), we don't fire the doomed API call — we
// stash WHAT they wanted here and trigger sign-in. WorkOS sign-in is a
// full-page redirect that always returns to `/` (the fixed redirectUri), so
// sessionStorage is the right carrier: same-origin, survives the redirect,
// dies with the tab. Google/GIS mode signs in with NO navigation, so the
// replay must be driven by the auth status transition, never by page load.
//
// take() clears BEFORE returning: the replay runs at most once even if it
// throws, so a failed replay can never loop.

import type { ViewMode } from "@/lib/nav";

export type AuthIntent =
  | { kind: "create"; name: string; posture: ViewMode; group: string }
  /** Launcher pre-modal gate (ported from PR #38): sign in BEFORE the form,
   *  then reopen the create modal (optionally group-preset) on return. The
   *  workbench-mounted modal still uses the full-fidelity "create" intent. */
  | { kind: "openCreate"; group: string | null }
  | { kind: "fork"; templateId: string }
  | { kind: "createGroup"; name: string };

const KEY = "sc-auth-intent";

// An abandoned sign-in must not leave a landmine: without an expiry, a user
// who bails out of AuthKit and voluntarily signs in hours later would have
// the stale action silently replayed WITH navigation. Sign-in round trips
// take seconds; anything older than this is abandonment.
const MAX_AGE_MS = 15 * 60 * 1000;

export function stashAuthIntent(intent: AuthIntent): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ intent, at: Date.now() }));
  } catch {
    // Storage unavailable (private mode quota etc.) — the user just signs in
    // and repeats the action by hand; never block the sign-in itself.
  }
}

/**
 * Read-and-clear the stashed intent. With `kind`, only an intent of that kind
 * is taken — others are left in place for the replay host that owns them
 * (the create modal takes only "create"; the Launcher takes anything).
 */
export function takeAuthIntent(kind?: AuthIntent["kind"]): AuthIntent | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const envelope = JSON.parse(raw) as { intent?: AuthIntent; at?: number };
    const parsed = envelope?.intent;
    const valid =
      parsed &&
      (parsed.kind === "create" ||
        parsed.kind === "openCreate" ||
        parsed.kind === "fork" ||
        parsed.kind === "createGroup");
    if (!valid) {
      sessionStorage.removeItem(KEY);
      return null;
    }
    if (typeof envelope.at !== "number" || Date.now() - envelope.at > MAX_AGE_MS) {
      sessionStorage.removeItem(KEY); // expired — abandoned sign-in
      return null;
    }
    if (kind && parsed.kind !== kind) return null; // not ours; leave it
    sessionStorage.removeItem(KEY);
    return parsed;
  } catch {
    try { sessionStorage.removeItem(KEY); } catch { /* ignore */ }
    return null;
  }
}

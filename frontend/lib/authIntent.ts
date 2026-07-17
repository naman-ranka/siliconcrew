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
  | { kind: "fork"; templateId: string }
  | { kind: "createGroup"; name: string };

const KEY = "sc-auth-intent";

export function stashAuthIntent(intent: AuthIntent): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(intent));
  } catch {
    // Storage unavailable (private mode quota etc.) — the user just signs in
    // and repeats the action by hand; never block the sign-in itself.
  }
}

export function takeAuthIntent(): AuthIntent | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);
    const parsed = JSON.parse(raw) as AuthIntent;
    if (parsed && (parsed.kind === "create" || parsed.kind === "fork" || parsed.kind === "createGroup")) {
      return parsed;
    }
    return null;
  } catch {
    try { sessionStorage.removeItem(KEY); } catch { /* ignore */ }
    return null;
  }
}

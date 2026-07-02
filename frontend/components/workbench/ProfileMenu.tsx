"use client";

import { useEffect, useRef, useState } from "react";
import {
  ExternalLink,
  Github,
  KeyRound,
  LogOut,
  Plug,
  Settings,
  User,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export const REPO_URL = "https://github.com/naman-ranka/siliconcrew";

/** Initials for the avatar tile: "Jane Doe" → "JD", "jane@x.com" → "J". */
export function initialsFor(name?: string | null, email?: string | null): string {
  const src = (name || "").trim();
  if (src) {
    const parts = src.split(/\s+/).filter(Boolean);
    const first = parts[0]?.charAt(0) ?? "";
    const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : "";
    return (first + last).toUpperCase() || "?";
  }
  const e = (email || "").trim();
  return e ? e.charAt(0).toUpperCase() : "?";
}

/**
 * Avatar button + dropdown for the v2 top bar. Everything account-shaped lives
 * here: identity, MCP handoff, API keys, settings, repo, sign out. Auth-aware:
 * when OAuth isn't configured (self-host) the sign-in/out affordances vanish
 * but the utility items remain.
 */
export function ProfileMenu({ onConnectMcp }: { onConnectMcp: () => void }) {
  const { enabled, status, user, signIn, signOut } = useAuth();
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Standard popover affordances: Esc + click-outside close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const signedIn = enabled && status === "signed_in";
  const initials = signedIn ? initialsFor(user?.name, user?.email) : "?";

  const item =
    "flex h-8 w-full items-center gap-2 rounded px-2 text-left text-xs text-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-primary/60";

  const runItem = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        data-testid="profile-menu-button"
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-full bg-surface-3 text-[10px] font-medium text-foreground",
          "outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-primary/60",
          open && "ring-2 ring-primary/40"
        )}
      >
        {!enabled ? <User className="h-3.5 w-3.5" aria-hidden /> : initials}
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Account"
          data-testid="profile-menu"
          className="absolute right-0 z-50 mt-1 w-64 rounded-md border border-border bg-popover p-1 text-xs shadow-e2 animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 motion-reduce:animate-none"
        >
          {/* Header — identity (or the invitation to have one). */}
          {enabled && (
            <>
              <div className="flex items-center gap-2 px-2 py-2">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[10px] font-medium">
                  {initials}
                </div>
                {signedIn ? (
                  <div className="min-w-0">
                    <div className="truncate font-medium text-foreground">
                      {user?.name || user?.email || "Signed in"}
                    </div>
                    {user?.email && (
                      <div className="truncate text-[11px] text-muted-foreground">{user.email}</div>
                    )}
                  </div>
                ) : (
                  <div className="min-w-0 flex-1">
                    <div className="text-muted-foreground">Not signed in</div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={runItem(signIn)}
                      className="mt-1 inline-flex h-6 items-center rounded bg-primary px-2 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      Sign in with Google
                    </button>
                  </div>
                )}
              </div>
              <div className="my-1 h-px bg-border" />
            </>
          )}

          <button type="button" role="menuitem" className={item} onClick={runItem(onConnectMcp)}>
            <Plug className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <span className="flex-1">Connect via MCP</span>
            <span className="rounded-full border border-primary/40 bg-primary/10 px-1.5 py-px text-[10px] text-primary">
              handoff
            </span>
          </button>

          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={runItem(() => setSettingsOpen(true))}
          >
            <KeyRound className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            API keys
          </button>

          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={runItem(() => setSettingsOpen(true))}
          >
            <Settings className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            Settings
          </button>

          <a
            role="menuitem"
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className={item}
            onClick={() => setOpen(false)}
          >
            <Github className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <span className="flex-1">Open-source repo</span>
            <ExternalLink className="h-3 w-3 text-muted-foreground" aria-hidden />
          </a>

          {signedIn && (
            <>
              <div className="my-1 h-px bg-border" />
              <button type="button" role="menuitem" className={item} onClick={runItem(signOut)}>
                <LogOut className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                Sign out
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

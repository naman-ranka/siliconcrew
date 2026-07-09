"use client";

import { useEffect, useRef, useState } from "react";
import * as Avatar from "@radix-ui/react-avatar";
import { LogIn, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Sign-in button / account chip. Renders nothing when OAuth is unconfigured
 * (self-host / zero-config) — `enabled` is false, so the header looks exactly
 * like today. Signed-out: "Sign in with Google". Signed-in: avatar + email with
 * a small dropdown (manual popover, matching SessionPicker/ThreadSwitcher) that
 * offers Sign out.
 */
export function AccountChip() {
  const { enabled, status, user, signIn, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  // Unconfigured OR still resolving session storage → render nothing.
  if (!enabled || status === "loading") return null;

  if (status !== "signed_in") {
    return (
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 text-xs"
        onClick={() => signIn()}
        aria-label="Sign in with Google"
        data-testid="signin-button"
      >
        <LogIn className="h-3.5 w-3.5" />
        Sign in with Google
      </Button>
    );
  }

  const label = user?.name || user?.email || "Account";
  const initial = (user?.email || user?.name || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${user?.email ?? label}`}
        data-testid="account-chip"
        className={cn(
          "flex items-center gap-2 rounded-md pl-1 pr-2 py-1 text-xs outline-none",
          "hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-primary/60"
        )}
      >
        <Avatar.Root className="h-6 w-6 shrink-0 overflow-hidden rounded-full bg-primary/15">
          {user?.picture && (
            <Avatar.Image className="h-full w-full object-cover" src={user.picture} alt="" referrerPolicy="no-referrer" />
          )}
          <Avatar.Fallback className="flex h-full w-full items-center justify-center text-[10px] font-semibold text-primary">
            {initial}
          </Avatar.Fallback>
        </Avatar.Root>
        <span className="max-w-[140px] truncate text-foreground hidden sm:inline">{label}</span>
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-50 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow-e2 animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 motion-reduce:animate-none"
        >
          <div className="px-2 py-1.5">
            <div className="truncate text-xs font-medium text-foreground">{user?.name || "Signed in"}</div>
            {user?.email && <div className="truncate text-[11px] text-muted-foreground">{user.email}</div>}
          </div>
          <div className="my-1 h-px bg-border" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-foreground outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

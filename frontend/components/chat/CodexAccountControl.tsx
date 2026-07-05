"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { codexApi, type CodexAuthStatus } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Sparkles, ExternalLink, Copy, Check, Loader2 } from "lucide-react";

/**
 * Codex ChatGPT-account connect control (device-code login). Shown in the Codex
 * surface. Start → the server runs `codex login --device-auth`; we show the
 * verification URL + one-time code and poll until the login lands, then the
 * account is used for Codex turns (instead of an API key).
 */
export function CodexAccountControl() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<CodexAuthStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await codexApi.status());
    } catch {
      /* ignore transient */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while a login is in progress; stop once connected or closed.
  useEffect(() => {
    const active = open && status?.in_progress && !status?.connected;
    if (active && !pollRef.current) {
      pollRef.current = setInterval(refresh, 2000);
    }
    if (!active && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [open, status?.in_progress, status?.connected, refresh]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const start = async () => {
    setBusy(true);
    try {
      setStatus(await codexApi.startDeviceAuth());
    } catch (e) {
      alert("Could not start Codex login: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      setStatus(await codexApi.disconnect());
    } finally {
      setBusy(false);
    }
  };

  const copyCode = async () => {
    if (!status?.user_code) return;
    try {
      await navigator.clipboard.writeText(status.user_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  const connected = !!status?.connected;
  const inProgress = !!status?.in_progress && !connected;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-1.5 text-[11px] rounded-md border px-2 py-1 outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60",
          connected
            ? "border-emerald-500/40 text-emerald-500"
            : "border-border text-muted-foreground hover:text-foreground"
        )}
        aria-label="Codex ChatGPT account"
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-emerald-500" : inProgress ? "bg-amber-500" : "bg-muted-foreground")} />
        {connected ? "ChatGPT connected" : inProgress ? "Signing in…" : "Connect ChatGPT"}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1 w-80 rounded-md border border-border bg-popover shadow-e2 p-3 text-xs animate-in fade-in-0 zoom-in-95">
          <div className="flex items-center gap-2 font-medium text-foreground mb-2">
            <Sparkles className="h-3.5 w-3.5 text-violet-500" /> Codex — ChatGPT account
          </div>

          {connected ? (
            <div className="space-y-3">
              <p className="text-muted-foreground">
                Connected. Codex turns use your ChatGPT subscription (no API key needed).
              </p>
              <button
                type="button"
                onClick={disconnect}
                disabled={busy}
                className="w-full rounded border border-border px-2 py-1.5 hover:bg-surface-2 text-muted-foreground disabled:opacity-50"
              >
                {busy ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          ) : inProgress && status?.login_url ? (
            <div className="space-y-2.5">
              <p className="text-muted-foreground">1. Open the sign-in page:</p>
              <a
                href={status.login_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 text-violet-500 hover:underline break-all"
              >
                <ExternalLink className="h-3.5 w-3.5 shrink-0" /> {status.login_url}
              </a>
              <p className="text-muted-foreground">2. Enter this one-time code:</p>
              <button
                type="button"
                onClick={copyCode}
                className="flex items-center gap-2 w-full rounded border border-border px-2 py-1.5 hover:bg-surface-2 font-mono text-sm tracking-widest text-foreground"
                title="Copy code"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                {status.user_code || "…"}
              </button>
              <p className="flex items-center gap-1.5 text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Waiting for you to finish in the browser…
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-muted-foreground">
                Sign in with your ChatGPT account so Codex uses your subscription instead of an API key.
              </p>
              <button
                type="button"
                onClick={start}
                disabled={busy}
                className="w-full rounded bg-violet-500 text-white px-2 py-1.5 hover:bg-violet-600 disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Connect ChatGPT account
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

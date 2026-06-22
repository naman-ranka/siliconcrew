"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, Info, Loader2, X } from "lucide-react";
import type { Toast } from "@/types";

const ICON: Record<Toast["kind"], React.ReactNode> = {
  success: <CheckCircle2 className="h-4 w-4 text-status-pass" />,
  error: <XCircle className="h-4 w-4 text-status-fail" />,
  info: <Info className="h-4 w-4 text-info" />,
  running: <Loader2 className="h-4 w-4 text-status-running animate-spin" />,
};

const ACCENT: Record<Toast["kind"], string> = {
  success: "border-l-status-pass",
  error: "border-l-status-fail",
  info: "border-l-info",
  running: "border-l-status-running",
};

/** Unified, calm toast stack (bottom-right). Replaces ad-hoc banners; status is
 *  carried by the left accent + icon, never the orange brand. */
export function Toaster() {
  const { toasts, dismissToast } = useStore();
  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[340px] max-w-[calc(100vw-2rem)]"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          aria-atomic="true"
          className={cn(
            "group flex items-start gap-2.5 rounded-lg border border-l-2 border-border bg-popover text-popover-foreground",
            "px-3 py-2.5 shadow-e3 animate-fade-in-up",
            ACCENT[t.kind]
          )}
        >
          <span className="shrink-0 mt-0.5">{ICON[t.kind]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium leading-snug">{t.title}</p>
            {t.detail && (
              <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2 break-words font-mono">{t.detail}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => dismissToast(t.id)}
            aria-label="Dismiss notification"
            className="shrink-0 text-muted-foreground/60 hover:text-foreground transition-colors duration-fast rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

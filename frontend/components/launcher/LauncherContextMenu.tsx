"use client";

import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Check, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface MenuItem {
  /** Separator row — every other field is ignored. */
  sep?: boolean;
  label?: string;
  icon?: LucideIcon;
  onClick?: () => void;
  danger?: boolean;
  /** Muted right-aligned hint (e.g. "keeps sessions"). */
  hint?: string;
  /** Hover-opened submenu (e.g. Move to group ▸). */
  submenu?: MenuItem[];
  /** Submenu decorations: colored dot / active check. */
  dot?: string;
  check?: boolean;
}

export interface LauncherContextMenuProps {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
}

/** Fixed-position context menu with one level of hover submenus — the
 * launcher's session/group/background menus (per the prototype). */
export function LauncherContextMenu({ x, y, items, onClose }: LauncherContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [sub, setSub] = useState<number | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Keep the menu on-screen (SSR-safe: only rendered client-side post-event).
  const left = Math.min(x, (typeof window !== "undefined" ? window.innerWidth : 1280) - 210);
  const top = Math.min(
    y,
    (typeof window !== "undefined" ? window.innerHeight : 800) -
      Math.min(items.length * 34 + 16, 360)
  );

  return (
    <div
      className="fixed inset-0 z-[130]"
      onMouseDown={onClose}
      onContextMenu={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div
        ref={ref}
        role="menu"
        onMouseDown={(e) => e.stopPropagation()}
        style={{ left, top }}
        className="absolute min-w-[196px] rounded-lg border border-border bg-surface-1 shadow-lg p-1 text-[12.5px]"
      >
        {items.map((it, i) =>
          it.sep ? (
            <div key={i} className="my-1 h-px bg-border" />
          ) : (
            <div key={i} className="relative" onMouseEnter={() => setSub(it.submenu ? i : null)}>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  if (it.submenu) return;
                  it.onClick?.();
                  onClose();
                }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-2.5 h-8 rounded-md hover:bg-surface-2",
                  it.danger ? "text-status-fail" : "text-foreground/85"
                )}
              >
                {it.icon && <it.icon className="h-3.5 w-3.5 opacity-80 shrink-0" />}
                <span className="truncate">{it.label}</span>
                {it.submenu && <ChevronRight className="h-3.5 w-3.5 ml-auto opacity-60" />}
                {it.hint && <span className="ml-auto text-[10px] text-muted-foreground/70">{it.hint}</span>}
              </button>
              {it.submenu && sub === i && (
                <div className="absolute left-full top-0 -ml-1 pl-1.5 min-w-[176px] z-10">
                  <div className="rounded-lg border border-border bg-surface-1 shadow-lg p-1 max-h-[280px] overflow-y-auto">
                    {it.submenu.map((su, j) => (
                      <button
                        key={j}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          su.onClick?.();
                          onClose();
                        }}
                        className="w-full flex items-center gap-2.5 px-2.5 h-8 rounded-md hover:bg-surface-2 text-foreground/85"
                      >
                        {su.dot !== undefined && (
                          <span className="h-2 w-2 rounded-full shrink-0" style={{ background: su.dot }} />
                        )}
                        {su.icon && <su.icon className="h-3.5 w-3.5 opacity-80 shrink-0" />}
                        <span className="truncate">{su.label}</span>
                        {su.check && <Check className="h-3.5 w-3.5 ml-auto text-primary shrink-0" />}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
}

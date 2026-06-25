"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;

const Tooltip = TooltipPrimitive.Root;

const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      // Warm-tinted popover surface + e2 elevation, not the shadcn default.
      "z-50 max-w-[260px] overflow-hidden rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-e2",
      // Motion via tailwindcss-animate; reduced-motion users get an instant tip.
      "animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-1 data-[side=left]:slide-in-from-right-1 data-[side=right]:slide-in-from-left-1 data-[side=top]:slide-in-from-bottom-1 motion-reduce:animate-none",
      className
    )}
    {...props}
  />
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

/**
 * Convenience wrapper for the common case: a styled tooltip on a single icon
 * control. Renders its child as the trigger (`asChild`) so the control keeps its
 * own semantics/aria — Radix handles keyboard focus + dismissal. Keep an
 * `aria-label` on the child for tests + a11y (the tip is supplementary).
 */
function IconTooltip({
  label,
  children,
  side = "bottom",
  sideOffset,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  sideOffset?: number;
}) {
  // Self-contained provider so the component works anywhere — including in
  // isolated component tests — without depending on a provider ancestor. Radix
  // uses the nearest provider, so this safely no-ops the delay nesting under the
  // app-level provider in layout.tsx.
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side={side} sideOffset={sideOffset}>
          {label}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider, IconTooltip };

"use client";

import { cn } from "@/lib/utils";

/**
 * One reusable empty-state primitive for the workbench artifact viewers.
 *
 * Voice is unified across viewers: lead with the concrete in-app action, and
 * where the agent is also an option add the consistent secondary
 * "…or ask the assistant" line via `assistantHint`. Status/brand colors stay
 * out of here — empty states read calm and neutral.
 */
export interface EmptyStateProps {
  /** Icon node (already sized by caller, or defaults to h-7 w-7 via wrapper). */
  icon: React.ReactNode;
  /** Short headline, e.g. "No report yet". */
  headline: string;
  /** Supporting copy describing the concrete in-app action. */
  children?: React.ReactNode;
  /** Optional secondary "…or ask the assistant" style hint. */
  assistantHint?: React.ReactNode;
  /** Optional primary CTA / controls (button, run picker, etc). */
  cta?: React.ReactNode;
  /** Extra content rendered above the icon (e.g. a PPA hero). */
  header?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  headline,
  children,
  assistantHint,
  cta,
  header,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col h-full", className)}>
      {header}
      <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-muted-foreground">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-2 text-muted-foreground/80 [&>svg]:h-7 [&>svg]:w-7">
          {icon}
        </div>
        <p className="text-sm font-medium text-foreground">{headline}</p>
        {children && (
          <p className="mt-1.5 max-w-[280px] text-xs leading-relaxed text-muted-foreground">
            {children}
          </p>
        )}
        {cta && <div className="mt-5 flex flex-col items-center gap-2">{cta}</div>}
        {assistantHint && (
          <p className="mt-3 max-w-[280px] text-[11px] leading-relaxed text-muted-foreground/70">
            {assistantHint}
          </p>
        )}
      </div>
    </div>
  );
}

import { cn } from "@/lib/utils";

/**
 * Shared panel/section header for the workbench shell so heights, padding, type
 * treatment, and dividers stay consistent across the rails and center panels.
 *
 * - `h-9 px-3` + bottom border + `bg-surface-1` for a calm, consistent rhythm.
 * - `label` renders the uppercase 11px tracked section-header treatment.
 * - `children` (optional) are right-aligned controls.
 */
export function PanelHeader({
  label,
  icon,
  children,
  className,
}: {
  label: React.ReactNode;
  icon?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 h-9 px-3 border-b border-border bg-surface-1 shrink-0",
        className
      )}
    >
      {icon}
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children && <div className="flex items-center gap-1 ml-auto">{children}</div>}
    </div>
  );
}

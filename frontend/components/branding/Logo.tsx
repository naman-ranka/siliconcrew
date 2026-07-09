import { cn } from "@/lib/utils";

/**
 * SiliconCrew mark — a stroked silicon die: rounded package, a central core,
 * and pins on all four sides. Consistent with the lucide `CircuitBoard` vibe
 * the app already used, but a real, ownable glyph. Themeable: everything is
 * `currentColor`, so it inherits `text-primary` in the brand lockup and adapts
 * to the light/dark themes for free.
 */
// TODO(owner): tweak the motif if you'd prefer a wafer/crew emblem over a die.
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("h-4 w-4", className)}
    >
      {/* package */}
      <rect x="4" y="4" width="16" height="16" rx="3" />
      {/* core */}
      <rect x="9" y="9" width="6" height="6" rx="1.5" />
      {/* pins — two per side, aligned to the core edges as traces */}
      <path d="M9 4V2M15 4V2M9 20v2M15 20v2M4 9H2M4 15H2M20 9h2M20 15h2" />
      {/* core node */}
      <circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

import { cn } from "@/lib/utils";

/**
 * Lightweight shimmer placeholder. Uses the shared `animate-shimmer` surface
 * gradient (globals.css) so loading sections feel "alive" instead of flashing
 * empty/"No …" text before content lands. Respects prefers-reduced-motion (the
 * shimmer keyframes are neutralized globally in that mode).
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-shimmer rounded-md", className)}
      {...props}
    />
  );
}

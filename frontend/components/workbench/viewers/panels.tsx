"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Shared honest-state panels for the v2 artifact-tab wrappers. Per-viewer
// skeletons show ONLY on first load; stale data stays rendered during a
// revalidate (the wrappers never route a populated slice back here).

export function ViewerSkeleton() {
  return (
    <div className="flex flex-col h-full p-4 gap-3" aria-hidden="true">
      <Skeleton className="h-8 w-[240px]" />
      <div className="flex-1 space-y-2 pt-2">
        {Array.from({ length: 10 }).map((_, i) => (
          <Skeleton key={i} className="h-3" style={{ width: `${38 + ((i * 17) % 55)}%` }} />
        ))}
      </div>
    </div>
  );
}

export function ViewerError({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail?: string | null;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      {detail && <p className="text-xs mt-1 text-muted-foreground max-w-[360px] break-words">{detail}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function ViewerEmpty({
  icon,
  title,
  detail,
}: {
  icon: React.ReactNode;
  title: string;
  detail?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <div className="h-10 w-10 rounded-lg bg-surface-2 flex items-center justify-center mb-3 text-muted-foreground [&>svg]:h-5 [&>svg]:w-5">
        {icon}
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {detail && <p className="text-xs mt-1 text-muted-foreground max-w-[360px]">{detail}</p>}
    </div>
  );
}

export function ViewerSpinner({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mb-3" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {detail && <p className="text-xs mt-1 text-muted-foreground max-w-[360px]">{detail}</p>}
    </div>
  );
}

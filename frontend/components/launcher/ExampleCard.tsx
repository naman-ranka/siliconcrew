"use client";

import { FileCode2, GitFork, Layers, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { plural } from "./util";
import type { TemplateSummary } from "@/types";

export interface ExampleCardProps {
  template: TemplateSummary;
  selected: boolean;
  onSelect: () => void;
  /** Double-click / primary open → preview. */
  onOpen: () => void;
}

/**
 * Gallery card for a template BUNDLE (Wave 11). Reuses the SessionCard visual
 * language (glyph · name · meta row) but leads with the example's highlight
 * bullets and a fork affordance. NO status-dot verdicts (revision 1): the
 * outcome lives in the highlight strings, not an ambiguous dot.
 */
export function ExampleCard({ template, selected, onSelect, onOpen }: ExampleCardProps) {
  const { name, description, highlights, file_count, run_count } = template;

  return (
    <div
      data-testid={`example-card-${template.id}`}
      onClick={onSelect}
      onDoubleClick={onOpen}
      className={cn(
        "group relative rounded-lg border p-3.5 cursor-pointer transition-all select-none",
        selected
          ? "border-primary/50 bg-surface-1 shadow-sm"
          : "border-border bg-surface-1/50 hover:bg-surface-1 hover:border-border/80"
      )}
    >
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            "w-7 h-7 rounded-md grid place-items-center shrink-0 border",
            selected
              ? "bg-primary/15 text-primary border-primary/25"
              : "bg-surface-2 text-muted-foreground border-border"
          )}
        >
          <Sparkles className="h-4 w-4" />
        </div>
        <span className="text-[13px] font-semibold text-foreground truncate">{name}</span>
        <button
          type="button"
          aria-label={`Fork ${name}`}
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
          className="ml-auto -mr-1 inline-flex items-center gap-1 h-6 px-2 rounded-md text-[11px] text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-surface-2 hover:text-foreground shrink-0"
        >
          <GitFork className="h-3.5 w-3.5" /> Fork
        </button>
      </div>

      {description && (
        <p className="mt-2 text-[12px] leading-snug text-muted-foreground line-clamp-2">
          {description}
        </p>
      )}

      {highlights.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {highlights.slice(0, 3).map((h, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11px] text-foreground/75">
              <span className="mt-1 h-1 w-1 rounded-full bg-primary/60 shrink-0" />
              <span className="min-w-0">{h}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-2.5 flex items-center gap-3 text-[11px] text-muted-foreground/80">
        <span className="inline-flex items-center gap-1" title={plural(file_count, "file")}>
          <FileCode2 className="h-3 w-3" />
          {plural(file_count, "file")}
        </span>
        <span className="inline-flex items-center gap-1" title={plural(run_count, "run")}>
          <Layers className="h-3 w-3" />
          {plural(run_count, "run")}
        </span>
      </div>
    </div>
  );
}

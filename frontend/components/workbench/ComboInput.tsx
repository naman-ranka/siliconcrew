"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// The "search ≻ suggest ≻ type anything" input (editor kind "combo"): a text
// input that opens a filtered suggestion dropdown. Free entry is ALWAYS
// allowed — suggestions come from the live workspace (manifest testbenches,
// file indexes…) which can be incomplete, so the value is never restricted
// to the list. Shared by CommandModal and CommandSurface param editors.
//
// Keyboard: ↑/↓ navigate suggestions, Enter selects the highlighted one (or
// accepts the typed text and closes), Esc closes the dropdown (consumed — it
// must not bubble up and close the surrounding modal).

/** A suggestion row: plain value, or value + a display-only subtitle (a
 *  module's defining file, a file's manifest role). The row's accessible
 *  name stays the VALUE alone, so name-based queries survive the subtitle. */
export type ComboSuggestion = string | { value: string; subtitle?: string };

const suggestionValue = (s: ComboSuggestion): string =>
  typeof s === "string" ? s : s.value;
const suggestionSubtitle = (s: ComboSuggestion): string | undefined =>
  typeof s === "string" ? undefined : s.subtitle;

export interface ComboInputProps {
  value: string;
  onChange: (v: string) => void;
  /** Suggestion pool; filtered by the current value (case-insensitive substring). */
  suggestions: ComboSuggestion[];
  placeholder?: string;
  ariaLabel?: string;
  /** Wrapper classes (width etc.); the input itself keeps the shared style. */
  className?: string;
  /** Fired when the user COMMITS a value: picks a suggestion, or presses
   *  Enter on typed text. Multi-value wrappers (MultiComboInput) use this to
   *  turn the committed value into a chip; single-value callers ignore it. */
  onCommit?: (v: string) => void;
}

export function ComboInput({
  value,
  onChange,
  suggestions,
  placeholder,
  ariaLabel,
  className,
  onCommit,
}: ComboInputProps) {
  const [open, setOpen] = React.useState(false);
  const [highlight, setHighlight] = React.useState(-1);
  const listId = React.useId();

  const q = value.trim().toLowerCase();
  const filtered = q
    ? suggestions.filter((s) => suggestionValue(s).toLowerCase().includes(q))
    : suggestions;

  const select = (v: string) => {
    onChange(v);
    setOpen(false);
    setHighlight(-1);
    onCommit?.(v);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (filtered.length === 0) return;
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setHighlight(e.key === "ArrowDown" ? 0 : filtered.length - 1);
        return;
      }
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setHighlight((h) => (h + delta + filtered.length) % filtered.length);
      return;
    }
    if (e.key === "Enter") {
      if (open && highlight >= 0 && highlight < filtered.length) {
        e.preventDefault();
        select(suggestionValue(filtered[highlight]));
      } else {
        // Accept the typed text as-is: close the dropdown; multi-value
        // wrappers additionally commit it as a chip. Consume the key so a
        // surrounding form never submits on it.
        e.preventDefault();
        setOpen(false);
        setHighlight(-1);
        onCommit?.(value);
      }
      return;
    }
    if (e.key === "Escape") {
      if (open) {
        // Consume: Esc closes the dropdown, not the surrounding modal.
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        setHighlight(-1);
      }
    }
  };

  return (
    <div className={cn("relative", className)}>
      <input
        type="text"
        role="combobox"
        aria-expanded={open && filtered.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlight(-1);
        }}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={() => {
          // Suggestion rows preventDefault on mousedown, so a row click never
          // blurs the input first — closing here is safe.
          setOpen(false);
          setHighlight(-1);
        }}
        onKeyDown={onKeyDown}
        className={cn(
          "h-8 w-full rounded-md border border-border bg-surface-1 px-2 font-mono text-xs text-foreground",
          "outline-none placeholder:text-muted-foreground",
          "focus-visible:ring-2 focus-visible:ring-primary/60"
        )}
      />
      {open && filtered.length > 0 && (
        <div
          id={listId}
          role="listbox"
          aria-label={ariaLabel ? `${ariaLabel} suggestions` : "Suggestions"}
          // Keep focus in the input so blur doesn't fire before the click.
          onMouseDown={(e) => e.preventDefault()}
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-md border border-border bg-popover py-1 shadow-e2"
        >
          {filtered.map((s, i) => {
            const v = suggestionValue(s);
            const sub = suggestionSubtitle(s);
            return (
              <button
                key={v}
                type="button"
                role="option"
                aria-selected={i === highlight}
                // Accessible name = the VALUE alone — the subtitle is visual
                // decoration; name-based queries/tests keep working.
                aria-label={v}
                onClick={() => select(v)}
                onMouseEnter={() => setHighlight(i)}
                className={cn(
                  "flex h-7 w-full items-center px-2 text-left font-mono text-xs text-popover-foreground",
                  i === highlight ? "bg-accent text-accent-foreground" : "hover:bg-accent"
                )}
              >
                <span className="truncate">{v}</span>
                {sub && (
                  <span className="ml-auto min-w-0 shrink truncate pl-2 text-[10px] text-muted-foreground">
                    {sub}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---- multi-value variant ------------------------------------------------------

export interface MultiComboInputProps {
  values: string[];
  onChange: (v: string[]) => void;
  /** Suggestion pool; already-chosen values are hidden from the dropdown. */
  suggestions: ComboSuggestion[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}

/**
 * The multi-combo: chips + a ComboInput to add entries. Picking a suggestion
 * or pressing Enter on typed text adds a chip; free entry is always allowed
 * (same honesty rule as the single combo — the suggestion pool can miss
 * files). Replaces both the zero-suggestion freeform chips and the closed
 * toggle-chip list with ONE selector (command-surface-simplification W2).
 */
export function MultiComboInput({
  values,
  onChange,
  suggestions,
  placeholder,
  ariaLabel,
  className,
}: MultiComboInputProps) {
  const [draft, setDraft] = React.useState("");

  const add = (raw: string) => {
    const v = raw.trim();
    if (!v) return;
    if (!values.includes(v)) onChange([...values, v]);
    setDraft("");
  };

  return (
    <div className={cn("flex max-w-[300px] flex-col items-end gap-1", className)}>
      <ComboInput
        value={draft}
        onChange={setDraft}
        onCommit={add}
        suggestions={suggestions.filter((s) => !values.includes(suggestionValue(s)))}
        placeholder={placeholder ?? "type or pick + Enter"}
        ariaLabel={ariaLabel}
        className="w-52"
      />
      {values.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/15 px-1.5 py-0.5 font-mono text-[10px] text-primary"
            >
              {v}
              <button
                type="button"
                aria-label={`Remove ${v}`}
                onClick={() => onChange(values.filter((o) => o !== v))}
                className="text-primary/70 transition-colors hover:text-primary"
              >
                <X className="h-2.5 w-2.5" aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default ComboInput;

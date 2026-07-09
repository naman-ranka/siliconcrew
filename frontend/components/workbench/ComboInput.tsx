"use client";

import * as React from "react";
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

export interface ComboInputProps {
  value: string;
  onChange: (v: string) => void;
  /** Suggestion pool; filtered by the current value (case-insensitive substring). */
  suggestions: string[];
  placeholder?: string;
  ariaLabel?: string;
  /** Wrapper classes (width etc.); the input itself keeps the shared style. */
  className?: string;
}

export function ComboInput({
  value,
  onChange,
  suggestions,
  placeholder,
  ariaLabel,
  className,
}: ComboInputProps) {
  const [open, setOpen] = React.useState(false);
  const [highlight, setHighlight] = React.useState(-1);
  const listId = React.useId();

  const q = value.trim().toLowerCase();
  const filtered = q
    ? suggestions.filter((s) => s.toLowerCase().includes(q))
    : suggestions;

  const select = (v: string) => {
    onChange(v);
    setOpen(false);
    setHighlight(-1);
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
        select(filtered[highlight]);
      } else {
        // Accept the typed text as-is: just close the dropdown.
        setOpen(false);
        setHighlight(-1);
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
          {filtered.map((opt, i) => (
            <button
              key={opt}
              type="button"
              role="option"
              aria-selected={i === highlight}
              onClick={() => select(opt)}
              onMouseEnter={() => setHighlight(i)}
              className={cn(
                "flex h-7 w-full items-center px-2 text-left font-mono text-xs text-popover-foreground",
                i === highlight ? "bg-accent text-accent-foreground" : "hover:bg-accent"
              )}
            >
              <span className="truncate">{opt}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default ComboInput;

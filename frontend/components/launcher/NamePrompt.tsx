"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

export interface NamePromptProps {
  title: string;
  initial?: string;
  placeholder?: string;
  cta?: string;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}

/** Small centered prompt for rename / new-group — lighter than a full Dialog,
 * matching the prototype's NamePrompt (mono input, Enter confirms, Esc cancels). */
export function NamePrompt({
  title,
  initial = "",
  placeholder,
  cta = "Save",
  onCancel,
  onConfirm,
}: NamePromptProps) {
  const [value, setValue] = useState(initial);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 30);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const confirm = () => {
    const v = value.trim();
    if (v) onConfirm(v);
  };

  return (
    <div
      className="fixed inset-0 z-[135] grid place-items-center p-6 bg-black/55"
      onMouseDown={onCancel}
      role="dialog"
      aria-label={title}
    >
      <div
        className="w-full max-w-[380px] rounded-lg border border-border bg-surface-1 shadow-lg p-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="text-sm font-semibold mb-2.5">{title}</div>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && confirm()}
          placeholder={placeholder}
          className="w-full h-9 px-3 rounded-md border border-border bg-surface-2 text-sm outline-none focus:border-primary/50 font-mono"
        />
        <div className="flex justify-end gap-2 mt-3.5">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" disabled={!value.trim()} onClick={confirm}>
            {cta}
          </Button>
        </div>
      </div>
    </div>
  );
}

"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, Cpu } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  COMMANDS,
  defaultValues,
  manifestFacts,
  runCommand,
  synthRunChoices,
  type CommandDef,
  type CommandId,
  type CommandParam,
  type CommandValues,
} from "@/lib/commands";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { cn } from "@/lib/utils";
import { COMMAND_ICONS } from "@/components/workbench/CommandPalette";

// Parameter dialog for a palette command. The v2 principle rendered: files and
// tops are SUPPLIED BY THE MANIFEST (read-only info box) — the user only edits
// choices (platform, clock, mode, stages…).

const SOURCE_STYLES: Record<CommandParam["source"], string> = {
  manifest: "border-info/30 bg-info/10 text-info",
  choice: "border-warning/30 bg-warning/10 text-warning",
  run: "border-success/30 bg-success/10 text-success",
  default: "border-border bg-surface-2 text-muted-foreground",
};

function SrcTag({ source }: { source: CommandParam["source"] }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1 py-px font-mono text-[9px] leading-3",
        SOURCE_STYLES[source]
      )}
    >
      {source}
    </span>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border transition-colors",
        checked ? "bg-primary" : "bg-surface-2"
      )}
    >
      <span
        className={cn(
          "block h-3.5 w-3.5 rounded-full bg-background shadow transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-[2px]"
        )}
      />
    </button>
  );
}

function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" aria-hidden />
        ) : (
          <ChevronRight className="h-3 w-3" aria-hidden />
        )}
        <span>{title}</span>
      </button>
      {open && <div className="mt-1.5 space-y-3 pl-4">{children}</div>}
    </div>
  );
}

function ParamEditor({
  param,
  options,
  value,
  onChange,
}: {
  param: CommandParam;
  options: readonly string[];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  switch (param.type) {
    case "enum": {
      // Long values (run ids) or >4 options → dropdown; short small sets →
      // segmented buttons.
      const segmented =
        options.length > 0 && options.length <= 4 && options.every((o) => o.length <= 12);
      if (segmented) {
        return (
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {options.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => onChange(opt)}
                className={cn(
                  "border-r border-border px-2.5 py-1 font-mono text-[11px] transition-colors last:border-r-0",
                  value === opt
                    ? "bg-primary/15 text-primary"
                    : "bg-transparent text-muted-foreground hover:bg-surface-2 hover:text-foreground"
                )}
              >
                {opt}
              </button>
            ))}
          </div>
        );
      }
      return (
        <Select value={String(value ?? "")} onValueChange={(v) => onChange(v)}>
          <SelectTrigger className="h-7 w-full font-mono text-[11px]">
            <SelectValue placeholder="Select…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((opt) => (
              <SelectItem key={opt} value={opt} className="font-mono text-[11px]">
                {opt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    case "boolean":
      return (
        <Toggle
          checked={Boolean(value)}
          onChange={(v) => onChange(v)}
          label={param.label}
        />
      );
    case "number":
      return (
        <div className="relative w-36">
          <Input
            type="number"
            value={value === "" || value == null ? "" : String(value)}
            step={param.step}
            min={param.min}
            onChange={(e) => {
              const raw = e.target.value;
              onChange(raw === "" ? "" : Number(raw));
            }}
            className={cn("h-7 font-mono text-[11px]", param.unit && "pr-9")}
          />
          {param.unit && (
            <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center font-mono text-[10px] text-muted-foreground">
              {param.unit}
            </span>
          )}
        </div>
      );
    case "text":
      return (
        <Input
          type="text"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 font-mono text-[11px]"
        />
      );
  }
}

function ParamRow({
  param,
  options,
  value,
  onChange,
}: {
  param: CommandParam;
  options: readonly string[];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const noRuns = param.source === "run" && options.length === 0;
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-xs text-foreground">{param.label}</span>
        <SrcTag source={param.source} />
      </div>
      {noRuns ? (
        <span className="text-[11px] italic text-muted-foreground">No synth runs yet</span>
      ) : (
        <ParamEditor param={param} options={options} value={value} onChange={onChange} />
      )}
    </div>
  );
}

function CommandForm({ id, def }: { id: CommandId; def: CommandDef }) {
  const manifest = useStore((s) => s.manifest);
  const runs = useStore((s) => s.runs);
  const currentSession = useStore((s) => s.currentSession);
  const setCommandModal = useWorkbenchUiStore((s) => s.setCommandModal);

  const [values, setValues] = React.useState<CommandValues>(() =>
    defaultValues(id, { manifest, runs })
  );
  const setValue = (key: string, v: unknown) => setValues((prev) => ({ ...prev, [key]: v }));

  const Icon = COMMAND_ICONS[id];
  const facts = manifestFacts(id, { manifest });
  const basic = def.params.filter((p) => !p.advanced);
  const advanced = def.params.filter((p) => p.advanced);

  // The pnr runId param ships with empty options — populated here from live runs.
  const optionsFor = (p: CommandParam): readonly string[] =>
    p.key === "runId" && p.source === "run" ? synthRunChoices(runs) : p.options ?? [];

  const missingRun =
    def.params.some((p) => p.source === "run") &&
    def.params.filter((p) => p.source === "run").some((p) => optionsFor(p).length === 0);
  const canSubmit = Boolean(currentSession) && !missingRun;

  const submit = React.useCallback(() => {
    if (!canSubmit) return;
    setCommandModal(null);
    void runCommand(id, values);
  }, [canSubmit, id, values, setCommandModal]);

  // ⌘/Ctrl+Enter submits while the modal is open (Esc close = dialog default).
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        submit();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [submit]);

  const sessionLabel = currentSession
    ? currentSession.id.length > 20
      ? `${currentSession.id.slice(0, 20)}…`
      : currentSession.id
    : "no session";

  return (
    <>
      <DialogHeader className="space-y-1">
        <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-primary" aria-hidden />
          {def.label}
        </DialogTitle>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted-foreground">{def.tool}</span>
          {def.async && (
            <span className="inline-flex items-center gap-1 rounded border border-info/30 bg-info/10 px-1.5 py-px text-[10px] text-info">
              <Cpu className="h-3 w-3" aria-hidden />
              async job
            </span>
          )}
        </div>
        <DialogDescription className="text-xs text-muted-foreground">
          {def.description}
        </DialogDescription>
      </DialogHeader>

      {facts.length > 0 && (
        <div className="rounded border border-info/30 bg-info/10 p-2">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-info">
            Supplied by manifest
          </div>
          <div className="space-y-0.5">
            {facts.map((f) => (
              <div key={f.label} className="flex gap-2 text-[11px]">
                <span className="shrink-0 text-muted-foreground">{f.label}:</span>
                <span className="min-w-0 break-words font-mono text-foreground">{f.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {basic.length > 0 && (
        <div className="space-y-3">
          {basic.map((p) => (
            <ParamRow
              key={p.key}
              param={p}
              options={optionsFor(p)}
              value={values[p.key]}
              onChange={(v) => setValue(p.key, v)}
            />
          ))}
        </div>
      )}

      {advanced.length > 0 && (
        <Collapsible title={`Advanced (${advanced.length})`}>
          {advanced.map((p) => (
            <ParamRow
              key={p.key}
              param={p}
              options={optionsFor(p)}
              value={values[p.key]}
              onChange={(v) => setValue(p.key, v)}
            />
          ))}
        </Collapsible>
      )}

      <Collapsible title="Inspect request">
        <pre className="overflow-x-auto rounded bg-surface-2 p-2 font-mono text-[11px] text-foreground">
          {JSON.stringify({ tool: def.tool, arguments: values }, null, 2)}
        </pre>
      </Collapsible>

      <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
        <span className="min-w-0 truncate text-[10px] text-muted-foreground">
          files &amp; tops from manifest · {sessionLabel}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-3 text-xs"
            onClick={() => setCommandModal(null)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-7 gap-1.5 px-3 text-xs"
            disabled={!canSubmit}
            onClick={submit}
          >
            {def.async && <Cpu className="h-3 w-3" aria-hidden />}
            {def.async ? "Dispatch" : "Run"}
            <kbd className="rounded border border-primary-foreground/30 bg-primary-foreground/10 px-1 font-mono text-[9px] leading-4">
              ⌘↵
            </kbd>
          </Button>
        </div>
      </div>
    </>
  );
}

export function CommandModal() {
  const commandModal = useWorkbenchUiStore((s) => s.commandModal);
  const setCommandModal = useWorkbenchUiStore((s) => s.setCommandModal);

  // Only render for valid command ids — anything else is treated as closed.
  const id =
    commandModal && commandModal in COMMANDS ? (commandModal as CommandId) : null;
  if (!id) return null;
  const def = COMMANDS[id];

  return (
    <Dialog open onOpenChange={(open) => !open && setCommandModal(null)}>
      <DialogContent className="w-[560px] max-w-[92vw] gap-3 p-4 sm:max-w-[560px]">
        {/* Keyed by id so values re-initialize when the command changes. */}
        <CommandForm key={id} id={id} def={def} />
      </DialogContent>
    </Dialog>
  );
}

export default CommandModal;

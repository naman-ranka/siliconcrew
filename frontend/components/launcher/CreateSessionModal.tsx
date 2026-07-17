"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  Columns2,
  Folder,
  Layers,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { stashAuthIntent } from "@/lib/authIntent";
import { sessionUrl, type ViewMode } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { slugify } from "./util";
import { performCreate } from "./createSessionAction";

export interface CreateSessionModalProps {
  /** Pre-filled group NAME (opened from a group's "+ Add"). */
  presetGroup?: string | null;
  /** Pre-selected "Start in" shell — the agent shell's nav rail passes
   * "agent" so creating from there doesn't bounce the user into the IDE
   * (Wave 8); the Launcher keeps the IDE default. */
  defaultStartIn?: ViewMode;
  onClose: () => void;
}

/**
 * New-workspace modal: name with a live `workspace/<slug>/` preview, a
 * "Start in" Chat|IDE choice (persisted as the session's shell), and an
 * optional group (a tag — created on the fly if the name is new). No model
 * picker: the model is a per-chat choice; creation uses the catalog default.
 */
export function CreateSessionModal({ presetGroup, defaultStartIn, onClose }: CreateSessionModalProps) {
  const router = useRouter();
  const { projects, loadProjects, loadModels } = useStore();
  const { enabled: authEnabled, status: authStatus, signIn } = useAuth();

  const [name, setName] = useState("");
  // S4 resolved: both shells are real; IDE stays the default pre-selection
  // (the stored per-session shell preference takes over after first open).
  const [startIn, setStartIn] = useState<ViewMode>(defaultStartIn ?? "ide");
  const [showGroup, setShowGroup] = useState(!!presetGroup);
  const [group, setGroup] = useState(presetGroup ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Latest `onClose` for the Escape handler below — kept out of that effect's
  // deps (and out of the mount-only effect entirely) so a parent re-render
  // that hands us a brand-new `onClose` closure never re-fires either effect.
  // See WaveformViewer's `xToTicksRef` for the same "update ref during
  // render" pattern used elsewhere in this codebase.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Mount-only: fetch the data the form needs and focus the name input.
  // `loadProjects`/`loadModels` are stable Zustand action references (bound
  // once in the store's `create()` initializer), so this really only runs
  // once per modal open — it must NOT depend on `onClose`, which is a fresh
  // closure on every parent render and previously caused this effect (and
  // the loadProjects() call inside it) to re-fire in a tight loop every time
  // the parent re-rendered after the projects list updated.
  useEffect(() => {
    loadProjects();
    loadModels();
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Separate, mount-only Escape listener. Reads onCloseRef.current so it
  // always calls the latest onClose without needing it as a dependency.
  useEffect(() => {
    // Consume the Esc (see ThreadSwitcher) — the modal is open for as long as
    // this component is mounted, so an Escape here always closes it.
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const slug = slugify(name) || "untitled";

  const submit = async () => {
    if (busy) return;
    if (!name.trim()) {
      setError("Give the workspace a name.");
      return;
    }
    // E2 intent gate: a signed-out user committing to create doesn't fire the
    // doomed 403 — stash what they wanted and sign in; the Launcher replays
    // the intent when status flips to signed_in. Gate on "anonymous"
    // specifically: "loading" means the token restore is still in flight and
    // must not bounce a signed-in user into a redundant sign-in.
    if (authEnabled && authStatus === "anonymous") {
      stashAuthIntent({ kind: "create", name, posture: startIn, group: group.trim() });
      void signIn();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const sessionId = await performCreate({ name, posture: startIn, group });
      router.push(sessionUrl(sessionId, { view: startIn }));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create the workspace");
      setBusy(false);
    }
  };

  const StartCard = ({
    id,
    icon: Icon,
    label,
    hint,
  }: {
    id: ViewMode;
    icon: typeof MessageSquare;
    label: string;
    hint: string;
  }) => {
    const on = startIn === id;
    return (
      <button
        type="button"
        onClick={() => setStartIn(id)}
        className={cn(
          "flex-1 flex items-center gap-2.5 h-[52px] px-3 rounded-md border text-left transition-colors",
          on ? "border-primary/60 bg-primary/10" : "border-border bg-surface-2 hover:bg-surface-3"
        )}
      >
        <Icon className={cn("h-4 w-4 shrink-0", on ? "text-primary" : "text-muted-foreground")} />
        <div className="min-w-0">
          <div className={cn("text-[12.5px] font-medium", on ? "text-foreground" : "text-foreground/85")}>
            {label}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">{hint}</div>
        </div>
        {on && <Check className="h-3.5 w-3.5 text-primary ml-auto shrink-0" />}
      </button>
    );
  };

  return (
    <div
      className="fixed inset-0 z-[120] grid place-items-center p-6 bg-black/55"
      onMouseDown={onClose}
      role="dialog"
      aria-label="New session"
    >
      <div
        className="w-full max-w-[420px] rounded-lg border border-border bg-surface-1 shadow-lg animate-in fade-in-0 slide-in-from-bottom-2 duration-200"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center px-5 h-[52px] border-b border-border">
          <span className="text-sm font-semibold">New session</span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="ml-auto h-7 w-7 grid place-items-center rounded-md hover:bg-surface-2 text-muted-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="space-y-1.5">
            <input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Workspace name — e.g. sync_fifo"
              className="w-full h-10 px-3 rounded-md border border-border bg-surface-2 text-sm outline-none focus:border-primary/50 placeholder:text-muted-foreground/50"
            />
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70 font-mono pl-0.5">
              <Folder className="h-3 w-3" /> workspace/<span className="text-foreground/70">{slug}</span>/
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-muted-foreground">Start in</label>
            <div className="flex gap-2">
              <StartCard id="agent" icon={MessageSquare} label="Chat" hint="Agent-led" />
              <StartCard id="ide" icon={Columns2} label="IDE" hint="Editor + tools" />
            </div>
          </div>

          {!showGroup ? (
            <button
              type="button"
              onClick={() => setShowGroup(true)}
              className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-3 w-3" /> Add to a group{" "}
              <span className="text-muted-foreground/50">(optional)</span>
            </button>
          ) : (
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                <Layers className="h-3 w-3" /> Group{" "}
                <span className="text-muted-foreground/50 font-normal">— a tag, not a folder</span>
              </label>
              <input
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="asu_hackathon"
                list="launcher-groups"
                className="w-full h-9 px-3 rounded-md border border-border bg-surface-2 text-sm outline-none focus:border-primary/50 placeholder:text-muted-foreground/50 font-mono"
              />
              <datalist id="launcher-groups">
                {projects.map((p) => (
                  <option key={p.id} value={p.name} />
                ))}
              </datalist>
            </div>
          )}

          {authEnabled && authStatus === "anonymous" && (
            <p className="text-[11.5px] text-muted-foreground">
              You&apos;ll be asked to sign in first — your workspace is created right after.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-border">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={busy}>
            Create session <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

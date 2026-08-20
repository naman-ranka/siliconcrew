"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Loader2,
  Plus,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { skillsApi } from "@/lib/api";
import type { SkillDetail, SkillLayer, SkillSummary } from "@/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Skills — the built-in pack, and your own layer over it.
 *
 * The page states the merge rules and then gets out of the way. Every row says
 * which layer answered for that name; the only control is on or off. No
 * conditions, no ordering, no priority language — the model this page has to
 * teach is "yours replaces ours, or ours", and anything richer would be a rules
 * engine wearing a UI.
 *
 * Nothing here decides anything. The backend owns the four rules; this reads
 * what it decided and re-reads after every change, because a skill list is
 * owner-scoped state and a cached copy in the browser would be the same lie as
 * a cached copy on the server.
 */

const LAYER_LABEL: Record<SkillLayer, string> = {
  builtin: "Built-in",
  user: "Yours",
  "user-replaces-builtin": "Yours, replacing a built-in",
};

const NEW_SKILL_TEMPLATE = `---
name: my-skill
description: One line naming the situation this applies to, so the agent knows when to read it.
---

# When this applies

...

# What to do

...
`;

function LayerBadge({ layer }: { layer: SkillLayer }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10.5px] font-medium border",
        layer === "builtin"
          ? "border-border text-muted-foreground"
          : "border-primary/40 text-primary"
      )}
    >
      {LAYER_LABEL[layer]}
    </span>
  );
}

/** On or off. The whole vocabulary of this page. */
function Toggle({
  on,
  busy,
  label,
  onChange,
}: {
  on: boolean;
  busy: boolean;
  label: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={busy}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!on);
      }}
      className={cn(
        "relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50",
        on ? "bg-primary" : "bg-muted-foreground/40"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-background transition-transform",
          on ? "translate-x-[18px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

export function SkillsPage() {
  const router = useRouter();
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [unmatched, setUnmatched] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const index = await skillsApi.list();
      setSkills(index.skills);
      setUnmatched(index.unmatched_disabled);
      setError(null);
    } catch (e) {
      // Honest emptiness: a failed read says so instead of rendering "no
      // skills", which would read as "the agent has no knowledge".
      setSkills(null);
      setError(e instanceof Error ? e.message : "Could not load skills.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    skillsApi
      .read(selected)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not read that skill.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const act = useCallback(
    async (key: string, fn: () => Promise<unknown>) => {
      setBusy(key);
      setError(null);
      try {
        await fn();
        await refresh();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "That did not work.");
        return false;
      } finally {
        setBusy(null);
      }
    },
    [refresh]
  );

  const editing = draft !== null;
  const safetyOff = useMemo(
    () => (skills ?? []).some((s) => s.always_load && !s.enabled),
    [skills]
  );

  const saveDraft = async () => {
    if (draft === null) return;
    const match = /^\s*---[\s\S]*?\bname:\s*([^\s#]+)/.exec(draft);
    if (!match) {
      setError("A skill starts with YAML frontmatter carrying a 'name' and a 'description'.");
      return;
    }
    const name = match[1].trim();
    const ok = await act("save", () => skillsApi.save(name, draft));
    if (ok) {
      setDraft(null);
      setCreating(false);
      setSelected(name);
      // Re-read: the saved text is now the layer's text, and the page must show
      // what the store holds rather than what the editor last had in it.
      setDetail(await skillsApi.read(name));
    }
  };

  return (
    <main className="h-screen w-screen overflow-hidden flex flex-col bg-background text-foreground">
      <header className="flex items-center gap-3 border-b border-border px-5 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          aria-label="Back"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <BookOpen className="h-4 w-4 text-muted-foreground" />
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight">Skills</h1>
          <p className="text-[12px] text-muted-foreground leading-tight">
            Procedural knowledge the agent reads when the situation matches. A skill you
            write with the same name replaces the built-in one — nothing is merged.
          </p>
        </div>
        <div className="ml-auto">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setCreating(true);
              setSelected(null);
              setDraft(NEW_SKILL_TEMPLATE);
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            New skill
          </Button>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="mx-5 mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12.5px]"
        >
          {error}
        </div>
      )}

      {safetyOff && (
        <div
          role="status"
          data-testid="safety-net-off"
          className="mx-5 mt-3 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12.5px]"
        >
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-600" />
          <span>
            The always-in-force verification skill is switched off. Nothing in a run ever
            says &ldquo;your test was too easy&rdquo;, so this one has no trigger of its
            own — every run made while it is off is stamped as such.
          </span>
        </div>
      )}

      {unmatched.length > 0 && (
        <div
          role="alert"
          className="mx-5 mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12.5px]"
        >
          <p className="mb-1.5">
            {unmatched.length === 1 ? "A skill you" : "Skills you"} switched off no longer
            {unmatched.length === 1 ? " exists" : " exist"} under that name — so nothing is
            switched off by {unmatched.length === 1 ? "it" : "them"}.
          </p>
          <div className="flex flex-wrap gap-2">
            {unmatched.map((name) => (
              <Button
                key={name}
                size="sm"
                variant="outline"
                className="h-6 text-[11.5px]"
                disabled={busy === `clear:${name}`}
                onClick={() => act(`clear:${name}`, () => skillsApi.setEnabled(name, true))}
              >
                Clear &ldquo;{name}&rdquo;
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[minmax(280px,380px)_1fr] gap-0">
        {/* The list */}
        <div className="min-h-0 overflow-y-auto border-r border-border p-3 space-y-1.5">
          {skills === null ? (
            <p className="px-2 py-6 text-[12.5px] text-muted-foreground">
              {error ? "Skills could not be read." : "Loading…"}
            </p>
          ) : (
            skills.map((s) => (
              <div
                key={s.name}
                data-testid={`skill-row-${s.name}`}
                onClick={() => {
                  setDraft(null);
                  setCreating(false);
                  setSelected(s.name);
                }}
                className={cn(
                  "cursor-pointer rounded-md border px-3 py-2",
                  selected === s.name ? "border-primary/60 bg-surface-2" : "border-border",
                  !s.enabled && "opacity-60"
                )}
              >
                <div className="flex items-center gap-2">
                  {/* The one skill whose failure mode is silence gets its own
                      mark — it is not "more important", it is un-triggered. */}
                  {s.always_load && (
                    <ShieldCheck
                      className="h-3.5 w-3.5 shrink-0 text-amber-600"
                      aria-label="Always in force"
                    />
                  )}
                  <span className="truncate text-[13px] font-medium">{s.name}</span>
                  <span className="ml-auto" />
                  <LayerBadge layer={s.layer} />
                  <Toggle
                    on={s.enabled}
                    busy={busy === `toggle:${s.name}`}
                    label={`${s.enabled ? "Disable" : "Enable"} ${s.name}`}
                    onChange={(next) =>
                      act(`toggle:${s.name}`, () => skillsApi.setEnabled(s.name, next))
                    }
                  />
                </div>
                {s.description && (
                  <p className="mt-1 text-[12px] text-muted-foreground line-clamp-2">
                    {s.description}
                  </p>
                )}
                {s.always_load && (
                  <p className="mt-1 text-[11.5px] text-amber-600">
                    Always in force — it has no trigger of its own.
                  </p>
                )}
                {s.builtin_changed && (
                  <p className="mt-1 text-[11.5px] text-amber-600">
                    The built-in this replaces has changed since you forked it. Yours is
                    still what runs.
                  </p>
                )}
                {s.error && (
                  <p className="mt-1 text-[11.5px] text-destructive">
                    Your version could not be read: {s.error}
                  </p>
                )}
              </div>
            ))
          )}
        </div>

        {/* The one being read or written */}
        <div className="min-h-0 overflow-y-auto p-4">
          {creating || (selected && detail) ? (
            <div className="h-full flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <h2 className="text-[14px] font-semibold truncate">
                  {creating ? "New skill" : detail?.name}
                </h2>
                {!creating && detail && <LayerBadge layer={detail.layer} />}
                <div className="ml-auto flex items-center gap-2">
                  {editing ? (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setDraft(null);
                          setCreating(false);
                        }}
                      >
                        Cancel
                      </Button>
                      <Button size="sm" disabled={busy === "save"} onClick={saveDraft}>
                        {busy === "save" && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                        Save
                      </Button>
                    </>
                  ) : (
                    <>
                      {detail?.layer !== "builtin" && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy === "reset"}
                          onClick={async () => {
                            const name = detail!.name;
                            const ok = await act("reset", () => skillsApi.remove(name));
                            if (ok) {
                              // A replacement resets to the shipped text; a
                              // skill that was only yours is now gone.
                              setSelected(detail!.builtin_text ? name : null);
                              if (detail!.builtin_text) setDetail(await skillsApi.read(name));
                            }
                          }}
                        >
                          <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                          {detail?.builtin_text ? "Reset to shipped" : "Delete"}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={() => setDraft(detail?.text ?? NEW_SKILL_TEMPLATE)}
                      >
                        {detail?.layer === "builtin" ? "Replace with your own" : "Edit"}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {!creating && detail?.builtin_changed && (
                <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12px]">
                  The built-in version has changed since you replaced it. Updating a
                  built-in never overwrites your copy — reset if you want the shipped text
                  back.
                </p>
              )}

              <textarea
                aria-label="Skill text"
                readOnly={!editing}
                spellCheck={false}
                value={editing ? draft! : detail?.text ?? ""}
                onChange={(e) => setDraft(e.target.value)}
                className={cn(
                  "flex-1 min-h-[340px] w-full resize-none rounded-md border border-border bg-surface-1 p-3",
                  "font-mono text-[12.5px] leading-relaxed outline-none focus:border-primary/60",
                  !editing && "text-muted-foreground"
                )}
              />
            </div>
          ) : (
            <div className="h-full grid place-items-center text-center px-6">
              <div className="max-w-[420px] text-[12.5px] text-muted-foreground space-y-2">
                <p>
                  {detailLoading ? "Reading…" : "Pick a skill to read it, or write one of your own."}
                </p>
                <p>
                  A skill you write with the same name as a built-in replaces it entirely.
                  Switching one off leaves a name in a list — never a copy — and updating a
                  built-in never overwrites what you wrote.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  FileCode2,
  GitFork,
  Layers,
  Loader2,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react";
import { templatesApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { stashAuthIntent } from "@/lib/authIntent";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { plural } from "./util";
import type { TemplateDetail, TemplateSummary } from "@/types";

export interface TemplatePreviewProps {
  template: TemplateSummary;
  onClose: () => void;
  /** Fork the bundle and navigate into the new session. Returns when done so
   * the button can show its pending state; may reject (e.g. hosted 400). */
  onFork: (templateId: string) => Promise<void>;
}

type DetailState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; detail: TemplateDetail };

/**
 * Right-hand slide-over preview for a template bundle (Wave 11, A8). A NEW
 * component — ThreadDrawer is Session-bound (owner-checked session endpoints)
 * and not reusable here. Mirrors its layout/feel over the PUBLIC
 * ``templatesApi.get``: what's inside (files + conversations) + a "Fork this
 * example" primary action.
 */
export function TemplatePreview({ template, onClose, onFork }: TemplatePreviewProps) {
  const { enabled: authEnabled, status: authStatus, signIn } = useAuth();
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [forking, setForking] = useState(false);
  const [forkError, setForkError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    templatesApi
      .get(template.id)
      .then((detail) => {
        if (!cancelled) setState({ status: "ready", detail });
      })
      .catch((e) => {
        if (!cancelled)
          setState({ status: "error", message: e instanceof Error ? e.message : "Failed to load" });
      });
    return () => {
      cancelled = true;
    };
  }, [template.id]);

  const detail = state.status === "ready" ? state.detail : null;
  const files = detail?.files ?? [];
  const conversations = detail?.conversations ?? [];

  const doFork = async () => {
    // E2 intent gate: signed-out fork signs in first; the Launcher replays
    // the fork when auth completes ("anonymous" only — never bounce a user
    // whose token restore is still loading).
    if (authEnabled && authStatus === "anonymous") {
      stashAuthIntent({ kind: "fork", templateId: template.id });
      void signIn();
      return;
    }
    setForking(true);
    setForkError(null);
    try {
      await onFork(template.id);
      // On success the caller navigates away — no need to reset state here.
    } catch (e) {
      setForkError(e instanceof Error ? e.message : "Fork failed");
      setForking(false);
    }
  };

  return (
    <div
      data-testid="template-preview"
      className="w-[336px] h-full flex flex-col border-l border-border bg-surface-1 animate-in slide-in-from-right-4 duration-200"
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-3.5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg grid place-items-center shrink-0 border bg-primary/15 text-primary border-primary/25">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold truncate">{template.name}</div>
            <div className="text-[10px] text-muted-foreground truncate">Example bundle</div>
          </div>
          <button
            type="button"
            aria-label="Close preview"
            onClick={onClose}
            className="h-6 w-6 grid place-items-center rounded-md hover:bg-surface-2 text-muted-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {template.description && (
          <p className="mt-3 text-[12px] leading-snug text-muted-foreground">
            {template.description}
          </p>
        )}

        {/* Meta row */}
        <div className="mt-3 flex items-center gap-4 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FileCode2 className="h-3.5 w-3.5" />
            {plural(template.file_count, "file")}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5" />
            {plural(template.run_count, "run")}
          </span>
          {template.platform && (
            <span className="ml-auto inline-flex items-center gap-1.5 min-w-0">
              <span className="truncate">{template.platform}</span>
            </span>
          )}
        </div>
      </div>

      {/* What's inside */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {template.highlights.length > 0 && (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Highlights
            </h3>
            <ul className="space-y-1.5">
              {template.highlights.map((h, i) => (
                <li key={i} className="flex items-start gap-2 text-[12px] text-foreground/85">
                  <span className="mt-1.5 h-1 w-1 rounded-full bg-primary/60 shrink-0" />
                  <span className="min-w-0">{h}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            What&apos;s inside
          </h3>
          {state.status === "loading" ? (
            <div className="space-y-1.5">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-4 w-full" />
              ))}
            </div>
          ) : state.status === "error" ? (
            <p className="text-[11px] text-muted-foreground">Couldn&apos;t load contents.</p>
          ) : (
            <div className="space-y-1">
              {files.slice(0, 40).map((f) => (
                <div
                  key={f}
                  className="flex items-center gap-1.5 text-[11.5px] font-mono text-foreground/75"
                >
                  <FileCode2 className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                  <span className="truncate">{f}</span>
                </div>
              ))}
              {files.length > 40 && (
                <div className="text-[10px] text-muted-foreground/60 pl-4.5">
                  +{files.length - 40} more
                </div>
              )}
              {files.length === 0 && (
                <p className="text-[11px] text-muted-foreground">No files listed.</p>
              )}
            </div>
          )}
        </section>

        {conversations.length > 0 && (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Conversations
            </h3>
            <div className="space-y-1">
              {conversations.map((c) => (
                <div
                  key={c}
                  className="flex items-center gap-1.5 text-[11.5px] text-foreground/75"
                >
                  <MessageSquare className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                  <span className="truncate">{c}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Fork action */}
      <div className="p-3 border-t border-border">
        {forkError && (
          <p className="mb-2 text-[11px] text-destructive" role="alert">
            {forkError}
          </p>
        )}
        <Button
          className="w-full h-10"
          disabled={forking}
          onClick={() => void doFork()}
          data-testid="fork-template"
        >
          {forking ? (
            <>
              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Forking…
            </>
          ) : (
            <>
              <GitFork className="h-4 w-4 mr-1.5" /> Fork this example
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

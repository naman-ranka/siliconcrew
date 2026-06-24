"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Key,
  ExternalLink,
  Check,
  Trash2,
  Loader2,
  Info,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { keysApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type ProviderId = "anthropic" | "openai" | "gemini";

const PROVIDERS: {
  id: ProviderId;
  label: string;
  env: string;
  console: string;
  hint: string;
  freeTier?: boolean;
}[] = [
  { id: "anthropic", label: "Anthropic", env: "ANTHROPIC_API_KEY", console: "https://console.anthropic.com/settings/keys", hint: "Starts with sk-ant-" },
  { id: "openai", label: "OpenAI", env: "OPENAI_API_KEY", console: "https://platform.openai.com/api-keys", hint: "Starts with sk-" },
  { id: "gemini", label: "Google (Gemini)", env: "GOOGLE_API_KEY", console: "https://aistudio.google.com/apikey", hint: "Google AI Studio key", freeTier: true },
];

type Mode = "loading" | "signin" | "self_host" | "vault_off" | "hosted" | "error";

/**
 * Settings → API Keys. Mode-adaptive (see the BYOK brief):
 *  - self-host (auth not configured / 400): read-only env-key guidance, no entry.
 *  - hosted + signed out: sign-in prompt.
 *  - hosted + signed in: per-provider CRUD against the encrypted vault.
 *  - hosted + vault off (503): graceful "key storage isn't configured".
 * Shared open-state lives in the store so the sidebar Settings button and the
 * chat "Add an API key" CTA both drive this one modal.
 */
export function SettingsModal() {
  const settingsOpen = useStore((s) => s.settingsOpen);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const pushToast = useStore((s) => s.pushToast);
  const models = useStore((s) => s.models);
  const { enabled, status, signIn } = useAuth();

  const [configured, setConfigured] = useState<string[]>([]);
  const [listError, setListError] = useState<{ status?: number; message: string } | null>(null);
  const [listing, setListing] = useState(false);

  // Force the model picker's availability to re-derive after a key change.
  const reloadModels = useCallback(async () => {
    useStore.setState({ modelsLoaded: false });
    await useStore.getState().loadModels();
  }, []);

  const refreshList = useCallback(async () => {
    setListing(true);
    setListError(null);
    try {
      const { providers } = await keysApi.list();
      setConfigured(providers);
    } catch (e) {
      const err = e as Error & { status?: number };
      setListError({ status: err.status, message: err.message });
    } finally {
      setListing(false);
    }
  }, []);

  // Fetch state when the modal opens for a signed-in hosted user. Self-host is
  // detected from auth config (no /api/keys call — it would 400).
  useEffect(() => {
    if (!settingsOpen) return;
    if (enabled && status === "signed_in") void refreshList();
    // Make sure availability is fresh for the self-host derivation + post-change UI.
    void useStore.getState().loadModels();
  }, [settingsOpen, enabled, status, refreshList]);

  const mode: Mode = useMemo(() => {
    if (!enabled) return "self_host";
    if (status === "loading") return "loading";
    if (status !== "signed_in") return "signin";
    if (listing && !listError) return "loading";
    if (listError?.status === 400) return "self_host"; // belt-and-suspenders
    if (listError?.status === 503) return "vault_off";
    if (listError) return "error";
    return "hosted";
  }, [enabled, status, listing, listError]);

  // Self-host: derive configured/missing per provider from model availability
  // (GET /api/keys 400s here, so /api/models is the source of truth).
  const envUsable = useMemo(() => {
    const s = new Set<string>();
    for (const m of models) if (m.available) s.add(m.provider);
    return s;
  }, [models]);

  return (
    <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
      <DialogContent
        className="bg-surface-1 border-border max-w-lg"
        data-testid="settings-modal"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="h-4 w-4 text-primary" /> Settings
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            API keys for the LLM providers the agent uses.
          </DialogDescription>
        </DialogHeader>

        <section aria-labelledby="byok-heading" className="space-y-3" data-testid="byok-section" data-mode={mode}>
          <h3 id="byok-heading" className="text-sm font-medium text-foreground">
            API Keys
          </h3>
          <Separator />

          {mode === "loading" && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          )}

          {mode === "signin" && <SignInState onSignIn={signIn} />}

          {mode === "self_host" && <SelfHostState envUsable={envUsable} />}

          {mode === "vault_off" && (
            <Notice icon={<AlertTriangle className="h-4 w-4 text-status-fail" />}>
              Key storage isn’t configured on this server, so BYOK is unavailable.
              The hosted free tier (Gemini) may still work; other providers need a
              server-side key.
            </Notice>
          )}

          {mode === "error" && (
            <div className="space-y-2" role="alert">
              <Notice icon={<AlertTriangle className="h-4 w-4 text-status-fail" />}>
                Couldn’t load your API keys{listError?.message ? `: ${listError.message}` : "."}
              </Notice>
              <Button variant="outline" size="sm" onClick={() => void refreshList()}>
                Retry
              </Button>
            </div>
          )}

          {mode === "hosted" && (
            <div className="space-y-3">
              <Notice icon={<ShieldCheck className="h-4 w-4 text-status-pass" />}>
                Keys are envelope-encrypted at rest and used only for your requests.
                We never display a stored key.
              </Notice>
              {PROVIDERS.map((p) => (
                <ProviderRow
                  key={p.id}
                  provider={p}
                  isConfigured={configured.includes(p.id)}
                  onSaved={async () => {
                    await refreshList();
                    await reloadModels();
                  }}
                  onRemoved={async () => {
                    await refreshList();
                    await reloadModels();
                  }}
                  pushToast={pushToast}
                />
              ))}
            </div>
          )}
        </section>
      </DialogContent>
    </Dialog>
  );
}

function Notice({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-surface-2 px-3 py-2 text-xs text-muted-foreground" role="note">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span>{children}</span>
    </div>
  );
}

function SignInState({ onSignIn }: { onSignIn: () => void }) {
  return (
    <div className="space-y-3 py-2" data-testid="byok-signin">
      <Notice icon={<Info className="h-4 w-4 text-info" />}>
        Sign in to add your own API keys and use models beyond the free tier.
      </Notice>
      <Button onClick={onSignIn} className="gap-1.5">
        Sign in with Google
      </Button>
    </div>
  );
}

function SelfHostState({ envUsable }: { envUsable: Set<string> }) {
  return (
    <div className="space-y-3" data-testid="byok-self-host">
      <Notice icon={<Info className="h-4 w-4 text-info" />}>
        This instance uses <span className="font-medium text-foreground">environment keys</span>.
        Set them in <code className="text-foreground">.env</code> (or{" "}
        <code className="text-foreground">.env.docker</code>) and restart the server —
        per-user key storage is disabled in local mode.
      </Notice>
      <ul className="space-y-1.5">
        {PROVIDERS.map((p) => {
          const present = envUsable.has(p.id);
          return (
            <li
              key={p.id}
              className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-xs"
              data-testid={`byok-env-${p.id}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={cn("h-2 w-2 rounded-full shrink-0", present ? "bg-status-pass" : "bg-muted-foreground/40")}
                  aria-hidden
                />
                <span className="text-foreground">{p.label}</span>
                <code className="text-muted-foreground truncate">{p.env}</code>
              </div>
              <span className={cn("shrink-0", present ? "text-status-pass" : "text-muted-foreground")}>
                {present ? "configured" : "not set"}
              </span>
            </li>
          );
        })}
      </ul>
      <a
        href="https://github.com/naman-ranka/siliconcrew/blob/main/frontend/.env.example"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-xs text-info hover:underline outline-none focus-visible:ring-2 focus-visible:ring-primary/60 rounded"
      >
        View .env.example <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

function ProviderRow({
  provider,
  isConfigured,
  onSaved,
  onRemoved,
  pushToast,
}: {
  provider: (typeof PROVIDERS)[number];
  isConfigured: boolean;
  onSaved: () => Promise<void>;
  onRemoved: () => Promise<void>;
  pushToast: ReturnType<typeof useStore.getState>["pushToast"];
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = saving || removing;

  const save = async () => {
    const key = value.trim();
    if (!key) {
      setError("Enter a key, or leave blank to keep the current one.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await keysApi.save(provider.id, key);
      setValue(""); // never keep the secret in state
      pushToast({ kind: "success", title: `${provider.label} key saved` });
      await onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setRemoving(true);
    setError(null);
    try {
      await keysApi.remove(provider.id);
      setConfirmRemove(false);
      pushToast({ kind: "info", title: `${provider.label} key removed` });
      await onRemoved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed");
    } finally {
      setRemoving(false);
    }
  };

  const inputId = `byok-input-${provider.id}`;

  return (
    <div className="rounded-md border border-border p-3 space-y-2" data-testid={`byok-row-${provider.id}`}>
      <div className="flex items-center justify-between">
        <label htmlFor={inputId} className="flex items-center gap-2 text-sm font-medium text-foreground">
          {provider.label}
          {isConfigured && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-status-pass/15 px-2 py-0.5 text-[10px] text-status-pass"
              data-testid={`byok-configured-${provider.id}`}
            >
              <Check className="h-3 w-3" /> configured
            </span>
          )}
          {provider.freeTier && !isConfigured && (
            <span className="rounded-full bg-info/15 px-2 py-0.5 text-[10px] text-info">free tier</span>
          )}
        </label>
        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={provider.console}
              target="_blank"
              rel="noreferrer"
              aria-label={`Where to get a ${provider.label} key`}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/60 rounded"
            >
              Get a key <ExternalLink className="h-3 w-3" />
            </a>
          </TooltipTrigger>
          <TooltipContent side="left">{provider.hint}</TooltipContent>
        </Tooltip>
      </div>

      {provider.freeTier && (
        <p className="text-[11px] text-muted-foreground">
          Gemini works without a key on the capped free hosted tier. Add a key to lift the cap.
        </p>
      )}

      <div className="flex items-center gap-2">
        <Input
          id={inputId}
          type="password"
          autoComplete="off"
          placeholder={isConfigured ? "Enter a new key to replace" : `Paste your ${provider.label} key`}
          value={value}
          disabled={busy}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void save();
          }}
          aria-label={`${provider.label} API key`}
          aria-describedby={`${inputId}-hint`}
          className="flex-1 bg-surface-2 border-border text-sm"
        />
        <Button size="sm" onClick={() => void save()} disabled={busy || !value.trim()} data-testid={`byok-save-${provider.id}`}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
        </Button>
        {isConfigured && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirmRemove(true)}
            disabled={busy}
            aria-label={`Remove ${provider.label} key`}
            data-testid={`byok-remove-${provider.id}`}
            className="border-border text-status-fail hover:bg-status-fail/10"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      <p id={`${inputId}-hint`} className="text-[10px] text-muted-foreground">
        {provider.hint}
      </p>

      {confirmRemove && (
        <div className="flex items-center justify-between rounded bg-status-fail/10 px-2 py-1.5 text-xs" role="alertdialog" aria-label={`Confirm remove ${provider.label} key`}>
          <span className="text-foreground">Remove the stored {provider.label} key?</span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setConfirmRemove(false)} disabled={removing}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="h-6 text-xs bg-status-fail hover:bg-status-fail/90 text-white"
              onClick={() => void remove()}
              disabled={removing}
              data-testid={`byok-remove-confirm-${provider.id}`}
            >
              {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Remove"}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-status-fail" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

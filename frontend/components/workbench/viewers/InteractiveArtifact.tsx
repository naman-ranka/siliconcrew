"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircuitBoard, Download, ShieldAlert, Zap, ZapOff } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ViewerError, ViewerSkeleton } from "./panels";
import {
  checkProvenance,
  composeSrcdoc,
  createWebsimSession,
  parseSimMeta,
  parseWebsimPayload,
  DEFAULT_CLOCK_HZ,
  MAX_CLOCK_HZ,
  MAX_CYCLES_PER_FRAME,
  type BridgeInbound,
  type Freshness,
  type WebsimSession,
} from "@/lib/websim";

// `interactive:<path>` — an agent-authored dashboard (<top>.dashboard.html)
// running against a REAL gate-level simulation of the design's yosys netlist,
// entirely client-side (lib/websim.ts).
//
// Trust boundary: the agent's HTML/JS executes ONLY inside the sandboxed
// iframe (`sandbox="allow-scripts"` — never allow-same-origin: the frame gets
// an opaque origin, no cookies/auth/parent DOM). The engine runs out here in
// the trusted shell; the frame talks to it exclusively via postMessage. The
// provenance strip is rendered by the shell OUTSIDE the iframe so dashboard
// code cannot spoof it (invariant 4: a mockup must never pass as a live sim).

type SimState =
  | { phase: "loading" }
  | { phase: "mockup" } // no siliconcrew-sim meta tag — declared static
  | { phase: "broken"; detail: string } // meta present but netlist unusable
  | { phase: "live"; netlist: string; sources: string[]; freshness: Freshness };

export function InteractiveArtifact({ path }: { path: string }) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const slice = useStore((s) => s.fileCache[path]);
  const loadFile = useStore((s) => s.loadFile);

  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sessionRef = useRef<WebsimSession | null>(null);
  const clockHzRef = useRef(DEFAULT_CLOCK_HZ);
  const runningRef = useRef(false);

  const [sim, setSim] = useState<SimState>({ phase: "loading" });
  const [srcdoc, setSrcdoc] = useState<string | null>(null);
  const [cycleDisplay, setCycleDisplay] = useState(0);

  useEffect(() => {
    if (sessionId) void loadFile(path);
  }, [sessionId, path, loadFile]);

  const html = slice?.file?.content ?? null;

  // Post the current outputs into the frame (the ONLY way dashboard state
  // may change — every displayed value originates from the engine).
  const postUpdate = useCallback(() => {
    const s = sessionRef.current;
    const frame = iframeRef.current?.contentWindow;
    if (!s || !frame) return;
    frame.postMessage(
      { type: "websim:update", outputs: s.readOutputs(), cycle: s.cycle },
      "*"
    );
  }, []);

  // Build the sim session + srcdoc whenever the dashboard html changes.
  useEffect(() => {
    if (!sessionId || html == null) return;
    let cancelled = false;
    sessionRef.current?.dispose();
    sessionRef.current = null;
    setSim({ phase: "loading" });
    setSrcdoc(null);
    setCycleDisplay(0);

    (async () => {
      const netlistPath = parseSimMeta(html);
      if (!netlistPath) {
        if (!cancelled) {
          setSim({ phase: "mockup" });
          setSrcdoc(composeSrcdoc(html));
        }
        return;
      }
      try {
        const bytes = await workspaceApi.fetchRawBytes(sessionId, netlistPath);
        const payload = parseWebsimPayload(new TextDecoder().decode(bytes));
        if (!payload) throw new Error(`${netlistPath} is not a websim-v1 artifact`);
        const session = await createWebsimSession(payload);
        if (cancelled) {
          session.dispose();
          return;
        }
        sessionRef.current = session;
        setSrcdoc(composeSrcdoc(html));
        setSim({
          phase: "live",
          netlist: netlistPath,
          sources: Object.keys(payload.sources),
          freshness: "unknown",
        });
        // Freshness lands asynchronously — never block the sim on it, never
        // claim fresh before the hashes agree.
        void checkProvenance(payload, (p) => workspaceApi.fetchRawBytes(sessionId, p)).then(
          (freshness) => {
            if (!cancelled) {
              setSim((prev) => (prev.phase === "live" ? { ...prev, freshness } : prev));
            }
          }
        );
      } catch (err) {
        if (!cancelled) {
          setSim({
            phase: "broken",
            detail: err instanceof Error ? err.message : String(err),
          });
          setSrcdoc(composeSrcdoc(html));
        }
      }
    })();

    return () => {
      cancelled = true;
      sessionRef.current?.dispose();
      sessionRef.current = null;
    };
  }, [sessionId, html]);

  // Bridge protocol: answer the frame's hello with init; apply its input /
  // clock requests. Only messages from OUR frame are honored.
  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (!iframeRef.current || ev.source !== iframeRef.current.contentWindow) return;
      const msg = ev.data as BridgeInbound | null;
      if (!msg || typeof msg.type !== "string") return;
      const s = sessionRef.current;
      if (msg.type === "websim:hello") {
        iframeRef.current.contentWindow?.postMessage(
          { type: "websim:init", ports: s?.ports ?? [], connected: s !== null },
          "*"
        );
        if (s) {
          runningRef.current = true;
          postUpdate();
        }
      } else if (msg.type === "websim:setInput" && s && typeof msg.name === "string") {
        s.setInput(msg.name, Number(msg.value) || 0);
        if (!s.hasClock) postUpdate();
      } else if (msg.type === "websim:setClockHz" && typeof msg.hz === "number") {
        clockHzRef.current = Math.max(0, Math.min(MAX_CLOCK_HZ, msg.hz));
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [postUpdate]);

  // Clock loop: batched cycles per animation frame (RTL time constants assume
  // a real clock — one tick per frame would make a debouncer take minutes).
  // Paused while the tab is keep-alive-hidden (offsetParent null) or the
  // document is hidden: a sim the user can't see must not advance.
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let carry = 0;
    let lastShown = -1;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(0.25, (now - last) / 1000);
      last = now;
      const s = sessionRef.current;
      if (!s || !runningRef.current || !s.hasClock) return;
      if (document.hidden || containerRef.current?.offsetParent == null) return;
      carry += clockHzRef.current * dt;
      let n = Math.min(Math.floor(carry), MAX_CYCLES_PER_FRAME);
      carry -= n;
      if (n <= 0) return;
      while (n-- > 0) s.tickCycle();
      postUpdate();
      // Cycle counter is honesty UI (a dead dashboard is visibly dead), but
      // don't re-render the shell 60×/s for it.
      if (s.cycle - lastShown >= clockHzRef.current / 4 || s.cycle < lastShown) {
        lastShown = s.cycle;
        setCycleDisplay(s.cycle);
      }
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [postUpdate]);

  const fileName = path.split("/").pop() || path;
  const download = () => {
    if (sessionId) void workspaceApi.downloadRawFile(sessionId, path);
  };

  if (!slice || (slice.status === "loading" && html == null)) return <ViewerSkeleton />;
  if (slice.status === "error" && html == null) {
    return (
      <ViewerError
        title="Couldn't load this dashboard"
        detail={slice.error}
        onRetry={() => void loadFile(path)}
      />
    );
  }
  if (html == null) return <ViewerSkeleton />;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="interactive-artifact" ref={containerRef}>
      {/* Provenance strip — shell-rendered, outside the sandbox, unspoofable */}
      <div
        data-testid="websim-provenance"
        className={cn(
          "flex h-9 shrink-0 items-center gap-2 border-b border-border px-3 text-xs font-mono",
          sim.phase === "live" && sim.freshness !== "stale"
            ? "bg-surface-1 text-foreground"
            : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
        )}
      >
        {sim.phase === "live" ? (
          sim.freshness === "stale" ? (
            <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <Zap className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
          )
        ) : sim.phase === "loading" ? (
          <CircuitBoard className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ZapOff className="h-3.5 w-3.5 shrink-0" />
        )}
        <span className="truncate">
          {sim.phase === "loading" && `${fileName} — loading simulation…`}
          {sim.phase === "mockup" &&
            `${fileName} — static mockup, NOT connected to a simulation`}
          {sim.phase === "broken" && `${fileName} — simulation unavailable: ${sim.detail}`}
          {sim.phase === "live" && (
            <>
              live gate-level sim · {sim.netlist} ← {sim.sources.join(", ")}
              {sim.freshness === "stale" && " · STALE: sources changed — rebuild the netlist"}
              {sim.freshness === "unknown" && " · freshness unverified"}
            </>
          )}
        </span>
        {sim.phase === "live" && (
          <span className="ml-auto shrink-0 tabular-nums text-muted-foreground" data-testid="websim-cycles">
            {cycleDisplay.toLocaleString()} cycles
          </span>
        )}
        <span
          className="shrink-0 text-[10px] text-muted-foreground"
          title="Cycle-accurate simulation of the synthesized netlist. Not timing-accurate: no gate delays, no setup/hold analysis."
        >
          2-state+x · no timing
        </span>
        <Button
          size="sm"
          variant="ghost"
          className={cn("h-6 gap-1 px-2 text-[11px] font-sans", sim.phase !== "live" && "ml-auto")}
          onClick={download}
        >
          <Download className="h-3 w-3" /> Download
        </Button>
      </div>

      {srcdoc == null ? (
        <ViewerSkeleton />
      ) : (
        <iframe
          ref={iframeRef}
          title={fileName}
          // SECURITY: allow-scripts ONLY. Never add allow-same-origin — the
          // agent-authored document must stay on an opaque origin with no
          // access to auth, storage, or the parent DOM.
          sandbox="allow-scripts"
          srcDoc={srcdoc}
          className="min-h-0 w-full flex-1 border-0 bg-white"
          data-testid="websim-frame"
        />
      )}
    </div>
  );
}

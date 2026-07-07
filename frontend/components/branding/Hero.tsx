"use client";

import { ArrowUpRight, Github, CircleDot } from "lucide-react";
import { Logo } from "./Logo";
import { REPO_URL, ISSUES_URL, CVDP_RESULT } from "./links";

// Honest capability copy — every line is drawn from the root README's
// Capabilities section. No invented benchmarks, no marketing claims.
// TODO(owner): trim/reword these bullets; they mirror README.md:50-62.
const CAPABILITIES = [
  "Spec-first: generates a structured YAML spec, then synthesizable Verilog-2001.",
  "Self-checking testbenches with waveform-based debugging on simulation failures.",
  "RTL-to-GDSII through the OpenROAD flow, targeting the SkyWater 130nm PDK.",
  "Formal verification (SymbiYosys) and an optional XLS high-level-synthesis frontend.",
];

// The open EDA tools the flow actually runs on — credibility with designers.
const TOOLS = ["OpenROAD", "Yosys", "Icarus Verilog", "Verilator", "sky130"];

/**
 * The signed-out / empty-account identity strip: what SiliconCrew is, the flow
 * it runs, the open tools behind it, and the one real, sourced result (CVDP).
 * Rendered as ONE section on `/` — layout emphasis, not a second route. Styled
 * entirely via design tokens so it reads correctly in both dark and paper light.
 */
export function Hero() {
  return (
    <section data-testid="landing-hero" className="mb-9">
      <div className="rounded-xl border border-border bg-surface-1/60 p-6 md:p-7">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-lg bg-primary/15 grid place-items-center shrink-0 text-primary">
            <Logo className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-[19px] font-semibold tracking-tight">SiliconCrew</h1>
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground/80 border border-border rounded px-1.5 py-0.5">
                Open source · MIT
              </span>
            </div>
            <p className="mt-1 text-[13.5px] text-foreground/85 leading-snug">
              An autonomous LLM agent for RTL design, verification, and synthesis.
            </p>
            <p className="mt-1 text-[12px] text-muted-foreground">
              spec → RTL → lint → simulate → synthesis / PnR → GDS, driven by an agent on open EDA
              tools.
            </p>
          </div>
        </div>

        <ul className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
          {CAPABILITIES.map((c) => (
            <li key={c} className="flex items-start gap-2 text-[12.5px] text-foreground/80">
              <span className="mt-1.5 h-1 w-1 rounded-full bg-primary/70 shrink-0" />
              <span className="min-w-0">{c}</span>
            </li>
          ))}
        </ul>

        <div className="mt-5 flex items-center gap-2 flex-wrap">
          {TOOLS.map((t) => (
            <span
              key={t}
              className="text-[11px] font-medium text-muted-foreground bg-surface-2 border border-border rounded-md px-2 py-1"
            >
              {t}
            </span>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-3 flex-wrap">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg bg-primary text-primary-foreground text-[12.5px] font-medium hover:opacity-90"
          >
            <Github className="h-4 w-4" /> View on GitHub
          </a>
          <a
            href={ISSUES_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border text-[12.5px] font-medium text-foreground hover:bg-surface-2"
          >
            <CircleDot className="h-4 w-4" /> Issues
          </a>
          {/* One real, sourced number — the README's CVDP result, marked honest. */}
          <a
            href={`${REPO_URL}#preliminary-results`}
            target="_blank"
            rel="noreferrer noopener"
            title={CVDP_RESULT.detail}
            className="ml-auto inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground hover:text-foreground"
          >
            <span className="tabular-nums font-medium text-foreground/90">{CVDP_RESULT.value}</span>
            <span>{CVDP_RESULT.label}</span>
            <ArrowUpRight className="h-3 w-3" />
          </a>
        </div>
      </div>
    </section>
  );
}

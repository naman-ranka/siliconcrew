"use client";

import { useStore } from "@/lib/store";
import { Upload, FilePlus, CheckCircle2, Waves, ArrowRight, Sparkles } from "lucide-react";
import { useRef } from "react";

/**
 * First-run guidance shown in the center when the workspace is empty. The
 * first-time-user review found newcomers didn't know what to click; this lays
 * out the real pipeline in plain language and offers the two starting actions
 * (upload, or write a file) right where the eye lands.
 */
export function Onboarding() {
  const { uploadFiles, setArtifactTab, currentSession } = useStore();
  const fileInput = useRef<HTMLInputElement>(null);

  const steps = [
    { icon: <Upload className="h-4 w-4" />, title: "Add your design", body: "Upload Verilog/SystemVerilog, or write a file in the Code tab." },
    { icon: <FilePlus className="h-4 w-4" />, title: "Add a testbench", body: "A *_tb.v that drives your module — simulation needs one." },
    { icon: <CheckCircle2 className="h-4 w-4" />, title: "Lint, then Simulate", body: "Use the pipeline bar above. Lint checks syntax; Simulate runs it." },
    { icon: <Waves className="h-4 w-4" />, title: "Inspect the waveform", body: "See signals over time and exactly where a test fails." },
  ];

  return (
    <div className="h-full overflow-y-auto flex flex-col items-center justify-center p-8 text-center">
      <div className="w-12 h-12 rounded-2xl bg-primary/15 flex items-center justify-center mb-4">
        <Sparkles className="h-6 w-6 text-primary" />
      </div>
      <h2 className="text-lg font-semibold">Let&apos;s build a chip</h2>
      <p className="text-sm text-muted-foreground mt-1 mb-6 max-w-md">
        This is your hardware workbench. Bring or write RTL, then run it through the
        pipeline — lint, simulate, synthesize — and inspect the results.
      </p>

      <ol className="grid sm:grid-cols-2 gap-3 max-w-2xl w-full mb-6 text-left">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-3 rounded-lg border border-border bg-surface-1 p-3">
            <div className="shrink-0 mt-0.5 text-primary">{s.icon}</div>
            <div>
              <div className="text-sm font-medium flex items-center gap-1.5">
                <span className="text-[10px] text-muted-foreground font-mono">{i + 1}</span>
                {s.title}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{s.body}</div>
            </div>
          </li>
        ))}
      </ol>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={!currentSession}
          onClick={() => fileInput.current?.click()}
          className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm font-medium hover:bg-primary/90 disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          <Upload className="h-4 w-4" /> Upload RTL
        </button>
        <button
          type="button"
          disabled={!currentSession}
          onClick={() => setArtifactTab("code")}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-surface-2 disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          <FilePlus className="h-4 w-4" /> Write a file <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          aria-label="Upload design files"
          onChange={(e) => {
            if (e.target.files) void uploadFiles(Array.from(e.target.files));
            if (fileInput.current) fileInput.current.value = "";
          }}
        />
      </div>
      <p className="text-[11px] text-muted-foreground/70 mt-4">
        New here? Each step in the bar above lights up as you go.
      </p>
    </div>
  );
}

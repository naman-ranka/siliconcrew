# Data Model (frozen vocabulary)

Shared types for the manifest and runs. Express as Pydantic on the backend and
mirror as TypeScript in the frontend. Field names are the contract.

## DesignManifest — the single source of truth

Replaces today's fragile resolution (latest `*_spec.yaml` by mtime + a file
list passed per tool call). One manifest per session binds files, roles, the
two top modules, and constraints. Both the human (UI) and the agent (a manifest
tool) edit the same object.

```ts
type FileRole = "rtl" | "tb" | "sdc" | "include" | "other";

interface DesignFile {
  name: string;          // "decoder.v"
  role: FileRole;        // auto-derived (naming + content heuristics), user/agent overridable
  path: string;          // workspace-relative
}

interface DesignManifest {
  sessionId: string;
  files: DesignFile[];
  synthTop: string;      // DUT top for synthesis (TBs excluded)   e.g. "cpu_top"
  simTop: string;        // testbench top for simulation           e.g. "cpu_tb"
  clockPeriodNs: number; // 10.0
  platform: string;      // "sky130hd"
}
```

**Role derivation (deterministic, overridable):** `*_tb.v` / `tb_*` → `tb`;
a module with no ports that instantiates another → `tb`; `.sdc` → `sdc`;
`.vh`/`.svh` → `include`; else `rtl`. Roles decide what reaches each stage:

| Stage | File set | Top |
|---|---|---|
| Lint | `rtl` + `include` | elaborate `synthTop` |
| Simulate | `rtl` + chosen `tb` + `include` | `simTop` |
| Synthesize | `rtl` + `sdc` (no `tb`) | `synthTop` |

## Run model — unified sim + synth

One timeline, two kinds. Synth already has this on disk
(`synth_runs/synth_NNNN/` + `index.json` + `run_meta.json`). **Sim must mirror
it** (`sim_runs/sim_NNNN/`) so VCDs stop colliding and sims become comparable.

```ts
type RunKind = "sim" | "synth";
type RunStatus = "running" | "passed" | "failed";

interface RunBase {
  id: string;            // "sim_0004" | "synth_0003"
  kind: RunKind;
  status: RunStatus;
  createdAt: string;
  top: string;           // simTop or synthTop used
  pinned: boolean;       // protected from auto-prune
  parentRunId?: string;  // lineage (e.g. staged synth retry → child of parent)
  provenance: Provenance;
}

interface SimRun extends RunBase {
  kind: "sim";
  mode: "rtl" | "post_synth";
  vcdPath: string;                 // sim_runs/<id>/<simTop>.vcd  (per-run, isolated)
  passMarkerFound: boolean;
  failure?: { type: string; firstFailureLine?: string; timeNs?: number };
  compileCommand: string;          // surfaced for transparency
  simCommand: string;
}

interface SynthRun extends RunBase {
  kind: "synth";
  stages: { name: string; status: RunStatus }[];   // constraints..finish
  ppa?: { areaUm2: number; cells: number; wnsNs: number; tnsNs: number; fmaxMhz: number; powerMw: number };
  artifacts: { gdsii?: string; netlist?: string; reports?: string };
}

interface Provenance {           // stamped on every run for reproducibility
  repoCommit: string;
  iverilogVersion?: string;
  orfsImageDigest?: string;      // pin
  pdk?: string;
  numCores?: number;             // pin for P&R determinism
}

interface PpaDiff { a: string; b: string; rows: { metric: string; a: number; b: number; deltaPct?: number }[]; }
```

## Determinism contract

Every run = pure function of (manifest subset + pinned toolchain), executed in
an isolated dir. To make it reproducible:
- pin `orfsImageDigest`, `iverilogVersion`, `pdk` (stamp in `provenance`);
- pin `numCores` in the generated `config.mk` (synth P&R is the only real
  nondeterminism source — not pinned today);
- seed `$random` in sim where used.

## Gaps these types formalize (for the agents)

1. **Manifest/roles** — does not exist today; tools take per-call file lists.
2. **Sim-run isolation** — does not exist; sims run in `cwd`, VCDs overwrite.
3. **Unified run API** — synth-only today; generalize to sim+synth.
4. **Determinism pins** — `numCores` / seeds not set; add to `config.mk` + sim.

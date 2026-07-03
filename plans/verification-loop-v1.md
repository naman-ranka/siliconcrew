# Verification Loop v1 — Implementation Plan

Status: IMPLEMENTED (items 1-6; review corrections applied).  Branch: `claude/siliconc-workbench-v2-ilsd83`.

## Intent

Verification is where a hardware engineer spends most of their time (edit → lint →
sim → waveform), yet it is currently the *least* configurable part of SiliconCrew:
one implicit testbench, syntax-only lint, full-flow-only synthesis, and a manifest
that cannot see design files in subdirectories. This package makes the fast loop
first-class while preserving the platform's two invariants:

1. **Manifest is the single source of truth** — it supplies files and targets;
   the user supplies only choices. New capability = new *choices*, never file
   hand-picking. Suggestions everywhere, free entry allowed, closed lists only
   for true enums.
2. **Agent/UI parity, zero drift** — every change lands in the `@tool` wrappers
   (and/or the REST action bodies, which are their own contract), so the agent,
   MCP clients, and the schema-driven Command Surface gain the capability
   simultaneously and identically.

Explicit non-goals (deferred, each its own follow-up): Verilator as a
*simulator* engine, run retention/GC, the structured Spec editor, renaming
`start_synthesis`.

---

## Item 1 — iverilog `-s <top>`: the multi-testbench correctness fix

**Problem.** `src/tools/run_simulation.py` builds
`iverilog -g2012 <includes> -o out -f filelist` with **no `-s` flag**. Without
`-s`, every un-instantiated module becomes a simulation root: with two
testbenches in the workspace, *both* elaborate and run in the same simulation
(two clock generators, interleaved `initial` blocks, garbage results). The
`top_module` parameter is recorded but not enforced at compile time.

**Change.** In `run_simulation.py`, append `"-s", top_module` to the compile
command whenever `top_module` is provided (it already reaches the function —
`sim_manager.py:204` passes it). No signature changes.

**Tests.** Unit: compile command contains `-s <top>` when top given, omits when
empty. Integration (iverilog-gated, follows existing skip pattern): workspace
with two TBs → run with `-s tb_a` → only `tb_a`'s output appears.

**Risk.** Low. Behavior change only for workspaces where multiple roots existed
(which were broken anyway). Single-TB workspaces produce identical results.

---

## Item 2 — Manifest: recursive scan + exclusions + derived testbench list

**Problem A (subdirectories).** `manifest.py` scans the workspace root only
(deliberate: *"nested directories are run artifacts or third-party stdcell
models"*). RTL under `rtl/` gets no role and is invisible to lint/sim/synth.
The fear behind root-only is legitimate — a naive walk would ingest
`synth_runs/` netlists and vendor models as user RTL and wreck top-inference.

**Problem B (testbenches).** `simTop` is a single value. The manifest already
regex-parses `module` declarations per file (`_MODULE_RE`), so it knows enough
to enumerate all testbench tops — it just doesn't surface them.

**Changes** (`src/tools/manifest.py`):
- `_scan_files` → recursive walk (`os.walk`) with an exclusion policy:
  - always skip: `sim_runs/`, `synth_runs/`, dot-dirs, `__pycache__`,
    `node_modules`;
  - user escape hatch: new manifest field `ignore: List[str]` (fnmatch globs
    against workspace-relative paths, e.g. `vendor/**`), editable via
    `update_manifest`/PUT `/manifest`;
  - depth cap (6) as a runaway guard.
- `DesignFile`: `path` becomes the workspace-relative path (with slashes);
  `name` stays the basename for display. At root, `path == name`, so existing
  manifests reconcile without migration.
- Role/tops logic keyed by **path**, not basename. Audit + update every
  consumer that keys roles by name:
  - `src/api/actions.py::_snapshot_files` (roles dict), `_snapshot_code`,
    `_snapshot_spec` — upgrade from `os.listdir` to manifest-driven /
    exclusion-aware walk;
  - `api.py::list_workspace_files` (GET /files) — same, for `/` route parity;
  - `write_manifest` role updates: accept `path` (canonical) and fall back to
    unique-basename matching for backward compatibility.
- New **derived** manifest field `testbenches: List[{file: str, module: str}]`
  — every `role: tb` file with its top module name(s), recomputed on each
  reconcile. NOT user-maintained. `simTop` keeps its meaning as the *default*
  TB (what one-click Simulate runs).

**Frontend ripples.** `DesignManifest` type gains optional `testbenches` +
`ignore`. FileExplorer role badges currently shown for root files keyed by
name → key by path (badges now appear on nested design files too).

**Tests.** Manifest: nested rtl/tb discovery + roles; exclusion of run dirs;
ignore globs; testbenches derivation (two TBs → two entries); reconcile of a
legacy root-only manifest.json is a no-op. Actions: snapshot code/spec include
nested files; roles in `/workbench` snapshot keyed correctly.

**Risk.** Medium — this is the widest-reaching item. Mitigations: exclusion
set + ignore globs + depth cap directly address the original root-only
rationale; top-inference unchanged in input *shape* (still DesignFile list).
Reviewer should specifically check `_infer_tops` and TB-detection heuristics
against nested paths, and hosted-mode tarball size (walk is read-only).

---

## Item 3 — Testbench choice end-to-end

**Facts.** REST `SimulateRequest` already accepts `simTop?` (plumbed to
`run_sim_isolated(top_module=...)`); the agent tool `run_isolated_simulation`
takes `sim_top`. With Item 1, the choice becomes *effective*; with Item 2, the
choices become *enumerable*. So this item is mostly surfacing:

- `lib/commands.ts` sim command: new param `simTop` (editor: combobox — Item 6;
  suggestions = `manifest.testbenches[].module`, default `manifest.simTop`,
  source badge `manifest`). `runCommand("sim")` passes it through the existing
  REST body. ⌘R with no modal keeps running the default TB — the fast path is
  untouched.
- CommandModal/Surface pick the param up automatically (schema/registry-driven).
- Activity/Runs already record `top` per run — no changes needed there.

**Tests.** Vitest: sim defaults include simTop from manifest; command body
carries an overridden TB. E2E (mocked): sim options modal shows TB suggestions;
selecting the non-default TB sends it in POST /simulate.

**Risk.** Low.

---

## Item 4 — Lint engines: `engine: auto | iverilog | verilator`

**Design.** Lint engines differ in what they *catch*, not their interface
(files + includes in → `file:line severity message` out), so one parameter
abstracts them:

- `src/tools/run_linter.py`: add `engine="auto"`.
  - `iverilog`: current behavior (`iverilog -t null -g2012 …`).
  - `verilator`: `verilator --lint-only -Wall -Wno-fatal <includes> <files>`;
    parse `%Warning-CODE:`/`%Error…: file:line[:col]: msg` into the same
    structured diagnostics (plus the warning CODE, e.g. `WIDTH`, `LATCH`,
    carried as a new optional `code` field).
  - `auto`: verilator if `shutil.which("verilator")` else iverilog. Explicitly
    requested-but-missing engine → honest structured error
    (`engine_unavailable`), never a crash.
  - Result gains `engine: <resolved name>` so the UI/activity show which engine
    actually ran.
- Agent tool `linter_tool` gains optional `engine` param (schema-driven UI
  picks it up automatically). REST `POST /lint` gains an optional body
  `{engine?}` (default auto) — currently it takes no body, so this is purely
  additive.
- Lint file set stays `rtl + include` (already excludes TBs — exactly why the
  synthesizable-subset linter is safe here).
- Frontend: `LintDiag` type gains optional `code`; diagnostics UI shows it as a
  small mono chip. Lint command param `engine` appears via the registry.

**Tests.** Parser unit tests on captured verilator output fixtures (warning,
error, multi-line); auto-fallback when which() fails (monkeypatched); REST
lint with engine body + activity row records engine; unavailable-engine error
envelope.

**Risk.** Low-medium. `-Wall` verbosity may need flag tuning
(e.g. `-Wno-DECLFILENAME`) — start minimal, treat flag curation as data, not
architecture. Container availability is env-dependent by design (probed).

---

## Item 5 — `start_synthesis` gains `max_stage` (fast synthesis-only estimate)

**Design.** Mirror `retry_pd`'s existing stage bounds:
- `synthesis_manager.start_synthesis_job(..., max_stage="finish")`, validated
  against the full `PD_STAGE_SEQUENCE` (`constraints…finish`). Threaded into
  the job args → the ORFS worker stops after the target stage.
- `run_meta.json` gains `max_stage`; stages beyond it are marked `skipped`
  (not `pending` — honest terminal state). Job/run status: `completed` when
  the *target* stage completes.
- **Reviewer attention points** (the two places that assume full flow):
  - `_reconcile_stale_status` keys on `6_finish.rpt` existence — must key on
    the target stage's artifact for partial runs;
  - signoff/auto-checks (`auto_checks.signoff`, equiv) expect finish artifacts
    — for partial runs record `"skipped (partial flow)"`, and
    `_build_status_response.next_action` should suggest continuing via
    `retry_pd` (which already validates parent-stage prerequisites, so
    "synth-only now, continue to GDS later" composes with existing lineage for
    free).
- Agent tool `start_synthesis` + REST `SynthesizeRequest` gain optional
  `max_stage`/`maxStage`. Tool description updated to state the default is the
  full RTL→GDS flow and `max_stage="synth"` is the fast estimate. **No rename**
  (breaks architect prompt, historical activity logs, external MCP clients).
- `lib/commands.ts` synth command: `maxStage` enum param (basic, since it's the
  headline use case), default `finish`.

**Tests.** Manager unit: max_stage validation; run_meta carries it; stage map
marks skipped; reconcile of a partial run doesn't mis-mark failed. REST:
synthesize with maxStage dispatches (mocked manager). Registry/UI: param
appears; PPA from a synth-only run renders (metrics parser already reads
`synth_stat.txt`; WNS may be synth-estimate — reviewer: confirm
`get_synthesis_metrics` degrades gracefully without finish reports).

**Risk.** Medium — touches the most complex manager. Contained by mirroring
the retry path's existing stage semantics.

---

## Item 6 — Frontend: searchable combobox for file/module params + explorer "New file"

**Combobox editor** (the "search ≻ suggest ≻ type anything" model):
- New editor kind `"combo"` in the surface param model: cmdk-style input with
  a filtered suggestion dropdown; **free entry always allowed**; suggestion
  rows can carry a subtitle (e.g. TB module → its file).
- `lib/schemaForm.ts` conventions upgrade from closed `enum` to `combo` for
  every *string* param whose options come from conventions (`vcd_file`,
  `verilog_file`, `sby_file`, `dslx_file`, `filename`, `file_path`,
  `spec_file`), plus new conventions: `sim_top` → `manifest.testbenches`
  modules; `top_module` → synthTop + all known modules. True enums from
  schemas (platform, stages, mode, generator) stay closed.
- Suggestion source for generic paths: the quick-open path index (already
  fetched/cached).
- `run_id`-family params stay closed enums (runs are a closed set — honesty).

**Explorer "New file":**
- Header `+` button and dir context-menu entry → inline name input (supports
  `sub/dir/name.v`); creates via the existing save path
  (`PUT /code/{path}` → `file_ops.write_file`, which already `makedirs`
  parents and re-reconciles manifest roles). New folders exist implicitly with
  their first file (git-style; no mkdir endpoint).
- After create: invalidate affected dir caches, open the file in a code tab.
- Depends on Item 2 for the new file to receive a role when nested.

**Tests.** Vitest: combo param mapping conventions; free-entry value flows to
payload; explorer create action calls saveCodeFile with nested path +
invalidates dirs. E2E: TB picker suggestion flow (Item 3's test); new-file
creation opens a tab.

**Risk.** Low. Combobox replaces dropdowns only where free entry is *more*
honest, not less.

---

## Sequencing, verification, compatibility

**Order.** 1 → 2 → 3/4/5 in parallel (independent) → 6. Items 1–5 backend-first
with pytest at each step; the schema-driven surface picks up new params
automatically, so 6 is the only bespoke frontend work beyond small type
additions.

**Gates per item and final:** backend pytest (new + the 81-test regression
sweep), `tsc`, vitest, full Playwright suite; final adversarial review pass
over the whole diff before push.

**Compatibility.**
- All new tool/REST parameters are optional with today's behavior as default —
  agent prompts, MCP clients, and existing sessions keep working unchanged.
- Legacy root-only `manifest.json` reconciles in place (path==name at root);
  `ignore`/`testbenches` default empty/derived.
- No tool renames; no changes to run/activity data shapes beyond additive
  fields (`code` on LintDiag, `max_stage` on run meta).

**Open questions for the reviewer.**
1. Item 2: any consumer of `DesignFile.name`-as-key I haven't listed (grep
   `role` overlays, e2e mocks, bench-orchestrator/cvdp pipelines)?
2. Item 5: exact mechanism by which the ORFS worker bounds stages (make target
   vs. stage loop) — confirm the stop-after-stage point and the artifacts the
   stale-status reconciler should key on for each possible `max_stage`.
3. Item 4: verilator presence in the shipped Docker images (`Dockerfile`,
   `Dockerfile.sby`) — if absent, decide whether to add it to the image or
   ship probe-only.
4. Item 2: `files_for_stage("simulate")` returns *all* TB files — with `-s`
   this is correct (unchosen TBs are dead code), but confirm no TB-file name
   collisions break the iverilog filelist.

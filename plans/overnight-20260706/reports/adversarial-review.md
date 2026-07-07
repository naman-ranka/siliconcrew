# Adversarial review — tonight's code diff

Scope: code commits on `claude/overnight-showcase` (`608864e..HEAD`, plus the
tonight-shipping perf commit `f095fcb` F2 which predates the branch point but
deploys with HEAD). Backend + frontend only; `examples/` bundle data and docs
out of scope. Method: code-reading + path-tracing only (no live probing, per
owner constraint). Each finding was traced to the exact state/inputs that break
it before reporting.

**Verdict: 2 real defects (both MEDIUM, self-host / UI-liveness), no CRITICAL.**
All three explicitly-flagged concerns pressure-tested; one confirmed (= Finding
2), two confirmed SAFE with the enumeration shown.

---

## Finding 1 — MED: docker-engine wall timeout does not stop the container

**File:** `src/tools/run_python.py` — `_run_argv` (timeout branch) + `_kill`;
`build_docker_argv` (no container name).

`run_python_analysis` is `python_engine="docker"` by default, and docker is the
self-host default (`settings.py`: `_env("PYTHON_ENGINE", "native" if hosted else
"docker")`). In docker mode the 30s wall-timeout kill is ineffective:

- `_run_argv` runs `docker run` in the foreground; on `subprocess.TimeoutExpired`
  it calls `_kill(proc)` → `os.killpg(os.getpgid(proc.pid), SIGKILL)`. That kills
  the **docker CLI client**, not the container. `dockerd` owns the container; a
  SIGKILL to the foreground client gives it no chance to forward a stop, so the
  container keeps running.
- `build_docker_argv` sets `--rm` but **no `--name`/label**, so nothing can
  `docker kill` the orphan afterward. `--rm` only fires when the container exits
  on its own.

**Concrete failure:** an agent writes `loop.py` containing `while True: pass` and
calls `run_python_analysis("loop.py")`. At 30s the tool returns
`{"timed_out": true, ...}`, but the orphaned container keeps spinning at
`--cpus 1` / `--memory 1g` **indefinitely** (until the host is rebooted or an
operator manually `docker ps` + `docker kill`s it). The "30s accident gate" the
docstring promises is unenforced in the engine that ships by default. (Native
mode is fine — POSIX `setrlimit(RLIMIT_CPU)` + `os.setsid()` + `killpg` on the
real process group all work.)

**Fix:** name the container (`--name sc_py_<uid>`), and on timeout run
`docker kill sc_py_<uid>` (or pass `--stop-timeout`/run detached with a tracked
id) before letting `--rm` clean up.

---

## Finding 2 — MED (invariant 4/7): X2A-4 refresh wiring amplifies unguarded
## SWR blanking in `loadManifest`/`loadRuns`

**File:** `frontend/lib/store.ts` — new schedulers `scheduleManifestRefresh`
(≈285) / `scheduleRunsRefresh` (≈294), WS-frame trigger (≈1157-1160), done-handler
(≈1189-1190); target fns `loadManifest` (≈1864) and `loadRuns` (≈1913).

The X2A-4 change makes the agent-shell Index reload `manifest` + `runs` off live
WS tool frames (debounced 1200ms) **and** unconditionally in the turn-`done`
handler. Both target functions have two SWR weaknesses that `loadThreads` (≈1345)
deliberately avoids:

1. **No post-await stale-session guard.** `loadManifest` does `set({ manifest })`
   after `await getManifest(currentSession.id)` with no
   `if (get().currentSession?.id !== sid) return;`. `loadRuns` likewise
   `set({ runs })` + `detectRunTransitions(sid, …)` after its await. `loadThreads`
   captures `sid` and re-checks it after the await — the pattern is known here,
   just not applied to these two.
2. **Blank-on-error.** `loadManifest` `catch { set({ manifest: null }) }`;
   `loadRuns` `catch { set({ runs: [] }) }`. Violates the "populated data never
   blanks" iron rule (invariant 4/7).

Before tonight these fired rarely (session load / explicit Refresh); now they fire
repeatedly during a *live* turn — and the documented scenario is exactly a
headless turn continuing while the user switches sessions (explore2-agent
root-cause).

**Concrete failures:**
- (a) A transient 500 on the manifest endpoint during a `write_file` burst flips
  `manifest` to `null` mid-turn → the agent Index / file tree flashes empty until
  the next refresh. Same for `runs → []`.
- (b) User on session A (A's turn streaming headless), switches to B. A late
  debounced `loadManifest` started while `currentSession` was still A resolves
  after the switch and does `set({ manifest })` with **A's** manifest while B is
  displayed; `loadRuns` cross-writes A's runs into B and
  `detectRunTransitions(A, …)` announces A's transitions against B (spurious
  unread markers / toasts).

**Fix:** capture `sid` and add the `loadThreads`-style post-await guard to both;
drop the `null`/`[]` blanking on error (keep prior data, set a soft error flag).

---

## Flagged item 1 (store.ts X2A-4 loadManifest cross-write) — CONFIRMED

Confirmed real (= Finding 2). `loadManifest` sets `manifest` unconditionally on
resolve with no session re-check. `loadRuns` was described as "reportedly has the
stale guard" — that is **not accurate**: `loadRuns` is single-flighted
(`singleFlight("runs:<sid>:<filter>")`) but has NO post-await session guard either,
and blanks to `[]` on error. Both need the fix.

## Flagged item 2 (F2 sync gated to MUTATING_TOOLS — any writer missing?) — CONFIRMED SAFE

Enumerated every tool in the LangChain registry (`TOOL_CATEGORIES` +
`mcp_tools`) against `MUTATING_TOOLS` (`tool_catalog.py:88`). Every workspace
*writer* is a member. The non-members were each checked for durable workspace
writes:

| Tool | In MUTATING_TOOLS? | Writes durable workspace artifact? |
|------|--------------------|-------------------------------------|
| write_spec, write_file, apply_patch_tool, edit_file_tool, load_yaml_spec_file, update_manifest | yes | yes ✓ |
| simulation_tool, run_isolated_simulation, cocotb_tool, sby_tool | yes | yes (run dirs / VCD) ✓ |
| start_synthesis, retry_pd | yes | yes ✓ |
| save_metrics_tool, generate_report_tool, schematic_tool | yes | yes ✓ |
| run_python_analysis, all hls tools | yes | yes ✓ |
| **linter_tool** | no | **no** — `run_linter` uses `iverilog -t null` (no output) / `verilator --lint-only` (no output); result returned as text (`run_linter.py:172,179`) |
| **waveform_tool** | no | **no** — `read_waveform` returns signal values as text (`wrappers.py:447`); reads the VCD, writes nothing |
| get_synthesis_status, wait_for_synthesis, get_synthesis_metrics, read_stage_report, get_route_drc_summary, get_cts_summary, get_congestion_summary, compare_pd_runs, search_logs_tool | no | no (pure readers). Status readers reconcile `run_meta`, which persists via its OWN durable channel (`_persist_run_meta_durable` → run store), independent of the workspace tarball — documented in the dispatch comment (`mcp_server.py:912-923`) |
| read_spec, read_file, get_manifest, list_files_tool | no | no (readers) |

No writer is missing from `MUTATING_TOOLS`. The only accepted exposure (stated in
the commit + code comment) is a tail of pure-read `attempt_events.jsonl` appends
that ride the next mutating call's sync — bounded, not silent. **Safe.**

## Flagged item 3 (design_report fail-dominant legacy + sim_runs read path) — CONFIRMED SAFE

`src/tools/design_report.py:_simulation_status_cell`:
- Primary path reads `list_sim_runs` (authoritative, newest-first) and reports the
  latest verdict; any non-`passed` status maps to ❌ Fail (honest — isolated sims
  are terminal, never "running", so no live-state is mislabeled).
- Legacy fallback (`.out`/`simulation.log` scan) is fail-dominant: once any file's
  content contains `"fail"`, `sim_passed` sticks `False` (the `elif … pass` only
  promotes to `True` when still `None`). This can mark a genuinely-passing legacy
  log that contains the substring `"0 failures"` as Fail — but that is the
  **intended, honest direction** (a false Pass is the dishonest one, X2A-2), and
  it only applies to pre-isolated-runs sessions. No path lets a failing/zero-pass
  result read as Pass. **Safe.**

---

## Verified safe (checked, not defects)

- **`stateless=True` (mcp_server.py:1155 / api.py:439):** no handler uses
  server→client features stateless disables (grep: no `send_notification` /
  `send_log` / sampling / `elicit`). The F1 pre-dispatch owner gate reads
  `self.server.request_context.request.state`, set per-request by the transport
  independent of the session's stateless flag — gate intact. First-connect
  `initialize` is still handled. Mirrors the SDK's own
  `StreamableHTTPSessionManager`.
- **Schematic hosted gate (`wrappers.py:764`):** returns early only when
  `hosted`; self-host falls through unshadowed.
- **`run_python` containment (`run_python.py`):** `is_within` realpaths both sides
  (symlink/`..`-safe); hosted gate is at the wrapper entry so agent/MCP/`/invoke`
  are all covered; core fn is only reachable via the gated wrapper in production.
- **`base_env` plumbing (`tool_engine.py`):** only cocotb passes it; xls/sby call
  `.run()` with `base_env=None` → unchanged `os.environ` inherit. Default-None
  invariant holds.
- **Failure plumbing:** `current_stage`/`check_notes` are genuinely written across
  `synthesis_manager.py` (not dead). `passMarker` legacy fallback
  (`sim_manager` `… or pass_marker`; RunsPane `?? "TEST PASSED"`) handles old
  `run_meta` lacking the field.
- **ImageArtifact.tsx** blob-URL lifecycle is correct (revoke on unmount/path
  change + `cancelled` guard; SVG via `<img>`, never inline HTML).
- **F5 DialogTitle (`CommandPalette.tsx`):** `sr-only` Dialog.Title inside the
  cmdk Radix Dialog satisfies the a11y requirement without layout change.

## Minor notes (not blocking)

- **Native cocotb env scrub (`run_cocotb.py:_COCOTB_ENV_KEEP`)** drops
  `PYTHONPATH`/`LD_LIBRARY_PATH`/`VIRTUAL_ENV`/`CONDA_PREFIX`. PATH is kept so
  venv binaries + `iverilog` resolve and cocotb finds its GPI libs via its
  package — likely fine, but untestable in CI (cocotb is a known env-gap) and
  could bite a machine that relied on an inherited `LD_LIBRARY_PATH`. Worth a
  keep-list entry if a real self-host cocotb run regresses.
- **ReportArtifact.tsx** failure panel hardcodes "Synthesis failed …"; only
  reachable for `report:<runId>` (synth-only in practice), so cosmetic.
- **RunsPane.tsx `failureReason`** returns `null` for a synth failure with no
  `checkNotes`; the `@ <stage>` still renders, so not silent.

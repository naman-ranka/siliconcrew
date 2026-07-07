# Python analysis wave — backend

Branch `claude/overnight-showcase`. Backend portion of
`plans/python-analysis-and-artifacts.md` (Amendments PA1–PA12 authoritative).
Two commits, per-item, pushed. Baseline backend gate = exactly 9 known failures;
after every item still exactly 9 (zero new).

File fence honored: touched only `src/tools/run_python.py` (new),
`src/tools/wrappers.py`, `src/tools/run_cocotb.py`,
`src/platform_engines/{settings,identity,tool_engine}.py`,
`src/api/tool_catalog.py`, `Dockerfile.python-analysis` (new), and test files.
NOT touched (excluded): `mcp_server.py`, `api.py`, `src/api/actions.py`,
`run_simulation.py`, `sim_manager.py`, `synthesis_manager.py`, and all frontend.

---

## Commit 1 — `feat(analysis): run_python_analysis bespoke gated subprocess + PYTHON gate` (cb5f9c4)

### Item 1 — the tool (`src/tools/run_python.py` + wrapper)
`run_python_analysis(script_file, args)` — runs a WORKSPACE FILE (not inline
code) as an isolated subprocess; returns
`{ok, exit_code, timed_out, duration_sec, engine, stdout_tail, stderr_tail, artifacts}`.

- **PA1 — bespoke subprocess, NOT the engine seam.** It does not route through
  `NativeToolEngine` (merges `{**os.environ,…}` — can only ADD, never scrub) nor
  `run_docker_command` (no isolation flags). Native path: `python -I` via
  `sys.executable`, `cwd=workspace`, an explicit **scrubbed** `env` dict
  (`PATH`/`HOME`/`LANG`/`MPLBACKEND=Agg`/`MPLCONFIGDIR`(a workspace dot-dir so
  the mpl cache is invisible to the artifact scan)/`PYTHONDONTWRITEBYTECODE`,
  plus Windows-only system vars so the interpreter can start) — NEVER the backend
  process env. POSIX `preexec_fn` sets RLIMIT_CPU/AS/FSIZE/NPROC + `os.setsid`;
  30s wall timeout; process-group kill (or `proc.kill()` on Windows).
- **PA2 — bespoke `docker run` with real isolation.** `build_docker_argv` (pure,
  unit-tested) emits `--network=none --user 1000:1000 --memory 1g
  --memory-swap 1g --cpus 1 --pids-limit 64 --read-only --tmpfs
  /tmp:rw,size=256m` + a single `-v <ws>:/workspace:rw` routed through
  `_translate_dood_volume` for docker-outside-docker, `-w /workspace`,
  `-e HOME=/tmp -e MPLBACKEND=Agg -e MPLCONFIGDIR=/tmp/.matplotlib`, then
  `python -I /workspace/<rel> <args>`. Args are argv (no shell → no injection).
- **PA5 — containment in the tool itself.** `is_within(workspace, script_file)`
  (realpath/symlink-safe) is called by `run_python_analysis` directly, because
  `enforce_file_containment` auto-runs ONLY on `/invoke`, not on the agent/MCP
  paths. (On `/invoke` it ALSO fires — `script_file` ends with `_file` — so that
  path gets belt-and-suspenders containment.)
- **PA6 — artifact scan.** Post-run scan via `manifest.iter_workspace_files`
  (the shared policy: excludes `sim_runs`/`synth_runs`/`orfs_*`/`results`/
  `__pycache__`/`node_modules`/dot-dirs, depth 6) for files with `mtime >=`
  run-start; the input script is excluded (it is the input, not an output). Each
  artifact carries `{path, kind, bytes}`; `kind` is image/data/text/vector/file
  by extension.
- **PA12 — pinned image.** `Dockerfile.python-analysis`: `python:3.12-slim` +
  numpy 2.1.3 + matplotlib 3.9.2 + pyyaml 6.0.2 + vcdvcd 2.3.5, non-root, no
  runtime pip. **BUILT and VERIFIED** locally (`siliconcrew/python-analysis:1`,
  405 MB) — a real docker-engine run produced `out.csv`+`plot.png` under
  `--network=none --read-only`. Pinned via the `python_image` setting
  (`PYTHON_ANALYSIS_IMAGE`, default `siliconcrew/python-analysis:1`). Note: the
  image lives in the LOCAL docker daemon only; it is not pushed to a registry, so
  a fresh machine must `docker build -t siliconcrew/python-analysis:1 - <
  Dockerfile.python-analysis` (or use `PYTHON_ENGINE=native`).
- **Engine selection.** `python_engine` setting mirrors `sim_engine` (docker
  local, native hosted — though hosted is gated off). Docker-preferred with a
  native fallback when the docker CLI is absent (`resolve_engine`).

### Item 2 — capability gate (PA3/PA4)
- `Action.PYTHON` added to `identity.py`, NOT in `ANONYMOUS_ALLOWED` (defense in
  depth).
- **The load-bearing switch is `get_settings().hosted` checked INSIDE the
  wrapper** — `authorize()` only distinguishes anonymous, so a signed-in hosted
  user would pass any Action. Placing the check at the wrapper entry covers
  agent / MCP / REST `/invoke` by construction (all execute the same func).
  Verified: on hosted, both `.invoke(...)` and `validate_and_execute(...)`
  (`/invoke`) return "Python analysis runs locally … not available on the hosted
  platform yet"; self-host runs the script.
- Registered in the ONE registry (invariant 2): `tool_catalog` new `analysis`
  category, `PROTECTED_TOOLS` + `MUTATING_TOOLS`; added to `mcp_tools` /
  `architect_tools`. Kept out of the essential/minimal set.

### Tests (Item 6 backend list) — all pass
`tests/test_run_python_analysis.py` (13 pass, 1 skip): containment (`../` +
absolute + missing), execution + artifact scan (+ run-dir exclusion + input-
script exclusion), args passthrough, timeout kill, env-scrub (child can't read a
planted secret; scrubbed env excludes arbitrary host vars), docker argv shape
(`--network=none` etc.) + DooD volume translation, engine fallback, rlimits
applied (POSIX; skipped on this Windows container). `tests/test_python_analysis_gate.py`
(3 pass): hosted unavailable / self-host runs / `Action.PYTHON` not anonymous.

### Excluded-file refinements (PA4) — documented, NOT applied (fence)
The wrapper-internal `settings.hosted` check already covers every path, so these
are message-quality refinements, not correctness gaps:
- `mcp_server.py:~879` ternary: `Action.SYNTHESIZE if name in
  TOOL_CATEGORIES["synthesis"] else Action.SAVE` → add `Action.PYTHON if name in
  TOOL_CATEGORIES["analysis"]` so the MCP authz message is PYTHON-specific.
  (Today it maps to SAVE, which still blocks anonymous and still lets the wrapper
  reject hosted — functionally correct.)
- `src/api/actions.py` `/invoke`: it checks only `flags["requiresSignIn"] and
  identity.anonymous`; a hosted-aware reject could short-circuit with the same
  "runs locally" message before execution. Not required — the wrapper returns it
  anyway.

---

## Commit 2 — `feat(analysis): scrub backend env from the native cocotb subprocess (Item 3)` (4c62d30)

`cocotb_tool` runs the agent's own Python; its native path went through
`NativeToolEngine.run`, which merged the full backend `os.environ` (API keys, DB
URLs, WorkOS/GCP creds) into the child — the exact hole `run_python_analysis`
was built to avoid. The docker path already isolates (clean image env + only
explicit `-e` vars), so this is native-only.

- `tool_engine.py`: added an opt-in keyword-only `base_env` to `ToolEngine.run`.
  When provided, `NativeToolEngine` uses it as the base instead of `os.environ`
  (`{**base_env, **env}`); default `None` preserves today's behavior for
  xls/sby (they run tool binaries, not user scripts).
  `DockerToolEngine` accepts it for interface parity (no-op).
- `run_cocotb.py`: passes a scrubbed `base_env` (`PATH`/`HOME`/`LANG` +
  toolchain-essential system vars only); `SC_*` runner vars still layer on top.
- Tests `tests/test_cocotb_env_scrub.py` (3 pass): native engine uses `base_env`
  not `os.environ` (and default still inherits, so xls/sby unchanged);
  `run_cocotb` passes a scrubbed base that drops a planted secret. Updated the
  existing `FakeEngine.run` signature in `test_cocotb_engine.py` for the new
  kwarg (the only pre-existing test the interface change touched).

Note on rlimits: Item 3's text says "same env-scrub + rlimits". I implemented the
**env-scrub** (the security-load-bearing part the plan's test names, and the
hole that undermines the new gate) but not rlimits on the cocotb native path —
adding a `preexec_fn` to the shared `NativeToolEngine` would also affect xls/sby
and risks false-killing legitimate long EDA runs. Recommend a follow-up if cocotb
native rlimits are wanted; it should be opt-in per-caller like `base_env`.

---

## Deferred (honest)

- **Item 4 — backend artifact metadata (`/file`,`/dir` kind/MIME, PA11).**
  Deferred deliberately. Its consumers are the frontend viewers (PA7/PA8) which
  are owned by another lane tonight and EXCLUDED here; the field-name contract
  must match theirs, so shipping a guessed contract risks cross-lane conflict.
  It also delivers little standalone value tonight: `run_python_analysis` already
  returns per-artifact `kind` in its own result, so the tool card renders
  "Open artifact →" without any `/file` change. **Exact minimal diff when the
  frontend lane is ready** (all in-scope, no excluded-file edits needed — the
  consumers pass the dicts straight through):
  - `workspace_fs.read_smart_file`: add `"kind"` (image/data/text/vector/file via
    the same extension map as `run_python.py:_KIND_BY_EXT`) + `"mime"`; the
    payload is returned verbatim at `api.py:2406`, so it flows through with no
    api.py edit.
  - `workspace_fs.list_dir`: add a NEW `"artifactKind"` field to file entries
    (do NOT overwrite the existing structural `"kind": "dir"|"file"`, which the
    explorer's sort depends on).
  Reuse the null-byte sniff already in `read_smart_file` for binary detection.
- **All frontend items (PA7 viewers, PA8 ArtifactKind union, PA9 toolArtifacts,
  PA10 FILE_KEYS convention).** Owned by the frontend lane. `run_python_analysis`
  is registered with an `args_schema` (`script_file` + `args`) so the schema-
  driven Command Surface renders a form for free; PA10 would upgrade `script_file`
  to a workspace-file combo.
- Hosted Python via the ORFS isolated-job seam (plan Deferred).

## Gates
- New suites: `test_run_python_analysis.py` 13 pass/1 skip;
  `test_python_analysis_gate.py` 3 pass; `test_cocotb_env_scrub.py` 3 pass.
- Full backend gate (standard ignores): **9 failed, 714 passed, 9 skipped** —
  the exact known baseline (congestion x2, lint norm_file, llm_factory, orfs_job
  stage_in, perf_read_no_sync, sby_engine, xls x2). Zero new. (One transient
  `test_llm_keys` failure was chased down to FIXTURE POLLUTION from repeated
  suite runs on a dirty tree — it passes on a freshly-restored tree; not related
  to this wave.)
- `git checkout -- tests/fixtures/ test_sby_output.txt` run after suites.
- Docker image `siliconcrew/python-analysis:1` builds and runs (verified).

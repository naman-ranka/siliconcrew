# Wave 10 — Python analysis tool + rich artifact viewing

Status: ACCEPTED w/ amendments (2nd-agent review folded in below; then
normal-agent implementation + my adversarial pass)
Supersedes the intent doc plans/python-analysis-artifacts.md (that stays as the "why").

## Amendments from 2nd-agent review (AUTHORITATIVE over the body where they conflict)

Several "reuse existing X" claims in the body are wrong at the code level.
Net effect: the tool is a **bespoke gated subprocess**, not a ride on the
existing tool-engine seam. Still bounded (~one new module), but not the
one-liner the body implied.

- **PA1 (env-scrub → bespoke subprocess, not the engine seam):**
  `NativeToolEngine.run` merges `{**os.environ, **env}` (tool_engine.py:110)
  and is shared by xls/sby/cocotb — you can ADD keys there, never REMOVE
  os.environ. So `run_python_analysis` must NOT route through
  NativeToolEngine/DockerToolEngine; it builds its own `subprocess.Popen`
  with an explicit scrubbed `env=` dict + POSIX `preexec_fn` rlimits. This
  is the single most important correction and it cascades into PA2.
- **PA2 (docker isolation flags don't exist on the helper):**
  `run_docker_command` (run_docker.py:43,95-113) hardcodes `docker run --rm
  [-v ws] [-e] -w cwd image bash -c` — NO `--network/--user/--memory/--cpus/
  --pids-limit/--read-only/tmpfs`. The docker engine must be a bespoke
  `docker run` invocation (or an extended helper) that adds those flags AND
  routes every bespoke `-v` through `_translate_dood_volume`
  (run_docker.py:9-40) for docker-outside-docker. Don't claim "reuse
  run_docker_command" as-is.
- **PA3 (hosted gate is settings.hosted, NOT the Action enum):**
  `authorize()` (identity.py:60-70) only knows anonymous vs
  ANONYMOUS_ALLOWED — a signed-in HOSTED user passes any Action. So adding
  `Action.PYTHON` gates anonymous, not hosted. The "hosted OFF" switch must
  consult `get_settings().hosted` EXPLICITLY at the gate. Keep
  `Action.PYTHON` out of ANONYMOUS_ALLOWED too (defense in depth), but the
  load-bearing check is `if settings.hosted: reject`.
- **PA4 (gate sites — the /invoke path has NO authorize() today):**
  `authorize(...)` is called at exactly ONE site (mcp_server.py:799-803
  ternary). REST `/invoke` (actions.py:746-763) only checks
  `flags["requiresSignIn"] and identity.anonymous` — it cannot express
  "hosted-unavailable". So the PYTHON gate is NET-NEW logic at: (a)
  mcp_server.py:801 (extend the ternary, else PYTHON→SAVE); (b)
  actions.py /invoke (add a hosted-aware reject); (c) the wrapper entry
  itself (agent path has no authorize gate at all) — put the
  `settings.hosted` check INSIDE `run_python_analysis` so every path
  (agent/MCP/REST) is covered by construction. Self-host: `authenticate`
  returns LOCAL_IDENTITY when `not settings.hosted` (auth.py:131-132) →
  never anonymous → allowed.
- **PA5 (containment is auto ONLY on /invoke):** `enforce_file_containment`
  (tool_catalog.py:197-206) runs only inside `validate_and_execute`
  (:219) — the MCP (mcp_server.py:834) and agent paths never call it. So
  `run_python_analysis` must call containment on `script_file` ITSELF
  (realpath/symlink-safe via paths.py is_within; `script_file` matches
  `_FILE_ARG_KEYS`). Don't rely on the catalog for it.
- **PA6 (artifact scan — reuse the MANIFEST iterator/excludes):** no
  existing tool does a "mtime ≥ start" scan (existing ones sort newest).
  Reuse `manifest.iter_workspace_files` + `_IGNORED_DIRS` (manifest.py:36-39
  = synth_runs/sim_runs/orfs_*/results/__pycache__/node_modules + dotdirs,
  depth 6) — NOT the smaller `workspace_fs._EXCLUDED_DIRS`.
- **PA7 (image needs a blob URL, not the download URL):** `/file?raw=1`
  (api.py:2083) requires a Bearer HEADER; `downloadRawFile` force-downloads
  and returns nothing renderable. ImageArtifact needs a NEW helper:
  fetch raw with authHeader → `blob()` → `URL.createObjectURL` → revoke on
  unmount. "reuse the download URL as <img src>" would 401/download.
- **PA8 (ArtifactKind is a closed union → 4 edit sites):** adding
  image/data/text requires editing ALL of: the `ArtifactKind` union
  (types/index.ts:316), `KIND_ICON` (ArtifactCenter.tsx:29-36), the
  no-default `ArtifactBody` switch (:46-59), and `REF_KINDS`
  (artifactKeys.ts:14-20) — or tsc breaks / parseArtifactKey returns null.
- **PA9 (toolArtifacts is single-key, string-only):**
  `artifactKeyForToolCall` (toolArtifacts.ts:58) gets `(name,args,
  resultText:string)` and returns ONE key — it never sees the structured
  artifacts array. The mapping must parse artifacts out of the result JSON;
  "card lists multiple artifacts" is a NEW multi-artifact card shape in
  ToolCallCard, not supported today. Scope it or ship single-primary-artifact
  first.
- **PA10 (FILE_KEYS doesn't exist):** schemaForm has RUN_ID_KEYS/
  MANIFEST_KEYS/BASIC_KEYS only; `*_file` params render as plain text. Add
  a FILE_KEYS set + a `conventionOptions` branch returning workspace files
  so `script_file` gets a file combo.
- **PA11 (Item 4 is net-new fields):** `read_smart_file`/`list_dir` return
  no kind/MIME — the plan ADDS those fields to `/file`,`/dir` (reusing the
  null-byte sniff is fine).
- **PA12 (docker image is net-new):** numpy/matplotlib/pyyaml/vcdvcd are
  already in requirements + the app image (native mode ready), but there is
  NO small pinned python-analysis image — the docker engine needs a new
  image/Dockerfile layer.

## Intent (locked)

A workspace-scoped Python analysis tool for small engineering-support jobs
(golden vectors, .mem/.hex/.csv generation, fixed-point/CRC/DSP checks,
plotting sim outputs), plus richer artifact viewing so generated files are
first-class evidence in the IDE. NOT a cocotb replacement, NOT a REPL/notebook,
NOT unrestricted shell.

## Decisions (locked; see plan header for defaults chosen)

- **Hosted: gated OFF** this wave via a new `Action.PYTHON` capability (hosted
  returns a clean "not available on hosted yet"; local/self-host gets it).
  Hosted lands later through the existing ORFS isolated-job seam — DEFERRED.
- **Local exec: Docker-preferred, native fallback.** A `python_engine`
  setting mirroring `sim_engine` (`settings.py:45-48,171`): `"docker"` →
  run through the existing `run_docker_command` with `--network=none`,
  workspace-only mount, non-root, mem/cpu caps (REAL isolation, no new
  sandbox); `"native"` → host `python -I` with the accident-gates below.
- **Gate philosophy:** accident-gates always on (cheap, cover ~95% of real
  need); malice-isolation comes free from Docker when present, and is
  honestly absent in native mode (documented: "native mode trusts your own
  machine, like running any script yourself").

## Item 1 — The tool (`src/tools/run_python.py` + wrapper)

`run_python_analysis(script_file: str, args: list[str] = []) -> str`

- **Script is a WORKSPACE FILE** (not an inline code param): reproducible —
  the run records exactly what executed; agents `write_file` the script
  first (they already do this well). Reject inline-code requests by shape.
- Resolve `script_file` through the platform's existing
  `enforce_file_containment` (realpath-based; already used for every file
  arg) — no `../` escape, must be inside the workspace.
- **Accident-gates (always on, both engines):**
  - 30s wall timeout (`subprocess` timeout — same pattern as EDA tools).
  - `cwd = workspace` (SessionContext).
  - `resource.setrlimit` in a POSIX `preexec_fn` (native) / container limits
    (docker): CPU seconds (~30), RSS (~1GB), file size (~256MB), NPROC
    (~64) — kills forkbombs, memory hogs, disk-fillers.
  - **Scrubbed env** — the child gets a minimal explicit env dict
    (PATH, HOME=workspace, LANG, MPLBACKEND=Agg, PYTHONDONTWRITEBYTECODE),
    NEVER the backend process env (which holds API keys / DB URLs). This is
    the single most important native gate.
  - `python -I` isolated mode (native): ignores PYTHON* env, no user site,
    no cwd on sys.path implicitly beyond the script's dir.
  - stdout/stderr tail caps (existing pattern).
- **Docker engine:** `--network=none`, `-v <workspace>:/workspace:rw` only,
  `--user` non-root, `--memory`/`--cpus`, `--pids-limit`, `--read-only`
  rootfs with a writable `/workspace` + tmpfs `/tmp`. Image: a small pinned
  `python:3.x-slim` + numpy + matplotlib + pyyaml + vcdvcd baked in
  (Dockerfile addition; NO pip at runtime). Reuse `run_docker_command`.
- **Pinned libs, no installs:** stdlib + numpy + matplotlib + pyyaml +
  vcdvcd (all already deps). No network in docker mode = installs
  impossible by construction; native mode documents "no pip" as policy +
  scrubbed PATH.
- **Result payload:** `{ ok, exit_code, stdout_tail, stderr_tail,
  duration_sec, engine, artifacts: [{path, kind, bytes}] }` — `artifacts`
  from a post-run mtime scan of the workspace (files with mtime ≥ run start,
  excluding the usual sim_runs/synth_runs/dot-dirs). This is what makes the
  tool card render "Open artifact →".
- **Catalog wiring:** register in `tool_catalog.py` TOOL_CATEGORIES under a
  new "analysis" category; MUTATING (writes files → workspace sync); NOT in
  the minimal/essential set (keep it out of the way of simple RTL flows);
  PROTECTED + new `Action.PYTHON` capability; add to `mcp_tools` +
  `architect_tools`. Schema-driven Command Surface form comes free (Wave 6);
  the `script_file` param uses the file-combo convention (schemaForm
  RUN_ID_KEYS-style; add a FILE_KEYS convention if not present).

## Item 2 — Capability gate (`src/platform_engines/identity.py` + authz)

- Add `Action.PYTHON = "python"` to the enum; NOT in `ANONYMOUS_ALLOWED`.
- Hosted (`is_hosted`) → the tool/endpoint authorizes PYTHON as unavailable
  with an actionable message ("Python analysis runs locally; not yet
  available on the hosted platform"). Self-host (uid None) → allowed.
- Mirror the check at BOTH the wrapper entry (agent/MCP path) and the
  `/invoke` REST path, exactly like SYNTHESIZE gating.

## Item 3 — Consistent posture for cocotb (no theater)

`cocotb_tool` already runs user Python via the docker/native `sim_engine`
seam. Apply the SAME env-scrub + rlimits to its native path so the new
gate isn't undermined by an existing hole. (Docker path already isolates.)
Small, surgical; add a regression test that the cocotb native subprocess
gets the scrubbed env.

## Item 4 — Backend artifact metadata (`src/api/workspace_fs.py` + actions)

- Extend the file-kind/MIME detection so `/file` and `/dir` responses carry
  an honest `kind` for the new artifact families: image
  (png/jpg/jpeg/webp/gif/svg), data (csv/tsv/json/yaml), vector/mem
  (hex/mem/coe/bin → metadata+download), text (txt/log/rpt/md). Reuse
  `read_smart_file`'s null-byte sniff for binary detection; images/binaries
  return metadata + a download URL, never inlined text.
- Artifact cache-control already terminal-immutable — reuse.

## Item 5 — Artifact key + viewers (frontend)

- `artifactKeys.ts`: add kinds `image`, `data`, `text` (keep existing
  code/spec/wave/report/layout/schematic). Key shape `image:<path>` etc.,
  parsed like `code:<path>`.
- `toolArtifacts.ts`: `run_python_analysis` → map its reported artifacts to
  keys (first image → `image:`, else first data → `data:`, else the script
  → `code:`); the tool card's "Open artifact →" uses it. Multiple artifacts
  → the card lists them (small, like the runs index rows).
- New viewers under `components/workbench/viewers/`:
  - `ImageArtifact` — `<img>` from the raw-file download URL; fit/contain,
    checkerboard bg, download button. SVG via the same (sanitized: render as
    `<img src=blob>` not `dangerouslySetInnerHTML`).
  - `DataArtifact` — CSV/TSV → virtualized table (reuse @tanstack/react-
    virtual already in deps); JSON/YAML → collapsible tree (or a pretty
    monospace fallback). Row/col caps with "showing N of M".
  - `TextArtifact` — monospace, the existing smart-file reader (1MB cap).
  - Binary/unknown → `ViewerEmpty` + download.
  - Wire into `ArtifactCenter`'s `ArtifactBody` switch + `KIND_ICON`.
- `openArtifact.ts`/`artifactLabel` learn the new kinds. QuickOpen indexes
  them (they're workspace files → already in the dir index).

## Item 6 — Tests / gates

- pytest: containment rejection (../ + absolute escape); timeout kill;
  rlimit caps (skip-if-not-POSIX); env-scrub (child cannot see a planted
  SECRET env var — native); artifact scan reports created files & excludes
  run dirs; hosted PYTHON gate returns unavailable / self-host allowed;
  docker-engine command shape (recording fake, `--network=none` present);
  cocotb native env-scrub regression.
- vitest: image/data/text viewer render + caps; toolArtifacts mapping for
  run_python_analysis; artifactKeys parse for new kinds.
- e2e: run a tiny script via the palette/Command Surface → tool card shows
  artifacts → open the PNG (image viewer) and the CSV (table). (Mocked at
  the action layer like existing e2e.)
- Dockerfile: the pinned python-analysis image layer builds.
- Gates: pytest · tsc · vitest · Playwright · next build.

## Deferred (documented)
- Hosted Python via the ORFS isolated-job seam.
- Notebook/REPL, streaming output, inline-code param, pip/package management.
- .vcd-derived analysis helpers beyond vcdvcd; GDS analysis libs.
- seccomp/gVisor hardening of the native path (docker is the isolation story).

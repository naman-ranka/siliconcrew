# Wave 10 — Python analysis tool + rich artifact viewing

Status: DRAFT (implementation-grade; pending 2nd-agent review, then normal-agent implementation + my adversarial pass)
Supersedes the intent doc plans/python-analysis-artifacts.md (that stays as the "why").

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

# Build brief — SimEngine seam (Docker locally, native in the cloud)

Work on `claude/integration-p1p2`. Commit + push there.

## The limitation
Synthesis (ORFS) already runs cloud-safe via the `OrfsRunner` seam
(`local_docker` / `cloud_job` / `remote`). But the three lighter engines still
shell out to Docker, which **does not work on Cloud Run** (no nested
containers):
- `src/tools/run_xls.py` — `run_docker_command` in ~5 places.
- `src/tools/run_sby.py` — built around `run_docker_command`.
- `src/tools/run_cocotb.py` — already uses cocotb's native `get_runner`
  (iverilog), but its Docker tie is the osvb grading container.

`iverilog` + `yosys` are **already native** in the app image, so cocotb/sby are
most of the way there; XLS needs its binaries.

## Goal
Make these three runnable **without Docker in hosted mode** (so they work on
Cloud Run, fast and cheap), while keeping **Docker the default locally** so
open-source contributors stay plug-and-play. Interactive sims should run as
**native subprocesses** in the app container (no stage-in/out, <~1s overhead),
not as per-run Cloud Run Jobs (which would add ~6s and kill the edit-run loop).
ORFS stays a Cloud Run Job (it's the 6.5 GB, minutes-long heavyweight).

## THE STANDARD WAY: a config-selected seam, NOT scattered `if hosted`
Mirror the existing `OrfsRunner` pattern. Do **not** put `if SILICONCREW_HOSTED:`
branches inside the three tool files.

1. **Add a `ToolEngine` seam** (e.g. `src/platform_engines/tool_engine.py`):
   ```python
   class ToolEngine(Protocol):
       def run(self, *, image: str, command: str, cwd: str,
               env: dict | None = None, timeout: int) -> ToolResult: ...

   class DockerToolEngine:   # = today's behavior; wraps run_docker_command
       ...
   class NativeToolEngine:   # runs `command` directly as a subprocess in cwd
       ...
   def get_tool_engine() -> ToolEngine:   # cached; chosen by settings
       ...
   ```
   `ToolResult` = the same shape the tools already consume (`{returncode/success,
   stdout, stderr, command}`), so call sites barely change.

2. **Settings flag** (mirror `ORFS_ENGINE`): in `settings.py`
   `sim_engine = _env("SIM_ENGINE", "native" if hosted else "docker")`.
   `get_tool_engine()` returns `NativeToolEngine` for `native`, else
   `DockerToolEngine`. Default local = `docker` → **behavior bit-for-bit
   unchanged for contributors.**

3. **Route the three tools through the engine.** Replace each
   `run_docker_command(command=…, image=…, …)` with
   `get_tool_engine().run(image=…, command=…, cwd=…, timeout=…)`. The tools keep
   all their own logic (building the command, parsing output); only *execution*
   is delegated. For cocotb, the `native` engine path uses the existing
   `get_runner` (iverilog); the `docker` path keeps the osvb container for
   CVDP grading.

## The one real refactor care-point: paths
Docker mounts the workspace and commands use **container paths** (`/workspace/…`).
Native runs in the **real cwd**, so those commands must use **cwd-relative (or
real) paths**. For each tool, make the command path-agnostic: `DockerToolEngine`
maps cwd→`/workspace` and rewrites; `NativeToolEngine` runs in the real cwd
as-is. Get this right or native runs will "file not found". Add a test per tool
asserting the command/paths the native engine produces.

## Dockerfile (hosted image) — add the native toolchains
Add to the production image so `native` mode has the binaries (all small vs
ORFS):
- **XLS:** download Google's precompiled Linux XLS binaries onto `PATH`.
- **SymbiYosys:** `sby` + **Z3** (and any solvers sby needs); `yosys` already present.
- **cocotb:** `cocotb` (pip) + **gcc/make** (C compiler for the VPI); `iverilog`
  already present.
Keep them in the main image (cheap); local still defaults to `docker`, so their
presence is harmless. (Optional: gate behind a build arg if you want a leaner
local image — not required.)

## Hosted isolation + limits (do not overclaim "fully isolated")
Native subprocesses share the **app's Cloud Run instance**, and Cloud Run can
run **multiple requests per instance** — so this is *per-instance*, not
*per-run*, isolation (weaker than Docker-per-run). Make it safe-enough:
- Run every tool in its **per-session workspace cwd** (already the model) — never
  a shared dir; rely on the tenancy seam.
- Enforce **timeouts** (tools have them) + **resource caps**; run the subprocess
  as a **constrained/non-root user** if practical.
- Recommend (doc, not code) **Cloud Run concurrency = 1** for the app service if
  true per-request isolation is wanted.
Document this honestly in the runbook; don't call it "container-grade isolation."

## Guardrails
- Local default unchanged (`docker`); one decision point (`settings`); no
  scattered `if hosted` in the tools.
- Don't touch the action API auth/tenancy or the one write path.
- Keep all tests green (134 backend / Vitest / e2e).

## Verify
- Unit: `get_tool_engine()` returns Docker by default, Native when
  `SIM_ENGINE=native` (or hosted); each tool routes through the engine; the
  native-path command uses cwd-relative paths (no `/workspace`).
- Native smoke (CI-friendly, no Docker): run a tiny **cocotb** (iverilog is
  present) end-to-end via the native engine; if XLS/Z3 are installed in CI, a
  trivial XLS + a trivial sby proof too — else mark `skipif` like the ORFS
  real-run gate.
- Confirm the Docker path is unchanged (mock `run_docker_command`).

## Deliver
Commit per tool/slice, push to `claude/integration-p1p2`, and summarize: the
`ToolEngine` interface, the `SIM_ENGINE` flag, the per-tool routing + path
handling, the Dockerfile additions, and the isolation/limits notes.

# Phase 0 — Foundation & Contracts

This directory is the **ground truth** that two parallel agent workstreams build
against. It exists so Phase 1 (frontend + API) and Phase 2 (deployed backend)
can proceed concurrently without diverging.

> Read this file first. Then the contract docs. The two `agent-brief-*` files
> are the high-level briefs handed to each workstream.

## The three phases

```
Phase 0  (sequential, FIRST — this directory)
  Freeze the shared seam + contracts both agents depend on.
        │
        ├───────────────────────────┬──────────────────────────────
        ▼                            ▼
Phase 1  Frontend + API            Phase 2  Deployed backend
  (agent-brief-phase1.md)            (agent-brief-phase2.md)
  • new workbench shell in the       • multi-tenant execution (enforce
    SAME Next.js app, reuse the        the session context seam)
    existing artifact viewers        • ORFS as an isolated job, not DooD
  • thin REST handlers that call     • object-storage workspaces
    SiliconCrew tools (never raw     • quotas / auth / abuse controls
    EDA), one shared action layer    • swap local impls behind the
  • build + test slice by slice        Phase-0 interfaces
```

## Why Phase 0 must come first

The two workstreams share the single most load-bearing thing in the system:
**how a request identifies the workspace/tenant it acts on, and the API
contract on top of the tools.** If Phase 1 builds endpoints against today's
process-global workspace and Phase 2 refactors that underneath, Phase 1 breaks.
So the seam is frozen here, with a *local* implementation Phase 1 can run
against and Phase 2 later replaces with a cloud-backed one.

## What Phase 0 delivers (this commit)

1. **The tenancy seam, in code, additive and tested.**
   - `src/utils/session_context.py` — task-local `SessionContext`, `session_scope`,
     and a `WorkspaceProvider` interface (`LocalWorkspaceProvider` now,
     cloud provider in Phase 2).
   - `src/tools/wrappers.py::get_workspace_path()` now prefers the context,
     then the `RTL_WORKSPACE` env var, then the default — **fully backward
     compatible** (unchanged until a caller sets a context).
   - `tests/test_session_context.py` — proves concurrent sessions are isolated
     (the fix for the cross-tenant race).
2. **Frozen contracts** (docs in this directory):
   - `api-contract.md` — endpoint surface + request/response shapes + rules.
   - `data-model.md` — design manifest, file roles, unified run model.
   - `agent-brief-phase1.md`, `agent-brief-phase2.md` — the two workstream briefs.

## The seam explained (the one thing to understand)

Today (`api.py`): `os.environ["RTL_WORKSPACE"] = workspace` per request →
every tool reads that global via `get_workspace_path()`. One process serving
many users races on it → cross-tenant corruption.

Phase 0 replaces the *resolution* with a task-local context. Because every tool
already funnels through `get_workspace_path()`, fixing that one function makes
**all ~30 call sites** context-aware with no edits to them.

### Required integration step (first task of Phase 1/2)

Wire the request lifecycle to set the context instead of mutating the global.
In `api.py`, replace the `os.environ["RTL_WORKSPACE"] = workspace` line with:

```python
from src.utils.session_context import SessionContext, session_scope
...
with session_scope(SessionContext(session_id=session_id, workspace=workspace)):
    # run the agent / call tools for this request
    ...
```

**Verification gate (do not skip):** confirm the context propagates through
LangGraph tool execution. `asyncio.to_thread` copies context, but
`loop.run_in_executor(...)` does **not**. If LangGraph runs sync tools via a
bare executor, wrap tool invocation with `contextvars.copy_context().run(...)`
(or run tools on the event loop). Add an integration test that fires two
concurrent sessions through the agent and asserts each writes only to its own
workspace. This is the gate that says "multi-tenant safe."

## Principles both workstreams must honor

- **Call SiliconCrew tools, never raw EDA tools.** Buttons and the agent both go
  through the tool layer (which already returns the exact `iverilog`/`vvp`/ORFS
  commands for transparency). No shelling out to `iverilog` from a handler.
- **One action layer.** A capability is one function reached identically by a
  REST handler (human click) and the agent (`@tool`). Never two code paths.
- **Hardware-first, artifact-first.** The pipeline (Spec→RTL→Lint→Sim→Synth→
  Signoff) is the spine; the result artifacts (waveform, timing, layout) are the
  star, not the code editor. See `mockups/workbench.html`.
- **Isolated, provenance-stamped runs.** Every run is a pure function of
  (manifest subset + pinned toolchain) in its own dir. Synth already does this
  (`src/tools/synthesis_manager.py`); sim must match it.
- **Slice and verify.** Each unit of work ends in something runnable and tested.
  No long open-ended runs without a feedback loop.

## Verification environment (proven working)

Visual / E2E verification is available in cloud sessions and was confirmed by
opening `mockups/workbench.html` and screenshotting it. Recipe for the agents:

- **Browser tools:** the committed `.mcp.json` provides the **Playwright MCP
  server**. First use in a session may need an explicit "use playwright mcp".
- **Install path:** use `npx playwright install chrome` (apt-based real Chrome).
  The bundled-Chromium CDN build (`cdn.playwright.dev`) may be blocked by egress;
  `install chrome` is the reliable path here.
- **Serving files:** the `file:` protocol is blocked. Serve over local HTTP
  (`python3 -m http.server 8765`) and load `http://localhost:8765/...`. The
  Next.js dev server is already HTTP, so the app under test is fine; this only
  matters for static files.
- **Loop:** navigate → screenshot → DOM snapshot for assertions. Use this for
  the Tier-2 (visual/E2E) checks each brief requires; Tier-1 (Vitest/jsdom)
  needs no browser.
- A bare HTML page served over HTTP typically logs one benign `favicon.ico 404`
  console error — harmless; don't chase it unless other errors appear.

## Reference material (already in the repo)

- `mockups/workbench.html` — the target UX (pipeline-first, artifact-first).
- `src/tools/synthesis_manager.py` — the run-isolation pattern to mirror for sim.
- `src/tools/run_simulation.py` — returns structured status + the raw commands.
- `docs/hosted_workbench_plan.md` — the deployment vision (Phase 2 context).

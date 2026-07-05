# SiliconCrew — agent field guide

Read this before touching anything. It encodes how this repo is built, how
decisions get made here, and the mistakes already paid for. The owner's
standing instruction, verbatim in spirit: **everything must be fundamental,
simple, honest, and hardware-designers-first — built as an excellent
open-source base, never a demo.** When in doubt, choose the boring, durable
design over the clever one, and say the trade-off out loud.

## What this is

An AI-assisted chip-design platform. Backend: FastAPI (`api.py`) + LangGraph
agent (`src/agents/architect.py`) + LangChain `@tool` wrappers
(`src/tools/wrappers.py`) + an MCP server (`mcp_server.py`) mounted for
external AI apps. Frontend: Next.js 14 (`frontend/`), Zustand stores. Flow:
spec → RTL → lint (iverilog/verilator) → sim (iverilog, multi-TB) → synthesis/
PnR (ORFS in docker locally, Cloud Run Jobs hosted) → reports/waveforms/GDS.

Two deployment modes, selected by `SILICONCREW_HOSTED` via
`src/platform_engines/settings.py`: **self-host** (sqlite, local docker,
local workspace dirs, no auth deps) and **hosted** (Cloud Run + Postgres +
GCS + WorkOS/Google auth + quotas). The engine-selection idiom
(`persistence_engine` / `sim_engine` / `orfs_engine` / `workspace_engine`,
lazy imports in the cloud branches) is sacred: **self-host must never need a
cloud dependency installed.**

Product surfaces: `/` Launcher (sessions = workspaces = one design block;
groups = tags, not folders) → `/w/{sid}?chat=&view=agent|ide`. Two postures:
**IDE** (user drives: ⌘K palette, Command Surface, file explorer, dock) and
**agent** (delegate: prompt + view ONLY — no command palette, no file
creation; artifacts in a slide-over panel whose home tab is the Runs/Files
Index; nav rail overlay on ⌘O). Posture is layout emphasis only — same
stores, same tabs.

## Platform invariants (violating these is a bug, not a style choice)

1. **The manifest is the single source of truth** for design files/roles/
   tops. UI/tools offer *suggestions* from it; free entry stays allowed;
   closed lists only for true enums.
2. **One tool registry, zero drift.** Agent, MCP, REST `/invoke`, and the
   Command Surface all execute the SAME wrappers; policy (categories,
   PROTECTED, ASYNC, MUTATING, EXCLUDED_FROM_UI) lives ONLY in
   `src/api/tool_catalog.py`. Never hand-maintain a parallel tool list.
3. **One event log, rendered everywhere.** Every actor's tool calls (agent /
   ui / mcp / system) land in `attempt_events.jsonl`; the IDE Activity dock
   and the agent-shell inline cards are two views of it. A user gesture that
   calls a tool goes through `/invoke` so it IS an event.
4. **Honest state, always.** No simulated data, no fake liveness, no
   ambiguous verdicts (a session has many runs → NO session-level status
   dots; per-RUN dots are fine). Async work = unread markers, never
   auto-switching tabs. Show staleness ("checked 4m ago") rather than
   pretending freshness.
5. **The run directory is the database.** `run_meta.json` + artifacts are
   authoritative; process memory is a cache. ONE key: `run_id` (job_id was
   eliminated — don't reintroduce it). Whoever computes writes its own
   terminal state; every read reconciles; a silent run past its ceiling is
   declared failed ("orchestrator lost") — no run is EVER stuck "running".
   Completion emits exactly one activity event (`completion:<run_id>`,
   deduped at read).
6. **The UI is a viewer, not an actor.** It never polls run status on its
   own. Updates come from: activity events (slow log-watch only while a run
   is live), the user's Refresh (same tool as everyone else), and window
   focus. `dispatch → poll(status, poll_after_sec) → read` is the one async
   contract; `wait_for_synthesis` (bounded ≤120s) is the ONLY blocker.
7. **URL is the source of truth** for location (`/w/{sid}?chat=&view=`);
   the store follows the URL, never the reverse. SWR iron rule in
   `frontend/lib/store.ts`: populated data never blanks; stale-response
   guards on every cross-session async.
8. **Tenancy is owner-scoped everywhere** (`_owner_clause`), with defense in
   depth. Watch the sharp edges: ensure-paths must seed rows for the TRUE
   owner (not the caller); in-memory registries keyed by bare ids collide
   across workspaces (`synth_0001` exists in every workspace — scope keys by
   workspace); browsing/listing endpoints must be READ-ONLY (never
   materialize rows).
9. **Twelve-factor hosted.** Nothing durable on instance disk. Metadata +
   LangGraph checkpoints are in Cloud SQL; workspaces in GCS; ORFS runs
   write to `orfs-runs/<session>/<run_id>` so ANY instance can adopt and
   finalize. Config fail-fast: `persistence_engine=postgres` with empty
   `DATABASE_URL` refuses to boot (silent sqlite fallback = data loss).

## How decisions get made here (the process that repeatedly worked)

1. **Discuss first.** The owner asks probing questions and wants trade-offs
   stated honestly; propose a recommendation, not a menu. Decisions get
   LOCKED and recorded in the plan ("Locked constraints" section).
2. **Write an implementation-grade plan** in `plans/<name>.md`: grounded in
   file:line evidence, with invariants, a full consumer sweep, a test list,
   and explicit "do NOT" fences. Every "reuse existing X" claim must be
   verified in code first — unverified reuse claims were wrong repeatedly.
3. **Second-agent review of the plan against the codebase** before any code.
   This caught 10–26 real corrections EVERY wave. The owner also runs an
   external ("codex") review; fold both into an "Amendments" section that is
   AUTHORITATIVE over the plan body. Never skip this step.
4. **Implement per-item with a commit+push per item** (a stop-hook enforces
   pushing). Subagents for mechanical, file-disjoint sweeps (test updates,
   frontend tracks) with precise contracts; never two agents in the same
   files; commit WIP before delegating (subagents can die mid-task — verify
   their "done" via tests, not their word).
5. **Full gates before calling anything done**, then an **adversarial review
   of the finished diff** ("find REAL bugs with concrete failure sequences;
   verify before reporting"). This caught 5–8 genuine bugs every wave
   (timezone floors, tenancy clobbers, write-only durable state). Fix with
   regression tests proven to fail on pre-fix code.
6. **Deferred ≠ dropped.** Every plan ends with a documented deferred list.
   Honesty about limits (e.g. "hosted legs are fake-tested; no live Cloud
   SQL in CI") beats pretending coverage.

## Gates & environment (exact commands)

- Backend: `python -m pytest tests/ -q --ignore=tests/test_identity_migration.py
  --ignore=tests/test_mcp.py --ignore=tests/test_mcp_remote_auth.py`.
  ~20 KNOWN env-gap failures in this container (llm_factory, mcp_auth,
  congestion_summary, perf_read_no_sync, cocotb, sby, sby_engine, xls —
  missing deps/binaries). ZERO new failures allowed; when unsure, `git
  stash` and compare against the clean-tree baseline. After suite runs:
  `git checkout -- tests/fixtures/ test_sby_output.txt` (tests dirty the
  checked-in fixture workspaces; some side effects are gitignored).
- Frontend (from `frontend/`): `npx tsc --noEmit` · `npx vitest run` ·
  `PW_EXECUTABLE=/opt/pw-browsers/chromium npx playwright test` (baseline:
  all pass, 1 env skip) · `npx next build`.
- No `pytest-asyncio`: drive async tests with `asyncio.run`. No live
  Postgres/GCS/Cloud Run in CI: recording fakes + `sys.modules` injection
  for lazy imports (patterns in `tests/test_checkpointer.py`,
  `test_synth_hosted_durability.py`, `test_persistence.py`).

## Sharp edges already paid for (do not rediscover these)

- **Route shadowing**: `/api/sessions/{session_id:path}` is greedy — session
  PATCH/DELETE/GET must stay registered AFTER every `/threads` sub-route.
- **Timezones**: never call `.timestamp()` on a naive datetime (it reads as
  LOCAL time). Parse ISO strings, assume UTC when naive, compare aware.
- **`shutil.copy2` preserves mtimes** — any mtime-based "did THIS run
  produce it" logic needs a dispatch-time floor + inherited handling.
- **`NativeToolEngine` merges full `os.environ`** (tool_engine.py) — you can
  add env keys through it, never scrub. A gated/sandboxed subprocess must be
  bespoke. `run_docker_command` has NO isolation flags (no --network/--user/
  limits) — extend it or go bespoke; route custom mounts through the
  docker-outside-docker translation (`HOST_WORKSPACE`).
- **`Action` enum authz gates ANONYMOUS only**; the hosted on/off switch is
  `get_settings().hosted`. `/invoke` has no `authorize()` — capability
  checks belong INSIDE the wrapper so agent/MCP/REST are covered by
  construction. `enforce_file_containment` auto-applies ONLY on `/invoke`.
- **run_meta absolute-path leak**: `netlist_path` is absolute and consumed
  at read time; `manifest.json` carries `sessionId` that reconcile won't
  overwrite — any workspace-copy feature must rewrite both (see the
  templates plan amendments).
- **Frontend session switches**: reset per-session slices (`runs`,
  `selectedRunId`, `synthJob`, threads guards) — run ids collide across
  sessions and transition detectors will fire falsely otherwise.
- **Esc/overlay discipline**: consumers `preventDefault()`; global listeners
  check `defaultPrevented` after a 0-timeout + a one-tick "overlay was open"
  grace. Keep-alive panels stay mounted at width-0 with `inert`.
- **Monaco/e2e**: regex text matchers break on Monaco's nbsp rendering — use
  string matchers. Playwright needs `PW_EXECUTABLE`; role-based selectors
  avoid strict-mode collisions.

## State of the repo (end of the 10-wave overhaul)

Waves 1–10 are done, reviewed, and pushed on `claude/siliconc-workbench-v2-
ilsd83`: workbench v2 (palette, activity, runs, artifact tabs), Command
Surface, schema-driven tool platform, verification loop (multi-TB sim, real
lint engines, max_stage synth), session system + launcher + agent shell v2
(slide-over), the foundational synthesis job model (run_id-only, tombstones,
adoption), and hosted chat durability (pooled Postgres checkpointer).
History and rationale live in `plans/*.md` — each plan's Status header and
Amendments section tell you what is authoritative.

**Queued, implementation-ready (already through review):**
- `plans/python-analysis-and-artifacts.md` — Python analysis tool (bespoke
  gated subprocess; docker-preferred; hosted OFF via `settings.hosted`) +
  image/data/text artifact viewers.
- `plans/session-templates-and-forks-wave.md` — templates as BUNDLES (not
  sessions), fork-only, transcripts rendered as workspace markdown; Level 1,
  self-host only.

**Known deferred (each documented in its plan):** metadata-store pooling,
dedicated `messages` table (decouple transcript from LangGraph), SSE push of
activity, per-stage ORFS invocation for the full flow (owner locked `make
-B` as-is), hosted per-stage timings, run retention/GC, checkpoint-continuity
forks, hosted template gallery.

## Final wisdom

The owner is not a hardware-flow expert and says so — your job is to be the
senior engineer who explains trade-offs plainly, protects the invariants,
and pushes back with evidence (they consistently reward honest pushback and
punish hand-waving). The reviews are not overhead; they are where more than
half the real defects were caught. And the test of every design here is the
same question the owner asks each time: *is this the simple, fundamental
version — or am I building machinery?* If you can't defend a piece of
machinery in one sentence to a hardware designer, delete it.

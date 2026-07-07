# Wave 11 — Session templates & forks: implementation report

Branch: `claude/overnight-showcase`. Plan:
`plans/session-templates-and-forks-wave.md` (implemented as amended, A1–A8).

## Per-item commit list

| Commit | Summary |
|--------|---------|
| `c304a41` | Backend: `bundles.py` (guarded copy + secret scan), `transcript.py` (lightweight checkpoint reader — no api.py, no LLM — + pure renderer), `templates.py` (list/get/fork/export with A1–A6 rewrites + A5 gate), `scripts/export_bundle.py` CLI, REST routes, `SessionResponse.source_template`. (items 1,2,4) |
| `60f52c6` | Ship the real `examples/sync_fifo` bundle (dogfood-authored) + harden export sanitizer (redact author paths, drop compiled `.out`, skip empty transcripts). (item 1) |
| `5f58769` | Frontend: `templatesApi`, store `templates`/`loadTemplates`/`forkTemplate`, Launcher Examples section, `ExampleCard`, `TemplatePreview` (new A8 component), Breadcrumb provenance chip. (item 3) |
| `835f8d6` | Tests: 26 pytest + 11 vitest cases. (item 5) |
| `cdf645f` | Fix: surface provenance via the session LIST (chip survives reload); Playwright e2e spec. |
| `e627817` | Fix: coerce `loadTemplates` payload to an array (Launcher reads `.length`). |

## Gate results (baseline vs after)

- **pytest** (`tests/ -q --ignore=identity_migration,mcp,mcp_remote_auth`):
  baseline **9 failed / 644 passed / 8 skipped**; after **9 failed / 670 passed
  / 8 skipped**. The 9 failures are the identical known env-gap set
  (congestion_summary ×2, lint_engines norm_file, llm_factory, orfs_job,
  perf_read_no_sync, sby_engine, xls_engine ×2). **ZERO new failures**; +26 from
  `tests/test_templates_fork.py`.
- **tsc** (`npx tsc --noEmit`): clean (exit 0).
- **vitest** (full run): **1 failed / 360 passed**. The single failure —
  `chat.threads.store.test.ts > newThread … toHaveBeenCalledWith("s1")` — is
  **pre-existing and NOT from this wave**: verified it also fails on `af0124b`
  (the codex-extension commit), which added a `runtime` arg to
  `threadsApi.create(sessionId, undefined, undefined, runtime)` while the test
  still asserts an exact single arg. My 11 new cases (ExampleCard,
  TemplatePreview, Breadcrumb chip) pass.
- **next build**: clean (exit 0).
- **Playwright**: `e2e/templates.spec.ts` **passes** (examples → preview → fork
  → lands in `/w/{fork}` with file tree + copied Activity trajectory +
  provenance chip). `workbench.smoke.spec.ts`: 10/11; the one failure is the
  `⌘P quick open` test which **passes on isolated re-run** (flaky — ⌘P races the
  browser's native print shortcut) and touches nothing in this wave; the two
  Launcher smoke tests (which render my Examples section) pass.

## Bundle shipped

`examples/sync_fifo/` — dogfood-authored via `export_session_bundle` (NOT
hand-written): created a self-host session, wrote real sync_fifo RTL + a
self-checking testbench, then drove the platform's own `/lint` and `/simulate`
actions. The bundle carries a **genuine** trajectory in `attempt_events.jsonl`:
`linter_tool` (iverilog, clean) → `run_isolated_simulation` sim_0001 **failed**
(a seeded read-ordering bug: `dout <= mem[wr_addr]`) → the fix →
`run_isolated_simulation` sim_0002 **passed** — plus both runs' real VCD
waveforms. No synthesis (native iverilog only; no local ORFS attempt — a
sim-only bundle is acceptable per the brief). No fabricated artifacts.

The export sanitizer was hardened for public bundles: redacts the author's
absolute host paths (source workspace + home) from `run_meta` command/log-tail
strings down to `<workspace>`, drops compiled `*.out`/`*.vvp` build artifacts,
and clears `manifest.sessionId`. Verified the committed bundle contains **no**
`naman`/`C:\Users` leaks.

## Deferred / incomplete (honest)

- **No conversation transcript in the shipped bundle.** No LLM key is available
  in this container, so I could not author a genuine agent chat. Rather than
  fabricate one (invariant 4), export **skips** empty-thread transcripts, so the
  bundle honestly ships no `conversations/` dir. The transcript renderer +
  reader + conversation preview UI are fully built and unit-tested; they simply
  have no chat to render for THIS bundle. A future bundle authored with a live
  key will exercise the chat showcase end-to-end.
- **Hosted fork path deferred (A5)** — Level 1 is self-host only; fork
  hard-gates to non-cloud with a clear 400. Hosted gallery is a later wave.
- All other plan "Deferred (documented)" items stand (Level-2 checkpoint-copy
  fork, hosted gallery/versioning, publish/review, etc.).

## For the findings ledger (do not edit FINDINGS.md myself)

- **Pre-existing stale vitest test** (from codex commit `af0124b`):
  `frontend/test/chat.threads.store.test.ts` → `newThread … toHaveBeenCalledWith("s1")`
  fails because `newThread` now calls `threadsApi.create(sessionId, undefined,
  undefined, runtime)` (4 args). One-line test fix (`toHaveBeenCalledWith("s1",
  undefined, undefined, undefined)` or `expect.anything()`). Left untouched —
  outside this wave's scope. This means CLAUDE.md's "vitest baseline: all pass"
  is stale on `claude/overnight-showcase`.
- **`⌘P` quick-open e2e is flaky** under parallel load (races the browser's
  native print shortcut); passes on isolated re-run. Candidate for a
  `page.keyboard` guard or a non-⌘P trigger.

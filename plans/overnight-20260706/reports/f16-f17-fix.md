# Wave 11 review fixes — F16 (sanitizer) + F17 (provenance chip)

Branch `claude/overnight-showcase`. One commit: **`8e90f1b`**. Stayed in my
files (backend templates code + `api.py` patch_session) — did not touch
`Launcher.tsx`, `store.ts`, or any landing/F2-agent files.

## F16 — export sanitizer only redacted run_meta.json (MEDIUM, privacy)

**Change:** factored the host-path redaction out of the inline run_meta loop
into a reusable `bundles.redact_host_paths(text, paths, placeholder)` — same
rules as before (native, JSON-escaped `\\`, and forward-slash variants;
longest-first so the workspace path is scrubbed before the home-dir prefix).
Applied it in three places now, not one:

1. `run_meta.json` command/log-tail strings (kept — unchanged behavior).
2. **`attempt_events.jsonl` + `attempt_log.json`** — read the whole file, redact
   the raw text (JSON-safe: `<workspace>` has no quotes/backslashes so the lines
   stay valid JSON), write back only if changed. `_sanitize_exported_workspace`.
3. **`render_transcript`** — new optional `redact_paths` param; the rendered
   markdown (which folds tool args/results via `_fmt_args`/`_summarize_result`)
   is redacted before return. The function stays PURE (deterministic in its
   args). `export_session_bundle` passes the same `[src_ws, home]` redaction set
   it hands the sanitizer.

Docstring corrected — it now says it redacts run_meta **and** the actor event
logs, and notes transcripts are redacted at render time (was overstated as
"strips the author's identity" while only touching run_meta).

**Regression tests** (`tests/test_templates_fork.py`):
- `test_render_transcript_redacts_author_paths` — a tool result echoing
  `C:\Users\naman\…\workspace\uart\...` comes out with no `naman` / `C:\Users` /
  `C:/Users`, only `<workspace>`; asserts the un-redacted render still leaks (so
  the test bites).
- `test_export_then_fork_round_trip` extended — the exported
  `attempt_events.jsonl` + `attempt_log.json` (seeded with an absolute author
  path) come out redacted to `<workspace>`.

The already-shipped `examples/sync_fifo` bundle re-scanned clean (its tool args
were relative), so no re-export was needed — this fix is preventive for the
flagship p1 (spec→GDS) export where docker/HOST_WORKSPACE absolute paths WILL
appear in the event log.

## F17 — provenance chip blanks on rename/move (LOW-MED, invariant 7 SWR)

**Change:** `patch_session` (`api.py`) now includes
`source_template=templates_mod.read_provenance(session_manager.get_workspace_path(session_id))`
in its `SessionResponse`, consistent with `list_sessions` / `get_session`. The
store replaces `currentSession` (rename) and the list entry (move) with the
patch response, so without this the forked-from chip vanished until the next
`loadSessions`. api.py-side only — no `store.ts` change (off-limits this round).

**Regression test:** `test_api_patch_session_preserves_provenance` — fork
`demo_fifo` → PATCH rename → the response AND the subsequent list carry
`source_template.id == "demo_fifo"`.

## Gate verdict

- `tests/test_templates_fork.py`: **28 passed** (was 26; +3 net: transcript
  redaction, patch provenance, plus the extended round-trip assertions).
- Full backend subset (CLAUDE.md command): **9 failed / 678 passed / 8 skipped**
  — the identical 9 known env-gap failures (congestion_summary ×2, lint_engines
  norm_file, llm_factory, orfs_job, perf_read_no_sync, sby_engine, xls_engine
  ×2). **ZERO new failures.**
- No TS touched (both fixes are backend; `Session.source_template` already
  existed) → tsc/next build not required for this change.

## F3 (not actioned — out of scope)

The reviewer's F3 (secret scan is name-only, misses content-borne secrets) is
explicitly "a known limitation, not a defect," already documented in-code, and
not part of this task. Left as-is; content-scrub enforcement stays a Level-3
deferral in the plan.

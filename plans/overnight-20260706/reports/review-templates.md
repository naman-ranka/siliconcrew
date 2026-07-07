# Wave 11 (session templates & forks) — adversarial diff review

Branch `claude/overnight-showcase`, diff `ccdb6e0..HEAD`. Read-only pass.
House rule: every finding has a concrete failure sequence + file:line, verified
against the code before reporting.

## Verdict

**Safe to keep. Build the landing-page gallery on it.** The load-bearing
amendments (A1–A8) are all honored and I verified each against the code. No
high-severity bug found (no half-fork, no path leak in the shipped bundle, no
route shadowing, timezone is aware-UTC, rollback is sound). Two real-but-minor
defects worth fixing before the gallery is a headline surface, plus one honest
limitation to keep in mind.

## Findings (ranked)

### F1 — [MEDIUM] Export sanitizer scrubs only `run_meta.json`; author host-paths in `attempt_events.jsonl` + rendered transcripts are NOT redacted
`src/utils/templates.py:383` `_sanitize_exported_workspace` runs its
path-redaction pass **only** inside the `_iter_run_metas` loop (run_meta files).
`attempt_events.jsonl` / `attempt_log.json` are copied verbatim by
`copytree_guarded`, and `conversations/*.md` are rendered *after* sanitization by
`render_transcript` (`transcript.py:122`), which passes tool args/results through
`_fmt_args`/`_summarize_result` with truncation but **no redaction**.
Failure sequence: author exports a session that ran synthesis or where a chat
turn referenced an absolute path → the docker/HOST_WORKSPACE path
`C:\Users\<name>\…` lands in a tool result inside `attempt_events.jsonl` and in
the transcript → committed to the PUBLIC examples repo. The function docstring
claims it "strip[s] the author's identity from a workspace about to be
committed" — overstated; it strips it from run_meta only.
Mitigation in place: export is a curator-in-the-loop offline tool that prints
`scan_for_secrets` warnings and tells the curator to review before committing;
and the shipped `examples/sync_fifo` bundle is verifiably clean (grep for
`naman`/`C:\Users`/`/home/` across the bundle → nothing).
Fix: run the same redaction over `attempt_events.jsonl`/`attempt_log.json` and
inside `render_transcript`, OR narrow the docstring and rely on the human review
+ secret scan. (This is the leak path the review brief asked to hunt for.)

### F2 — [LOW-MED] Provenance chip blanks after renaming / moving a forked session (SWR "populated data never blanks" violation)
`api.py:1275` `patch_session` constructs `SessionResponse` **without**
`source_template` (defaults to `None` → serialized `null`).
`frontend/lib/store.ts:622` `renameSession` does
`currentSession = updated` and `moveSession:616` replaces the list entry with the
patch response. `Breadcrumb.tsx:22` reads `currentSession?.source_template`.
Failure sequence: fork `sync_fifo` → land in `/w/{id}`, chip shows "forked from
Sync FIFO" → rename the session (a common first action) → store overwrites
`currentSession` with the patch response whose `source_template` is null → chip
disappears. Self-heals only on the next full `loadSessions` (window focus /
reload). Violates invariant #7 (SWR iron rule) and the plan's "provenance
survives" intent for the rename case.
Fix: include `source_template=templates_mod.read_provenance(session_manager.get_workspace_path(session_id))`
in `patch_session`'s response (consistent with `list_sessions`/`get_session`),
or merge in the store (`{ ...prev, ...updated }`) so the field is preserved.

### F3 — [LOW / honest limitation] Secret scan is name-only; misses content-borne secrets and some name shapes
`src/utils/bundles.py:131` `scan_for_secrets` matches only basename substrings.
It will not flag: an API key pasted into `spec.md`, a `.v` comment, or a chat
transcript; a token in a generically-named `config.json`/`notes.txt`;
`env.production` (no leading dot, so `.env` doesn't substring-match). Already
documented in-code as "name-based only… a warning list, not a guarantee," so
this is a known limitation, not a defect — noted so the gallery curator knows
`spec.md` and transcripts are unscanned. Pairs with F1.

## Amendments verified honored (A1–A8) + sharp edges

- **A1** create-then-copytree: `templates.py:352-357` create_session first, then
  `copytree_guarded(..., dirs_exist_ok=True)` into the empty dir. ✓
- **A2** netlist rewrite: `_rewrite_run_meta_netlists:240` iterates **every**
  run_meta, keys on `meta.get("top_module")` — verified synth run_meta uses
  `"top_module"` (synthesis_manager.py:1387), not sim's `"top"` — and re-derives
  via `_find_netlist(run_dir, top)` against the copied (mtime-preserved) run dir,
  reproducing the original choice. No-op for the shipped bundle (sim runs carry
  no `netlist_path`). ✓
- **A3** `_clear_manifest_session_id:215` blanks a non-empty `sessionId`; shipped
  manifest already `""`. ✓
- **A4** `.source_template.json` provenance, no schema migration. ✓
- **A5** hosted hard-gate: `_is_cloud_workspace()` (workspace_engine=="cloud")
  raised as `TemplatesUnavailable` → `api.py:807` 400, as the FIRST statement in
  `fork_from_template` so no partial fork is possible. ✓
- **A6** rollback: `except BaseException → delete_session` (`templates.py:361`).
  Verified the subtle case: create_session pre-makes dst, so
  `copytree_guarded`'s own cleanup is skipped (`created_dst=False`), but the
  outer `delete_session` removes the whole dir — no half-fork. Byte/file ceiling
  guard present (`bundles.py:89-96`). ✓
- **A7** no `api.py` import: `transcript.read_thread_messages` imports only
  `platform_engines.checkpointer` (stdlib + lazy aiosqlite/langgraph). ✓
- **Route shadowing**: `/api/templates*` are single-segment `{template_id}` (no
  `:path`), distinct prefix from the greedy `/api/sessions/{…:path}`. ✓
- **Timezone**: `forked_at` is `datetime.now(timezone.utc)` — aware. ✓
- **Tenancy**: fork's create_session gets `user_id=_uid(identity)` (caller-owned);
  `_safe_bundle_dir` commonpath-guards traversal. ✓
- **M2 trajectory**: `/activity` reads `attempt_events.jsonl` by workspace
  LOCATION (actions.py:697), not the internal `session_id` field, so copied
  events render in the fork despite carrying the source id. ✓

## Gate claims re-verified
- `tests/test_templates_fork.py`: **26 passed** (report said 26). ✓
- Pre-existing vitest failure `chat.threads.store.test.ts > newThread` — file is
  **untouched by Wave 11** (`git diff ccdb6e0..HEAD` empty for it) and still
  fails at HEAD (1 failed / 7 passed), so it was failing before this wave.
  Report's "pre-existing, unrelated" claim is honest. ✓

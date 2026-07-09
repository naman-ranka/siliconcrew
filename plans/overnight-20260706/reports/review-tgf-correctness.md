# Adversarial correctness review — templates-GCS + hosted-fork

**Diff reviewed:** `git diff endgame..HEAD` (22 commits) on
`worktree-templates-gcs-hosted-fork`. Read-only on code; suites run below.

## Verdict

**DEPLOY-SAFE.** No CRITICAL or MAJOR correctness/tenancy defect found in the
finished diff. The two headline fixes hold under adversarial tracing:

- **A17 (cross-tenant leak+clobber) — HOLDS.**
- **A18 (concurrent same-template race) — HOLDS.**

**TENANCY verdict: SOUND.** A hosted fork seeds the workspace + metadata row for
the TRUE forking owner; no traced sequence lets user B read or overwrite user
A's session, workspace, or `source_template`, nor write the official templates
bucket. Findings below are LOW / acknowledged only.

## A17 — cross-tenant leak+clobber (b687ab8): PROVEN to hold

Defense is in depth and each layer was checked against the code, not the commit
message:

1. `create_session` pre-check now reads the **shared** store unscoped —
   `self._store.get_session(session_id, user_id=None)` (`session_manager.py:154`).
   On a second instance with empty local disk it still sees an id owned in Cloud
   SQL, so a name-derived fork id already held by another tenant is rejected
   (→ `_allocate_fork_session` suffixes to a free id, `templates.py:362-378`).
2. The cloud fork calls `provider.delete_workspace(new_session_id)` **before**
   `workspace_for` (`templates.py:469-475`), purging any orphaned manifest so
   `workspace_for` can never hydrate a prior tenant's committed files
   (`delete_workspace` drops scratch + sibling caches + the manifest object,
   `workspace_provider.py:729-750`; only the manifest makes a workspace
   adoptable).
3. Cloud `delete_session` now purges the GCS workspace after the ownership guard
   (`session_manager.py:247,260-267`) — closing the D7 orphan window at source;
   self-host has no provider and skips it.

Sequence (B) — user B forks a template A already forked — resolves at the
unscoped pre-check → B gets a distinct id, A's row/workspace untouched (verified
`test_cross_tenant_fork_of_same_template_isolates_owner_and_workspace`,
`tests/test_hosted_fork.py:485`). Sequence (A) — delete-then-refork by the same
user — resolves via the delete-time GCS purge + the fork-time
`delete_workspace` (verified `test_refork_after_delete_is_not_contaminated…:458`).
The new `source_template` setter is owner-scoped (`WHERE session_id=? AND
user_id=?`, `metadata_store.py:355-361, 749-755`) so no cross-owner set; reads
flow through owner-scoped `get_session` so no cross-owner read.

## A18 — concurrent same-template fork race (870a0ed): PROVEN to hold

The residual (both racers pass the non-atomic pre-check) is closed at the DB
layer, not process-locally: `create_session` uses `insert_session` (INSERT-only,
`metadata_store.py:290-302` sqlite / `702-716` postgres) which raises
`DuplicateSession` on the primary-key conflict; the loser cleans up its just-made
dir and raises `FileExistsError` → `_allocate_fork_session` retries a fresh
suffix (`session_manager.py:157-170`). Because the loser is handed a *distinct
owned id* before any `delete_workspace`/`sync`, A17's own delete-before-hydrate
can never touch the winner's live workspace. Atomicity is real (sqlite
`IntegrityError` / postgres `UniqueViolation` on the PK), not a check-then-act.
`upsert_session` (still COALESCE-owner) is untouched and used only by the
idempotent `ensure_session`. Verified
`test_concurrent_same_template_fork_race_insert_arbitrates:525`,
`test_insert_session_raises_on_duplicate:567`,
`test_create_session_rejects_preexisting_global_row:581`. Same-instance
concurrency is additionally serialized by `os.makedirs` (no `exist_ok`) raising
before insert.

## Rollback / partial-fork (§4.7): sound

`sync()` is the LAST fork step and writes the manifest last within sync
(`templates.py:491-492`), so any earlier failure leaves no adoptable workspace.
`_rollback_fork` (`templates.py:381-401`) runs `delete_workspace` + owner-guarded
`delete_session` best-effort; only unreferenced content-addressed blobs may
survive (documented GC-deferred). Verified `test_rollback_on_materialize_failure`,
`test_rollback_on_sync_failure`, and REST `…maps_to_503/500` assert
`get_all_sessions()==[]`.

## Split / sha / honest-offline: sound

- **Split (priority 3):** filter is by result-tree + TYPE
  (`split_bundle_binaries.py:57-78`) — `.gds/.def/.spef/.rtlil/.v/.guide/.webp` +
  `mem.json`. It leaves `.odb`/`.sdc`/`.rpt`/logs/`run_meta.json` in git, so
  `_STAGE_COMPLETION_MARKERS` (`synthesis_manager.py:136-142`, keys off
  `.odb`/`.sdc`) and `get_ppa_metrics` (reads only `*.rpt`/`*.log`,
  `get_ppa.py:37-93`) are byte-identical pre/post split. A binary-less fork
  re-derives `netlist_path=None` (not the `inputs/` RTL) via A15
  (`templates.py:271-328`) — no crash, runs pane intact — and the layouts
  endpoint honestly reports the split-out GDS in `missing_binaries`
  (`api.py:2532-2569`), consumed correctly by `LayoutArtifact.tsx:37-70`.
- **sha (priority 4):** hosted materialize verifies every listed file post-extract
  (`template_source.py:242,248-275`) and the self-host fetch verifies per-file
  sha + guards path traversal (`fetch_examples.py:113-153`). A corrupt/absent GCS
  object → honest `TemplateStoreUnavailable`/rollback, never a crash. Verified
  `test_gcs_corrupt_binaries_fails_sha_verify:335`.
- **Honest-offline (priority 5):** all three template routes map
  `TemplateStoreUnavailable`→503 (`api.py:839,850,870`); existing sessions use
  separate endpoints; the store keeps last-good within TTL
  (`template_source.py:186-202`).

## Findings (all LOW / acknowledged — none block deploy)

1. **LOW — global session-name namespace, now a hard 409 on normal create.**
   `create_session`'s unscoped pre-check (`session_manager.py:154`) rejects ANY
   tenant's existing name-derived id, so two users can't both create a session
   named e.g. "counter" (second gets 409, `api.py:778-779`), and the 409 is an
   existence oracle. This is a strict *improvement* over the prior silent
   cross-tenant adoption on multi-instance, and is documented in the plan §5
   deferred. Fix direction (deferred): per-tenant id namespacing or opaque ids.

2. **LOW — best-effort GCS purge is not failure-independent.** delete_session's
   purge and the fork's `delete_workspace` both call the same
   `store.delete_file`; a persistent store-delete failure defeats both, so a
   deleted session's manifest could survive and a same-user, same-name refork
   would hydrate the deleter's OWN prior (deleted) data. Same-tenant only, needs
   a durable delete failure; acceptable under documented orphan-GC-deferred.

3. **LOW — sha verify silently skipped on a malformed `.sc_binaries.json`.**
   `_verify_binaries` returns without verifying if the manifest fails to parse
   (`template_source.py:263-264`). The source-archive corruption that would
   damage the manifest normally fails `tar` open first → rollback, so exposure is
   marginal; consider treating an unparseable manifest present-but-invalid as a
   hard fork failure.

4. **INFO — deploy ordering.** Setting `TEMPLATES_BUCKET` (flips
   `templates_engine=gcs`, `settings.py:201`) before `publish_templates` uploads
   `index.json` makes the hosted gallery honest-503 until publish. Recoverable,
   no data loss; the Item-4 runbook already sequences publish-first — follow it.

## Suites run (this review)

`test_hosted_fork.py` · `test_template_source.py` · `test_split_bundle_binaries.py`
· `test_templates_fork.py` → **91 passed**. Regression sweep
(`test_chat_threads` · `test_create_session_with_project` · `test_projects` ·
`test_tenancy_redteam` · `test_mcp_tenancy_f1` · `test_persistence` ·
`test_session_rename_and_thread_count` · `test_model_selector`) → **97 passed**.
Zero new failures observed in the touched areas.

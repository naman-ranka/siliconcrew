# Review — templates-GCS / hosted-fork vs CLAUDE.md fundamentals

**Reviewer:** philosophy/fundamentals pass (read-only).
**Scope:** `git diff endgame..HEAD` on `worktree-templates-gcs-hosted-fork`
(~3.5k lines of code + ~1.2M lines of binary deletion), against CLAUDE.md
philosophy + 9 invariants + sharp edges + engine-selection idiom, and
`plans/templates-gcs-hosted-fork-implementation.md` (body + AUTHORITATIVE
Amendments A1–A18).

---

## VERDICT: ALIGNED (ship-ready; only MINOR notes below)

This is the simple, fundamental version — not machinery. The template gallery
is given the *same* self-host/hosted split as everything else in the repo, via a
`TemplateSource` factory that mirrors `get_workspace_provider` beat-for-beat.
Every new piece is one-sentence-defensible to a hardware designer. The two
CRITICAL/MAJOR defects in this area (cross-tenant fork leak+clobber A17,
concurrent-fork data loss A18) were found and fixed *inside this wave* with
regression tests proven to fail on pre-fix code — exactly the process CLAUDE.md
prescribes. I found no new CRITICAL or MAJOR correctness defect.

## SELF-HOST SACRED RULE: **PASS**

"Self-host must never need a cloud dependency installed." Verified end to end:

- `template_source.py:40` top-imports only `GcsObjectStore` (a *class object*),
  and `workspace_provider.py` has **no** top-level `google.*` import (lines
  24–37 are pure stdlib; SDK import is lazy inside `GcsObjectStore`). Importing
  `template_source` with `google-cloud-*` absent succeeds.
- `get_template_source()` (`template_source.py:324`) returns
  `LocalTemplateSource()` on the self-host branch and **never constructs**
  `GcsObjectStore`. Only the `gcs` branch instantiates it. No cloud object is
  built on the self-host path.
- `fork_from_template` lazy-imports `template_source` (`templates.py`, inside the
  function) — no import-time coupling; and `api.py`'s new top-level
  `import template_source` only pulls `workspace_provider`, already imported by
  `api.py` transitively.
- `scripts/fetch_examples.py` is **stdlib-only** (argparse/hashlib/io/os/sys/
  tarfile/tempfile/urllib; `json` imported inside a function) and imports
  **nothing** from `src`. `make fetch-bundles` runs with zero cloud deps and
  zero src-cloud coupling, over public HTTPS (`storage.googleapis.com`), no SDK,
  no auth.
- `publish_templates.py` lazy-imports `google.cloud.storage` inside `main()`
  (`:275`) — operator tool, off the service path.
- Self-host gallery works fully offline: `LocalTemplateSource.list()` delegates
  to `list_templates()` and can never raise `TemplateStoreUnavailable`.

## Invariant conformance (spot-checked in code)

- **INV 1 (manifest = source of truth):** preserved through the fork.
  `_clear_manifest_session_id` still runs on `dst`; the gcs source archive roots
  at the `workspace/` subtree (A9) so the fork's `manifest.json` lands at the
  workspace root exactly as the self-host `copytree` of `workspace/` produced it.
- **INV 2 (one tool registry, no drift):** `tool_catalog.py` untouched; the plan
  verified templates have zero tool/MCP consumers and none were added. The
  publish/split/fetch scripts + `index.json` are a *publish-time projection* of
  the bundles, not a hand-maintained parallel list; the one divergence
  (index `file_count`/`run_count` computed at publish vs local walk) is
  explicitly documented and accepted (A13). No registry drift.
- **INV 4 (honest state):** an unreachable store → `TemplateStoreUnavailable` →
  **503** ("Template gallery is unreachable"), *never* an empty 200
  (`api.py` list/get). Frontend renders a dedicated "couldn't reach the examples
  gallery" + Retry panel and only when `templatesError && templates.length===0`
  — cached templates win (`Launcher.tsx`). Missing GDS is distinguished from
  never-produced via `missing_binaries` in the layouts response
  (`api.py:/layouts`), surfaced as "GDS not present — re-run synthesis, or fetch
  the example binaries" (`LayoutArtifact.tsx`). Binary-less fork forces
  `netlist_path=None` rather than pointing at pre-synthesis RTL (A15,
  `templates.py:_run_has_split_out_netlist`). Nothing faked-as-empty.
- **INV 8 (tenancy, defense in depth):** list/get are READ-ONLY (route through
  the source, materialize no rows). `set_source_template` is owner-scoped
  (`_owner_clause`) in both stores. The bucket ACL (`main.tf`) is public
  `objectViewer` + backend SA `objectViewer` only — **no** public/user/SA write;
  no lifecycle-delete rule; `force_destroy=false`; separate bucket from
  workspaces. The A17/A18 fixes (atomic `insert_session` arbitrated by the
  `session_id PRIMARY KEY` — verified present in both sqlite `:130` and postgres
  `:594` — plus `delete_workspace`-before-`workspace_for` and cloud
  `delete_session` GCS purge) close a real cross-tenant leak+clobber, with 14
  targeted tests in `test_hosted_fork.py` including the concurrent race.
- **INV 9 (twelve-factor):** heavy binaries removed from git/image; source stays
  baked (A12 — `.dockerignore` correctly left as-is). Fetch cache + provider
  scratch + index TTL cache are caches, not truth. Any instance serves the
  gallery (GCS index) and completes a fork (materialize into `workspace_for`
  scratch → rewrites → `sync` LAST = atomic initial commit, D5/D7).

## Simplicity / proportionality

Each piece defends in one sentence, and none is over-built:

- `template_source.py` (365 lines, mostly docstrings): "the gallery gets the
  same engine split as workspaces." TTL cache (A14), post-extract ceiling (A9),
  per-file sha256 verify (A4) are each mandated by an amendment, not gratuitous.
- `metadata_store` additions: `insert_session` = "the DB PK arbitrates concurrent
  forks"; `set_source_template` = "durable copy of the forked-from chip for
  hosted list endpoints." Both minimal.
- `session_manager` `delete_session` GCS purge: "a deleted cloud session must
  leave no adoptable manifest for a name-derived refork" (D7/A17).
- The A17/A18 three-layer defense is warranted, not machinery: the adversarial
  pass reproduced destructive *data loss*, and CLAUDE.md explicitly calls for
  defense in depth on tenancy. Atomic insert is the root fix; the other two
  close distinct orphan windows.
- Operator scripts (split/publish/fetch) are proportionate to a one-time real
  migration.

## Deferral discipline

User-publish / community tier / moderation correctly **DEFERRED**, not
half-built: no write ACL for public/user/SA, no publish endpoints, `tier` is a
schema-only field ("official"), `community/` is a prefix mention only. Matches
plan §6 and the intent doc's Level-1 scope.

---

## Findings (all MINOR — none blocking)

**M1 — `allUsers objectViewer` also grants object *listing* on the templates
bucket.** `roles/storage.objectViewer` includes `storage.objects.list`, so the
bucket is anonymously listable, not just object-GET-able (`main.tf`
`templates_public_read`). Benign today (every object is a public official
template and the fetch path addresses by known id from the index). Worth a
one-line note in the migration runbook: if/when the deferred `community/` tier
lands, anonymous listing would expose unmoderated drafts — gate listing (or use
per-object public ACLs) before that wave, don't inherit this grant.

**M2 — Hardcoded default bucket in the OSS fetch path.**
`fetch_examples.py:46` defaults `DEFAULT_BASE_URL` to
`siliconcrew-siliconcrew-templates` (this project's bucket). It's honest and
overridable (`--base-url` / `$SILICONCREW_TEMPLATES_BASE_URL`), but for "an
excellent open-source base" a downstream forker's `make fetch-bundles` silently
points at the upstream project's bucket until they discover the override.
Consider documenting the override prominently in the README fetch section (Item
4 runbook) so the default reads as "the reference gallery" rather than a
surprise coupling.

**M3 — Redundant (harmless) double `delete_workspace` on cloud rollback.**
`_rollback_fork` (`templates.py`) calls `provider.delete_workspace(sid)` and
then `session_manager.delete_session(sid)`, which *also* purges the cloud
workspace (`session_manager.py` delete branch). Both are best-effort/idempotent,
so this is correctness-neutral — noted only so a future reader doesn't mistake
it for a missing guard. No change required.

**M4 — `create_session` gains a shared-store `get_session` round-trip on every
create (self-host included).** The new pre-check
(`session_manager.py:150`, `user_id=None`) is the intended cross-instance
namespace guard (A17) and the atomic `insert_session` is the real arbiter, so
the pre-check is only a friendly fast-path. Cost is one indexed PK SELECT per
create — negligible; flagged only for completeness. One behavior nuance: a
self-host row that exists without its on-disk dir now raises `FileExistsError`
where the old code would have recreated the dir. Arguably more correct
(insert_session would reject it anyway); no action needed.

## Verification done
- Confirmed no top-level `google.*` import in `workspace_provider.py` /
  `template_source.py`; local factory branch never builds `GcsObjectStore`.
- Confirmed `fetch_examples.py` stdlib-only, no `src` import.
- Confirmed `session_id TEXT PRIMARY KEY` in both sqlite and postgres schemas
  (A18 atomicity is real).
- Confirmed `_allocate_fork_session` catches `FileExistsError` → retries (loser
  path from A18).
- Confirmed `upsert_session` retained for `ensure_session`; `insert_session`
  used only by `create_session`.
- Enumerated `listLayouts` consumers (`store.ts` ×2, `LayoutArtifact.tsx`) —
  all updated to the new `{layouts, missing_binaries}` shape.

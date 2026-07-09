# Templates GCS + hosted fork — implementation-grade plan

**Status:** DRAFT pending second-agent review. Amendments section (end) is
AUTHORITATIVE over the body once review lands.
**Parent intent doc:** `plans/templates-gcs-and-hosted-fork.md` (commit 5bb2095) —
its §4 hard constraints are non-negotiable and repeated here only where they
bind a concrete decision.
**Grounding:** five parallel code sweeps (templates module/consumers, workspace
providers, bundle contents, frontend, tests/deploy) — every §1 claim of the
intent doc re-verified; corrections noted inline as **[Gnd]**.

---

## 0. Locked design decisions (with the evidence that locked them)

**D1 — The split line.** Move `synth_runs/*/orfs_results/**` and
`orfs_reports/*.webp` to GCS; keep EVERYTHING else in git.
Evidence: the 14 bundles are already `--prune-pnr`'d (no `.odb`, only
`6_final.gds`); weight is 19.4 MB `.gds` + 17.8 MB `.def` + 15.1 MB `.rtlil` +
8.5 MB `.webp` + 6.7 MB `.spef` + ~6.5 MB misc/netlists — all under
`orfs_results/` except the webp previews, and **no UI viewer reads any of it
except the `.gds`** (report viewer renders from `run_meta.json.summary_metrics`
only — `src/tools/design_report.py`; explorer prunes `synth_runs` —
`src/tools/manifest.py:96`). Keep in git: `orfs_reports/*.rpt` + `*.txt`
(1.4 MB, read by agent stage tools — `get_stage_status` uses `.rpt` as the
completion signal, `src/tools/synthesis_manager.py:137-143`), `orfs_logs/`
(0.24 MB), all `run_meta.json`/`index.json`/`completion.event`/`inputs/`,
RTL/TB/spec/manifest/trajectory. Result: repo `examples/` 75 MB → ~2.3 MB, and
a fresh clone still contains real readable designs + full run evidence (§4.2).
**No `.vcd` exists in any bundle** — waveforms are a non-issue for the split.

**D2 — Engine selection: `TemplateSource` mirrors `get_workspace_provider`.**
`LocalTemplateSource` (reads `examples/`, wraps today's code) vs
`GcsTemplateSource` (reads a bucket index + bundle archives; lazy cloud
imports). Selection lives in ONE factory. The engine is chosen by **explicit
config presence**: `TEMPLATES_BUCKET` set → `gcs`, else `local` — overridable
via `TEMPLATES_ENGINE`. Rationale: hosted must keep serving the baked-in
gallery UNTIL the one-time migration publishes the bucket — defaulting hosted
to `gcs` before the index exists would take the gallery down on deploy. This
is explicit-config-wins, resolved once in settings, not a silent fallback.

**D3 — Bucket layout (shaped for the deferred community tier, per §6):**
```
gs://<project>-siliconcrew-templates/
  official/index.json                      # the whole gallery, one small object
  official/bundles/<id>/source.tgz         # KB-scale: everything git keeps
  official/bundles/<id>/binaries.tgz       # the orfs_results/webp payload
```
A **separate bucket** — NOT a prefix of the workspaces bucket, whose terraform
lifecycle rule (`deploy/terraform/main.tf:77-80`) would silently DELETE
template objects. Public-read (allUsers objectViewer) so the self-host fetch
script needs no auth/SDK; admin-write only (backend SA gets objectViewer, not
write — listing stays READ-ONLY by construction). `community/` is a future
prefix; `tier` is an index field written as `"official"` now.

**D4 — Index shape.** One JSON object, `official/index.json`:
```json
{ "version": 1, "generated_at": "<aware-UTC ISO>",
  "templates": [ { "id","name","description","highlights","top_module",
                   "platform","source_note",          // template.json verbatim
                   "file_count","run_count",           // computed at publish
                   "files": [...], "conversations": [...],  // preview lists
                   "tier": "official",
                   "source": {"key","bytes","sha256"},
                   "binaries": {"key","bytes","sha256"} } ] }
```
Why persisted counts/lists: `_template_summary` computes `file_count`/
`run_count` by walking `workspace/` (`templates.py:103-116`) and `get_template`
walks for `files`/`conversations` — a hosted gallery has no local workspace to
walk, so publish-time computation is the only honest source. **[Gnd]**

**D5 — Hosted fork reuses the existing copy/rewrite logic; materialization is
NOT GCS-native.** The one blocking defect today is a path mismatch: fork copies
into `session_manager.get_workspace_path()` (local `base_dir` —
`session_manager.py:283-284`) while hosted tools read the
`CloudWorkspaceProvider` scratch from `workspace_for()` (`workspace_provider.py:526`).
The incremental sync's first-commit path handles a brand-new session with
pre-existing files (no index + no remote manifest → full scan → all blobs
upload → manifest LAST, `workspace_provider.py:619-714`). So the hosted flow is:
`create_session` → `dst = provider.workspace_for(sid)` → materialize bundle
into `dst` → existing rewrites → `sync(sid)` **last** (= atomic initial
commit) → return. **Gate on the workspace engine** (`_is_cloud_workspace()`,
i.e. `settings.workspace_engine == "cloud"` — `templates.py:72-83`), exactly
the predicate the current gate uses; NOT on `settings.hosted`. **[Gnd** — the
intent doc's `:785 settings.hosted` cite was slightly off: the selector is
`settings.is_cloud_workspace` at `workspace_provider.py:783`.**]**

**D6 — Hosted fork is all-or-nothing.** Source + binaries must both
materialize or the fork fails with an honest error and full rollback. A
partial bundle is a half-fork (§4.7 forbids); honest *degradation* (missing
GDS) is a SELF-HOST-without-fetch state, not a hosted one — hosted has the
bucket by definition.

**D7 — Rollback ordering beats GCS cleanup.** `delete_session`
(`session_manager.py:217-248`) removes local dir + DB rows + checkpoints but
has NO GCS delete (`metadata_store.py:325,688` are metadata-only) **[Gnd]**.
Because `sync()` is the LAST fork step and the manifest is written last within
sync, any failure before/inside sync leaves no adoptable workspace — at worst
orphaned content-addressed blobs (unreferenced, harmless, dedupe-shared). On
failure: best-effort scratch cleanup + `delete_session`, and best-effort
delete of the workspace manifest key if sync partially ran. Do NOT build a
full GCS workspace-GC in this wave (deferred with run retention/GC).

**D8 — Provenance must live in the metadata store (hosted chip fix).**
`read_provenance` is called at THREE api.py sites (`:722`, `:1294`, `:1397`)
via `get_workspace_path` — the wrong (local) path on hosted, so the "forked
from" chip is already silently broken there **[Gnd — real pre-existing bug]**.
List endpoints cannot afford `workspace_for()` hydration. Fix: persist
`source_template` (id, name, forked_at) into the session metadata row at fork
time; the three api sites read the store value first and fall back to the
workspace file (covers pre-existing self-host forks). The workspace
`.source_template.json` stays (run-directory-is-the-database; the workbench
still shows it as a file).

**D9 — `.sc_binaries.json` is the one split artifact, and it lives INSIDE
`workspace/`.** Written by the split tool at
`examples/<id>/workspace/.sc_binaries.json`:
`{"version":1,"files":[{"path","bytes","sha256"}]}` (workspace-relative
paths of every moved file). Three consumers: (a) the fetch script knows what
to fetch + verify; (b) forks copy it, so the backend can distinguish "run
never produced a GDS" from "binary not fetched" — the §3D honest state;
(c) the publish script uses it to build `binaries.tgz` deterministically.

**D10 — Fetch distribution: public GCS HTTPS, stdlib only.**
`scripts/fetch_examples.py` + `make fetch-bundles` download
`https://storage.googleapis.com/<bucket>/official/bundles/<id>/binaries.tgz`
via the `urllib` pattern already proven in `src/tools/stdcells.py:119-129`,
verify sha256 from `.sc_binaries.json`/index, extract with `tarfile`, and are
idempotent (skip files already present+matching). No GCS SDK, no auth, no new
dependency — self-host stays cloud-free (§4.1). GitHub Releases rejected:
publish-without-redeploy is the point, and a Release is a redeploy-shaped step.

---

## 1. Work items (one commit+push per item, in order)

### Item 1 — Split tooling + the split itself + fetch script (self-host intact)
Backend/scripts only. Self-host behavior after this item: identical except
heavy binaries are fetch-or-regenerate.

1. `scripts/split_bundle_binaries.py` (new): for each `examples/<id>`,
   classify per D1 (`workspace/synth_runs/*/orfs_results/**` +
   `workspace/**/orfs_reports/*.webp`), write
   `workspace/.sc_binaries.json`, and (with `--apply`) delete the binaries
   from the working tree. `--dry-run` prints the inventory + byte totals.
   Reuse nothing blindly: `_prune_pnr_intermediates` (`templates.py:485`) is a
   DIFFERENT, weaker filter — do not extend it; the split filter is new and
   lives in the script (export-time pruning stays as-is).
2. `scripts/fetch_examples.py` (new) + `Makefile` target `fetch-bundles`:
   per D10. `--base-url` overridable (env `SILICONCREW_TEMPLATES_BASE_URL`);
   default points at the official public bucket. Missing remote object →
   honest per-bundle "not published yet" message, non-zero exit only with
   `--strict`.
3. Run the split (`--apply`) on all 14 bundles; commit the deletion. Binaries
   remain recoverable from git history; the publish runbook (§3) reads them
   from `HEAD~`-era tree or a pre-split checkout via `--ref`.
4. Honest missing-binary state (§3D bullet 3, minimal version): the layouts
   listing path (`api.py:2492` `/layouts` and the run-scoped resolver used by
   `LayoutArtifact`) gains awareness of `.sc_binaries.json` — when a requested/
   expected `.gds` is listed there but absent on disk, the response says so,
   and `LayoutArtifact.tsx:55-62` adds one copy branch: "GDS not present —
   re-run synthesis (or fetch the example binaries)". Keep it to exactly this
   surface; no other viewer needs it (report/runs work from source; waveforms
   have no committed binaries at all).
5. `.dockerignore`: no change needed once binaries leave git (image lightens
   automatically), but verify no other rule breaks `examples/` source baking.

Tests (item 1): split tool dry-run/apply on a tmp fixture bundle
(`.sc_binaries.json` shape, only D1 patterns moved, idempotence); fetch script
against `file://`/local-HTTP fake (sha256 verify, idempotent re-run, honest
missing-object handling); existing `test_templates_fork.py` stays green
(its fixtures are synthetic; `test_shipped_sync_fifo_bundle_is_forkable`
unaffected — sync_fifo has no binaries); NEW: fork of a split bundle without
fetched binaries succeeds and degrades honestly (`netlist_path` re-derives to
None via `_find_netlist` — no crash, runs pane intact); layouts endpoint
missing-vs-never-produced distinction.

### Item 2 — TemplateSource abstraction + GCS index + dynamic hosted gallery + honest offline
1. `src/platform_engines/template_source.py` (new): `TemplateSource` protocol
   (`list()`, `get(id)`, `materialize(id, dst_dir)`) + `LocalTemplateSource`
   (delegates to the existing `templates.py` listing/preview and
   `copytree_guarded` materialization — behavior-identical) +
   `GcsTemplateSource` (index via `GcsObjectStore.get_file`
   (`workspace_provider.py:211-219`), bundles via `get_tree`; lazy imports;
   raises `TemplateStoreUnavailable` on any network/objects failure — never
   returns an empty list for an error). In-process index TTL cache (60 s).
   Factory `get_template_source()` per D2 + `set_template_source()` test seam
   (mirror `set_workspace_provider`, `workspace_provider.py:794-797`).
2. Settings: `templates_engine` ("local"|"gcs"), `templates_bucket`
   (`TEMPLATES_BUCKET`), threaded per the existing storage block
   (`settings.py:70-73`, `get_settings` `:210-212`). Fail-fast at the factory:
   `templates_engine=gcs` with empty bucket → raise at first use (surfaced as
   the honest 503, logged at startup) — mirroring where the postgres guard
   lives (engine builder, not settings).
3. REST: `GET /api/templates` + `GET /api/templates/{id}` route through the
   factory. `TemplateStoreUnavailable` → **503** with a distinct detail
   ("Template gallery is unreachable") — never an empty 200 (§3D bullet 1).
   Both remain PUBLIC and READ-ONLY (no row materialization — invariant 8).
4. `scripts/publish_templates.py` (new, admin/offline): builds
   `source.tgz` + `binaries.tgz` per bundle (from a pre-split ref via `--ref`,
   or a fetched working tree), computes the D4 index entries (counts + preview
   lists from the FULL bundle), uploads via
   `GcsObjectStore(bucket, prefix="official")` (`put_file`/`put_tree`,
   `workspace_provider.py:203-219`), writes `index.json` LAST (atomic publish).
   Auth: application-default or service-account file (the `roll_cloudrun.py:14`
   pattern) — an operator tool, not a service path.
5. Terraform: `google_storage_bucket.templates`
   (`${project_id}-siliconcrew-templates`, uniform access, NO lifecycle-delete
   rule), allUsers `objectViewer`, backend SA `objectViewer` only;
   `TEMPLATES_BUCKET` env on the backend service (`main.tf:227-420` block).
6. Frontend honest offline (the ONE real gallery change): `Launcher.tsx`
   consumes `templatesError`/`templatesLoading` (stored but never read —
   `store.ts:722-735`) and renders an "unable to connect" + Retry panel when
   `templatesError && templates.length === 0`, structurally mirroring the
   `sessionsError` block (`Launcher.tsx:489-497`). Cached templates stay
   visible on refresh error (store already keeps last-good). Both gallery
   placements (`Launcher.tsx:498-509`, `:644`).

Tests (item 2): `GcsTemplateSource` over `InMemoryObjectStore`
(`workspace_provider.py:126-167`) — list/get from index, `materialize`
extracts source+binaries, unreachable store → `TemplateStoreUnavailable`;
REST 503 body on store failure (TestClient + injected failing source);
read-only check (list/get create no sessions/threads rows); settings
engine-resolution matrix (bucket set/unset × explicit override); publish
script index-shape golden test against a tmp bundle (no live GCS — fake
store); vitest: unable-to-connect panel renders + Retry calls
`loadTemplates`, cached-templates-persist case; e2e: mock 503 → panel.

### Item 3 — Hosted fork (headline) + provenance durability + tenancy proof
1. Refactor `fork_from_template` (`templates.py:320-370`): keep the exact
   sequence and rewrites, parameterize the two engine-dependent pieces:
   - **destination**: `_is_cloud_workspace()` → `get_workspace_provider().workspace_for(sid)`
     (empty scratch for a fresh session — `workspace_provider.py:550-553`);
     else `session_manager.get_workspace_path(sid)` (unchanged).
   - **materialization**: `get_template_source().materialize(id, dst)` —
     local = today's `copytree_guarded`; gcs = `get_tree(source)+get_tree(binaries)`
     with the same `max_bytes`/`max_files` guards applied post-extract.
   Then the UNCHANGED rewrites (`_clear_manifest_session_id`,
   `_rewrite_run_meta_netlists`, `_write_provenance`) run on `dst`, and on
   cloud workspaces `provider.sync(sid)` runs LAST (D5/D7). **Delete the
   `TemplatesUnavailable` raise** (`templates.py:337-341`); keep the exception
   class for compat until nothing references it, then remove with its 400
   mapping (`api.py:836-837`) and the frontend test for the alert message
   (`templatePreview.test.tsx:52-60`) is updated to a generic-failure case
   (the `role="alert"` surface itself stays — it now shows real errors).
2. Rollback per D7: existing `except BaseException` block extended — scratch
   dir cleanup + `delete_session` + best-effort workspace-manifest-key delete.
3. Provenance durability per D8: metadata store gains `source_template`
   (JSON text column, nullable) on sessions — sqlite + postgres, following the
   existing migration idiom in `metadata_store.py` (verify exact mechanism in
   review); `fork_from_template` writes it via session_manager; the three
   api.py `read_provenance` sites (`:722`, `:1294`, `:1397`) read
   store-first/file-fallback.
4. REST error mapping: `TemplateStoreUnavailable` during fork → 503;
   guard-ceiling/other failures → 500 with honest detail (rollback already
   ran). `require_signed_in` + `user_id=_uid(identity)` unchanged — the fork
   is owned by the TRUE forking user by construction (`api.py:822-838`).

Tests (item 3): forced-hosted harness — `set_workspace_provider(
CloudWorkspaceProvider(InMemoryObjectStore(), tmp_scratch))` +
`set_template_source(fake gcs source)` (patterns:
`test_synth_hosted_durability.py:31-51`, `test_mcp_tenancy_f1.py:31-58`):
- happy path: fork → files in scratch, manifest committed in fake store
  (sync ran, manifest key present), `sessionId` cleared, `netlist_path`
  re-derived, provenance file + store field, Chat 1 seeded
  (`ensure_default_thread`), session owned by alice
  (extend `test_fork_is_owned_by_caller_not_template`,
  `test_templates_fork.py:207-213`), invisible to bob.
- rollback: materialize failure / sync failure → `delete_session` ran, no
  session row, no workspace manifest key in the fake store.
- all-or-nothing: missing `binaries.tgz` → fork fails honestly, rollback.
- tenancy red-team (model `test_tenancy_redteam.py`): no path writes another
  user's workspace prefix or the templates bucket (fake store asserts write
  keys all under `workspaces/<new-sid>`; template source saw zero writes).
- provenance: hosted GET/list/PATCH responses carry `source_template` from
  the store (fake store, no local file).
- self-host regression: entire existing fork suite green, zero behavior change.

### Item 4 — Migration runbook + docs (no code)
`docs/` (or plan appendix): operator steps in SAFE order — (1) terraform apply
(bucket + env), (2) `publish_templates.py --ref <pre-split>` → verify index +
one bundle fetch, (3) deploy image with `TEMPLATES_BUCKET` set (gallery flips
to gcs engine), (4) live-verify hosted fork (the §5 criteria: fork Simon,
open files, see trajectory, fresh chat). Self-host README: `make
fetch-bundles` + the honest degradation story. **Actual execution against the
real bucket is owner-run** (needs prod credentials + terraform apply — outward
-facing; not done by this wave's implementer without explicit go-ahead).

---

## 2. Consumer sweep (every touchpoint, verified)

| Surface | Where | Change |
|---|---|---|
| REST list/get | `api.py:807-819` | route via factory; 503 on store failure |
| REST fork | `api.py:822-838` | error mapping; gate lift is inside templates.py |
| `read_provenance` sites | `api.py:722, 1294, 1397` | store-first/file-fallback |
| Tool registry / MCP | — | **NONE — templates have zero tool/MCP consumers [Gnd]**; do not add any |
| `templates.py` | `:62-208` listing/preview, `:320-370` fork | Local source wraps listing; fork refactor per Item 3 |
| `bundles.py` | `copytree_guarded :40`, `redact_host_paths :131` | unchanged (reused) |
| `session_manager.py` | `:133 create`, `:217 delete`, `:283 get_workspace_path`, `:298 ensure_default_thread` | unchanged; fork stops using `:283` on cloud |
| `workspace_provider.py` | `:526 workspace_for`, `:597 sync`, `:170 GcsObjectStore`, `:126 InMemoryObjectStore`, `:773 factory`, `:794 test seam` | unchanged (reused); do NOT touch sync internals |
| `metadata_store.py` | sessions schema ×2 stores | + `source_template` column (Item 3) |
| `settings.py` | storage block `:70-73`, `get_settings :210-212` | + `templates_engine`, `templates_bucket` |
| Frontend store/api | `store.ts:722-750`, `api.ts:120-133` | unchanged shapes; Launcher consumes error state |
| `Launcher.tsx` | `:363-388, :489-509, :644` | unable-to-connect panel |
| `TemplatePreview.tsx` | `:41-75, :201-221` | unchanged (alert surface reused) |
| `LayoutArtifact.tsx` | `:29-62` | one copy branch (missing-binary) |
| `types/index.ts` | `:28-51` | additive optional fields only (`tier?`) |
| Tests | `test_templates_fork.py` (473 lines), `templatePreview.test.tsx`, `exampleCard.test.tsx`, `e2e/templates.spec.ts`, `breadcrumb.test.tsx` | extend per items; hosted-gate tests become hosted-fork tests |
| `scripts/export_bundle.py` | export path | unchanged (authoring stays self-host) |
| Dockerfile/.dockerignore | `:81 COPY . .` | no change; image lightens via git |
| Terraform | `main.tf:68-81, 161-165, 227-420` | new bucket + env (Item 2) |
| Docs/README, Makefile | — | fetch-bundles, runbook (Items 1/4) |

## 3. Do-NOT fences
- Do NOT import any cloud dependency outside lazy blocks in
  `GcsTemplateSource`/publish script; self-host must run with `google-cloud-*`
  absent (sacred, §4.1).
- Do NOT reuse the workspaces bucket or its prefix for templates (lifecycle
  rule deletes; also keeps public-read isolated to template content).
- Do NOT grant the backend SA write on the templates bucket; do NOT build
  user-publish, moderation, community prefix content, or public-write ACLs
  (§6 — schema room only: `tier` field, `official/` prefix).
- Do NOT let list/get materialize rows or write anything (READ-ONLY browsing).
- Do NOT return an empty gallery on store failure — distinct error → 503 →
  "unable to connect" (never fake-empty).
- Do NOT touch `CloudWorkspaceProvider` sync/materialize internals, the tool
  registry/`tool_catalog.py`, or the `run_id` model.
- Do NOT move `.rpt`/`orfs_logs`/`run_meta.json`/`inputs/` out of git (D1).
- Do NOT auto-fetch binaries on import/startup — explicit `make fetch-bundles`
  only.
- Do NOT change the self-host fork's observable behavior (same files, same
  rewrites, same rollback).
- Do NOT call `.timestamp()` on naive datetimes anywhere new (aware UTC only,
  as `_write_provenance` already does).

## 4. Full gates (unchanged commands, zero new failures)
Backend pytest (CLAUDE.md invocation + fixture-restore), frontend
`tsc --noEmit` / `vitest run` / playwright (`PW_EXECUTABLE`) / `next build`.
Then adversarial review of the finished diff; fixes with regression tests
proven to fail pre-fix.

## 5. Deferred (documented, not dropped)
User publish + community tier + moderation (per intent §6); GCS workspace GC
for orphaned blobs (D7); staleness UI for the gallery TTL cache; per-bundle
thumbnails in the index; hosted `read_provenance` file-only forks backfill.

## 6. Open items for the review pass (verify in code before build)
1. Exact migration idiom in `metadata_store.py` for adding the
   `source_template` column to BOTH stores (and what `list_sessions` row
   mapping needs).
2. `GcsObjectStore.get_tree`/`put_tree` archive format — confirm plain
   tar(.gz) consumable by stdlib `tarfile` for the fetch script, or whether
   fetch should use per-file objects instead.
3. Whether `workspace_for()` on a brand-new session is callable BEFORE any
   request-lifecycle wiring (locks, scratch creation) from the REST fork
   handler's thread context.
4. The layouts-listing change surface (Item 1.4): confirm the exact resolver
   `LayoutArtifact` hits and the cheapest honest signal shape.
5. `TemplatesUnavailable` removal blast radius (frontend copy asserts the
   message text?).
6. Publish script `--ref` mechanics (git archive vs checkout) on Windows.

---

## Amendments (AUTHORITATIVE — override the body wherever they conflict)

Second-agent review verdict: implementation-ready AFTER these amendments.
Architecture confirmed sound (engine-selection mirroring, READ-ONLY listing,
owner-scoped fork, separate bucket vs the `main.tf:77-80` lifecycle-delete,
zero tool/MCP consumers, `_safe_extract` zip-slip coverage, guard ceilings ≫
bundle sizes).

**A1 [CRITICAL] — Narrow the split line to heavy file TYPES.** D1's "no UI
viewer reads orfs_results except .gds" was an inaccurate read:
`_STAGE_COMPLETION_MARKERS` (synthesis_manager.py:136-144) keys stage
completion off files UNDER `orfs_results` (`route→5_route.sdc`,
`place→3_place.odb`, …; `_find_stage_completion_marker` :165-178), and
`get_ppa_metrics` (get_ppa.py:21-34) recursively scans it;
`design_report.py:10,21` falls back to get_ppa (not "summary_metrics only").
SPLIT = `**/orfs_results/**/*.{gds,def,spef,rtlil}` + synthesized netlist
`.v` under orfs_results + `orfs_reports/*.webp`. KEEP `.sdc/.json/.guide/
.tcl/.txt` (tens of KB) so stage-status/reconcile/PPA are byte-identical on
self-host-without-fetch. ADD a parity test: fork a split bundle (no binaries)
and assert get_ppa/get_stage_status/design-report outputs identical to
pre-split.

**A2 [MAJOR] — Fork off the event loop.** `fork_template` (api.py:822-838) is
`async def` calling `fork_from_template` synchronously; all other blocking
api.py ops use `asyncio.to_thread` (:1261, :1524, :2476, :2489). Wrap the
fork call in `asyncio.to_thread` in Item 3.

**A3 [MAJOR] — Object naming is `.tar.gz`, not `.tgz`.**
`GcsObjectStore._blob` (workspace_provider.py:189-191) appends `.tar.gz` and
prepends the prefix. Index stores suffix-less store-relative keys
(`bundles/<id>/source`); `GcsTemplateSource` uses
`GcsObjectStore(prefix="official").get_tree(key)`; fetch builds
`https://storage.googleapis.com/<bucket>/official/<key>.tar.gz`.

**A4 [MAJOR] — Verify per-file sha256 post-extraction**, from
`.sc_binaries.json` (archives are gzip-mtime-nondeterministic —
`_tar_dir_to_bytes` workspace_provider.py:94-100). Index archive hashes
advisory only. Per-file verify is also what makes fetch idempotence work.

**A5 [MAJOR] — Provenance needs a NEW store setter.** `upsert_session` has a
fixed COALESCE column list (metadata_store.py:250-266, 628-643); no arbitrary-
column write path and no JSON field to piggyback. Work: (a) SQLite column via
`_migrate_columns` (:153-179) `ADD COLUMN source_template TEXT`; Postgres
`ADD COLUMN IF NOT EXISTS` in init_schema (mirror :574-577); (b) new
owner-scoped `set_source_template(session_id, value, user_id)` on BOTH stores
+ the MetadataStore Protocol (:34-75); (c) SessionManager passthrough;
(d) fork calls it after `_write_provenance`. Reads flow free (SELECT *).

**A6 [MAJOR] — Mixed-engine policy (RULING).** Hosted-workspace +
local-templates (deployed split image, no TEMPLATES_BUCKET yet) would produce
a binary-less hosted fork, which D6 forbade. Ruling: **D6 is scoped to the
gcs source** — a source must deliver everything it PROMISES. `gcs` source:
index promised binaries → missing/failed `binaries` archive = fork fails +
rollback (all-or-nothing). `local` source: copies what is present (existing
semantics) → binary-less fork is HONEST degradation, on self-host or hosted
alike (GDS is regenerable; viewers already honest). Drop D6's "never on
hosted." ADD mixed-combo tests: cloud-workspace+local-source AND
local-workspace+gcs-source (both coherent: destination and materialization
are independent axes).

**A7 [MAJOR] — Layouts honest signal is a response-shape change (do it
properly).** GET `/api/workspace/{sid}/layouts` (api.py:2492-2509) returns
`List[str]`; `listLayouts` types `string[]` (api.ts:291-292). Change the
response to `{"layouts": [...], "missing_binaries": [...]}` (paths from
`.sc_binaries.json` entries absent on disk, `.gds` only), update `api.ts`,
`LayoutArtifact.tsx` (new copy branch "GDS not present — re-run synthesis, or
fetch the example binaries"), any other listLayouts consumer, and the e2e
mock (templates.spec.ts:112). Enumerate consumers before editing.

**A8 [MAJOR] — Tests that assert the OLD gate.**
`test_fork_hosted_is_gated` (test_templates_fork.py:241-247) and
`test_api_fork_hosted_400` (:468-469) FAIL after the gate lift — rewrite both
in Item 3 as hosted-fork-succeeds tests. Frontend blast radius of
`TemplatesUnavailable` removal = templatePreview.test.tsx:52-60 mock string
only (the `role="alert"` surface stays; no production code asserts the text).

**A9 [MAJOR] — source archive roots at the `workspace/` SUBTREE.** Session
workspaces must not contain `template.json` or a nested `workspace/` dir
(self-host copies `examples/<id>/workspace/` — templates.py:346,355-357).
`template.json` content is index-only. `get_tree` has NO size guard
(copytree_guarded enforces during copy) → the post-extract max_bytes/
max_files guard is NET-NEW code; tar traversal is covered by `_safe_extract`
(workspace_provider.py:116-123 — NOT `_guard_member`, that's the manifest
path). Ceilings hold: largest bundle 15 MB ≪ 512 MiB / 20k files
(bundles.py:26-27).

**A10 [MINOR] — Open items #2/#3 resolved.** `workspace_for` on a brand-new
sid is SAFE from the REST handler: no manifest → `os.makedirs(scratch)`
return (workspace_provider.py:532-553); fresh per-session lock; no
request-lifecycle middleware to race (only CORS api.py:490 + MCP :575). Must
still be off-loop (A2). Archive format = stdlib `tarfile` w:gz/r:gz,
recursive top-level arcnames — fetch can urllib+tarfile (with A3 naming).

**A11 [MINOR] — Publish `--ref` = `git worktree add --detach <tmp> <ref>`**,
read via FS, `git worktree remove`. Publish auth = ADC /
GOOGLE_APPLICATION_CREDENTIALS via `storage.Client()` (roll_cloudrun.py:14 is
a different mechanism — service_account + AuthorizedSession REST; don't cite
it as the pattern).

**A12 [MINOR] — .dockerignore is correct as-is**: `workspace/`+`workspace*/`
match context-root only, so `examples/<id>/workspace/` stays baked. Do NOT
"fix" it to `**/workspace/` — that would silently exclude all bundle sources.

**A13 [MINOR] — Preview hygiene.** Filter `.sc_binaries.json` and
`.source_template.json` out of `_shallow_file_preview` and publish-time file
lists. `file_count`/`run_count` divergence local-vs-index (source-only vs
full) is accepted and documented.

**A14 [MINOR] — Index TTL cache is last-good/SWR by declaration**: store
outage serves cached entries up to TTL then 503s; that staleness contract is
intended, not accidental.

**A15 [MAJOR, discovered during Item 1] — netlist_path re-derivation can land
on RTL source in a binary-less fork.** Real bundles keep
`synth_runs/*/inputs/*.v` in git, and `_find_netlist`
(synthesis_manager.py:1020) scans BOTH `orfs_results` AND `inputs` — so
forking a split bundle WITHOUT fetched binaries re-derives `netlist_path` to
the RTL input, not None. That run_meta would then claim a "netlist" that is
actually pre-synthesis RTL — dishonest for gate-level sim. Item 3 rule: in
`_rewrite_run_meta_netlists`, when the run's `.sc_binaries.json` lists any
`orfs_results/**/*.v` that is absent on disk, set `netlist_path = None`
(gate netlist is split-out, not merely never-produced). Do NOT change
`_find_netlist` itself (shared with live synthesis).

**A16 [MINOR, applied post-Item-1] — Split filter tightened**: also move
`orfs_results/**/mem.json` (unread yosys memory dump, 1.7 MB worst case) and
`orfs_results/**/*.guide` (route guides, no consumer). A1's blanket
"keep .json/.guide" was overbroad; the principle is keep-what-a-reader-
consumes, and no reader touches these. `design_metrics.json` and all stage
`.sdc`/`.rpt`/logs remain in git.

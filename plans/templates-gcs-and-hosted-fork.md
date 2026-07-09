# Templates: source-in-git / binaries-in-GCS / dynamic gallery / hosted fork — requirements & intent

**Status:** DRAFT for review. This is a *direction* document — it states the
problem, the current-state evidence, the intent, and (heaviest section) the hard
constraints. It deliberately does **not** prescribe the implementation. The
reviewing agent turns it into an implementation-grade plan (full file:line
consumer sweep, test list, do-NOT fences) per the CLAUDE.md process — and **every
"reuse existing X" claim below must be re-verified in code before building**
(unverified reuse claims were wrong repeatedly here). The implementer reasons
about the mechanism; the §4 constraints are non-negotiable.

**Owner intent, verbatim in spirit:** shift the heavy template artifacts to GCS
so the repo stays light and we can publish/update examples without a redeploy —
BUT keep the design fundamentally sound: self-host must keep working, the
open-source repo must stay genuinely useful, forking must work on the DEPLOYED
app (not just self-host), and every offline/missing state must be *honest*, never
faked or broken. Build it "very, very strong" on the fundamentals. The
community/user-publish direction is noted for the future but is **NOT a priority
now** — the implementation must simply not *preclude* it.

---

## 1. Current state (evidence)

**Where templates live today:** committed bundle directories under `examples/`
(14 bundles). Discovery reads the local dir: `default_examples_dir()`
(`src/utils/templates.py:62`) → `list_templates()` (`:134`) / `get_template()`
(`:173`); REST at `GET /api/templates` (`api.py:807`), `GET
/api/templates/{id}` (`:813`). Because they're in the repo, they're **baked into
the backend Docker image** → adding/updating a bundle needs commit → image
rebuild → redeploy (done exactly that this session).

**Forking is self-host ONLY today (the gap this closes):** `fork_from_template()`
(`src/utils/templates.py:320`) hard-gates on `_is_cloud_workspace()` (`:72`) and
raises `TemplatesUnavailable` (`:337-338`). On the deployed app the "Fork this
example" button therefore returns an honest 400 — *"Templates are available in
self-host today; the hosted gallery is a later wave"* — surfaced as a
`role="alert"` above the button (verified live this session, rev 00056). So
hosted visitors can **browse + preview** but **not fork**. That deferral was the
Wave-11 A5 hard-gate: the hosted GCS-copy materialization path was never wired.

**The prerequisite now exists:** the hosted workspace persistence is now
**incremental content-addressed sync** (`CloudWorkspaceProvider`,
`workspace_provider.py:245`) — per-file blobs + a manifest committed last. This
is exactly the persistence a hosted fork needs (materialize bundle → session
scratch → persist to the user's own GCS workspace). Before this session there was
no clean path; now there is.

**Provider selection (the sacred idiom):** `get_workspace_provider()`
(`workspace_provider.py:773`) returns `CloudWorkspaceProvider` when
`settings.hosted` (`:785`) else `LocalWorkspaceProvider` (`:790`). Template
loading MUST follow this same self-host/hosted engine-selection.

**Export/sanitize already exists** (for the future user-publish path):
`export_session_bundle()` (`:524`) + `_sanitize_exported_workspace()` (`:384`,
called `:571`) — packages a workspace and strips author host-paths (F16 broadened
this). Noted here only so the future direction reuses it rather than reinventing.

---

## 2. The problem
1. **Repo weight / redeploy-to-publish.** Heavy binaries (GDS, ODB/DEF/SPEF, ORFS
   run dirs, VCDs) in the repo bloat clones and force a full image rebuild+deploy
   to add or update an example. (Already partly mitigated — bundles are pruned to
   ~2 MB via `--prune-pnr` — but it grows with every bundle.)
2. **Hosted fork is off.** The deployed showcase is half-delivered: visitors can
   look but not fork, which is the exact opposite of the gallery's purpose.

---

## 3. Intent — the design (direction, not prescription)

### 3A. Split *source* (git) from *heavy binaries* (GCS) — the core decision
A bundle is not indivisible. Keep the **tiny source** in git — `spec.md`, RTL
`.v`, testbench, `manifest.json`, the `attempt_events` trajectory (tens of KB,
the readable/educational/open-source value, and what a re-run needs). Move the
**heavy binaries** — GDS, ODB/DEF/SPEF, ORFS run dirs, VCD waveforms — to GCS,
with a **fetch script** (`fetch_examples.py` / `make fetch-bundles`) that pulls
them for self-host on demand. This resolves the self-host and open-source
tensions instead of trading them away: repo stays light, a clone still contains
real designs, and self-host works with **no GCS** (it has the source and can
*re-run synthesis to regenerate the GDS*).

### 3B. Dynamic gallery from a GCS index
Hosted gallery reads a small **index object** from GCS (all templates + metadata)
and renders from it — publish/update a bundle by uploading to GCS, no redeploy.
Fork then pulls the specific bundle's source+binaries. (No bucket-scan per
request — one small index fetch.)

### 3C. Hosted fork enabled (the deferred A5 GCS-copy path) — first-class deliverable
Lift the `_is_cloud_workspace()` gate **only after** wiring the hosted
materialization: fetch bundle → materialize into the new session's scratch
workspace → persist via the incremental sync to the *forking user's* GCS
workspace → seed a fresh empty chat thread (as self-host already does). Self-host
fork path stays as-is.

### 3D. Honest offline / missing states (invariant 4)
- GCS/index unreachable → gallery shows **"unable to connect"**, NOT an empty or
  fake gallery. Only *browsing/forking new* templates is affected.
- A session already forked keeps working when the template GCS is down — its
  files live in the *user's own* workspace, independent of the template store.
- Self-host without fetched binaries → viewers show **"GDS not present — re-run
  synthesis"** (honest degradation), never a broken/empty viewer.

---

## 4. Hard constraints (NON-NEGOTIABLE — build "very strong" on these)
1. **Self-host never needs a cloud dependency (sacred).** Template loading uses
   the same engine-selection as `get_workspace_provider`: a **local source dir**
   is the self-host template provider; **GCS** is the hosted one. Additive, never
   a replacement. Self-host with no network must list, preview, fork, and run
   templates using only repo source (binaries optional, via fetch or re-run).
2. **The open-source repo stays genuinely useful.** A fresh clone must contain
   real, readable designs (source + trajectory), not just manifests. Only the
   regenerable heavy binaries may live outside git.
3. **Tenancy (invariant 8) — the F1-class area, treat with paranoia.** The fork
   must seed the workspace/rows for the **TRUE forking owner**, not the caller/
   anonymous (the documented ensure-paths sharp edge). Gallery listing +
   index-read stay **READ-ONLY** — never materialize rows. No path lets one user
   read/overwrite another's workspace or the official templates.
4. **Honest state (invariant 4).** Offline, not-fetched, partial-bundle, and
   fork-in-progress all show the truth (see §3D). No faked gallery, no broken
   viewer masquerading as empty.
5. **Twelve-factor (invariant 9).** Templates stop being baked into the image
   (improves this). Nothing durable assumed on instance disk; the fetch-script
   cache and any scratch are caches, not truth. Any hosted instance can serve the
   gallery and complete a fork.
6. **Manifest = source of truth (invariant 1).** The bundle `manifest.json`
   remains authoritative for the forked session's files/roles/tops.
7. **Sharp edges the hosted fork MUST get right** (from CLAUDE.md + the templates
   amendments): rewrite the absolute `netlist_path` in every copied `run_meta`;
   clear/rewrite `manifest.json` `sessionId` (reconcile won't overwrite it);
   preserve provenance (`.source_template.json`); `shutil.copy2` mtime handling;
   and roll back cleanly (delete_session) on any fork failure so a half-fork never
   survives.
8. **Behavior parity self-host vs hosted.** A fork produces the same resulting
   session (files, runs, provenance, seeded chat) on both — only the
   materialization mechanism differs.

---

## 5. Success criteria
- **Repo light:** a clone contains only source (KB-scale bundles); heavy binaries
  are fetched or regenerable.
- **Publish without redeploy:** uploading a new bundle + index entry to GCS makes
  it appear in the hosted gallery with no image rebuild.
- **Hosted fork works:** on the deployed app, forking a gallery example creates a
  real owner-scoped session with the design materialized + a fresh chat — verified
  live (e.g. fork the Simon game, open its files, see the trajectory).
- **Self-host intact:** with no network, list/preview/fork/run all work from repo
  source; a missing GDS reads as "re-run synthesis," not broken.
- **Honest offline:** GCS down → "unable to connect" on new browsing; existing
  sessions unaffected.
- **Tenancy proven:** a test shows a forked workspace is owner-scoped and no
  cross-user or user→official write/read path exists.
- Full gates green; no new failures; self-host behavior/timings unchanged.

---

## 6. Non-goals now / future direction (noted so the design doesn't preclude it)
Explicitly **deferred, not a priority** — but the storage layout (official prefix,
per-bundle index entries, tier/provenance metadata) should be shaped so these
drop in later without a rewrite:
- **User-published templates ("publish my session to the gallery").** Would reuse
  `export_session_bundle` + `_sanitize_exported_workspace`; needs its own wave for
  the safety surface (users fork+RUN others' RTL/TB → sandboxing, size/quota caps,
  moderation) and **official-vs-community separation** (admin-write-only official
  prefix + a `tier`/`provenance` field + honest "community, unverified"
  attribution). Design the index/prefix scheme now to leave room for a `community/`
  space and a `tier` field; do NOT build the publish path, the moderation, or the
  public-write ACLs in this wave.
- **Growing the official gallery over time** — the whole point of no-redeploy
  publishing; just means more index entries, no new mechanism.

DO-NOT (this wave): user upload/publish, public-write buckets, moderation, real-
time anything. Keep it to: source/binary split, GCS index + fetch script, dynamic
official gallery, hosted fork, honest states.

---

## 7. Open questions for the design/review pass
- Where does the split line sit exactly — which files are "source" (always in
  git) vs "binary" (GCS/fetch)? (Proposed: everything under the run dirs'
  `orfs_results`/`orfs_logs`/`*.gds`/`*.vcd` = binary; spec/RTL/TB/manifest/
  attempt_events/run_meta = source. Verify against what the viewers actually
  need.)
- The GCS index shape (one index object vs per-bundle metadata) and how the
  self-host local provider mirrors it without GCS.
- Hosted fork: can the existing `fork_from_template` copytree be reused as-is once
  the source is on the instance (baked/fetched) + the incremental sync persists
  the scratch, or does the materialization need to be GCS-native? (Verify: is the
  bundle source present on hosted instances today via the image, or must it be
  fetched from GCS first?)
- Fetch-script distribution: pull binaries from the same public GCS bucket, or a
  GitHub Release? Auth for the public read.
- Migration: the 14 existing repo bundles → split source/binary + upload binaries
  + build the index, without losing provenance or breaking the current
  self-host fork.

---

## 8. Suggested sequencing (reviewer may re-order)
1. Source/binary split of the existing 14 bundles + the fetch script (self-host
   still 100% functional; repo lightens). No hosted behavior change yet.
2. GCS index + dynamic hosted gallery listing (publish-without-redeploy) + honest
   offline. Read-only.
3. **Hosted fork** — wire hosted materialization, get the §4.7 sharp edges right,
   lift the gate, prove tenancy. This is the headline deliverable.
4. (Future, separate waves — not now) user publish + official/community + moderation.

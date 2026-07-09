# Review — templates-GCS / hosted-fork vs requirements

**Scope:** `git diff endgame..HEAD` on `worktree-templates-gcs-hosted-fork`
(19 commits, b617473..cc025da). Authoritative requirements:
`plans/templates-gcs-and-hosted-fork.md` (§3–§6). Implementer plan:
`plans/templates-gcs-hosted-fork-implementation.md` (Amendments A1–A18 authoritative).

## VERDICT

**Requirement-complete and fundamentally sound.** Every §3 intent (A source/binary
split, B dynamic GCS gallery + publish-without-redeploy, C hosted fork enabled, D
honest offline/missing) is delivered, and each §4 hard constraint is satisfied with
strong, substantive test proof (114 targeted tests pass; the tenancy / offline /
hosted-fork red-team cases are real, not vacuous). §6 non-goals are correctly NOT
built while leaving the documented schema room. The engine-selection idiom is
mirrored exactly, listing is read-only by construction (IAM + code), and the
adversarial-review fixes (A17 cross-tenant leak+clobber, A18 concurrent race) are
present with regression tests that assert no-clobber / no-leak / distinct-owned-id.

Only defect found is **doc-honesty (MINOR)**: the `templates.py` module docstring
still declares the feature self-host-only. No functional gap. No over-building.

## Requirement conformance table

| Requirement | Met? | Evidence (file:line) | Gap / note |
|---|---|---|---|
| **§3A** split line correct (source in git; heavy binaries out) | **Yes** | `scripts/split_bundle_binaries.py:55-78` — `_RESULTS_BINARY_EXTS={.gds,.def,.spef,.rtlil,.v,.guide}`, `_RESULTS_BINARY_NAMES={mem.json}` under `orfs_results/`, `.webp` under `orfs_reports/`; keeps `.sdc/.json/.rpt/.txt/.tcl/logs`. Matches A1+A16. | — |
| **§3A** all 14 bundles split | **Yes** | 13 `.sc_binaries.json` present; `sync_fifo` correctly untouched (source-only, no PnR payload) — `split_bundle_binaries.py:28-29`, verified on disk. | — |
| **§4.2** clone still has real readable designs | **Yes** | git-tracked `examples/` = **3.8 MB** (was ~75 MB); RTL/spec/manifest/trajectory/reports/logs all in git (e.g. `examples/traffic_light/workspace/synth_runs/synth_0001/inputs/traffic_light.v` readable). Heavy files gitignored: `examples/.gitignore:5-12` mirrors the split filter. | Plan claims ~2.3 MB; actual 3.8 MB because `orfs_logs/*.json` + `*.rpt` are intentionally kept (A1, for byte-identical PPA). "KB-scale" is loosely met (~270 KB/bundle); defensible, but the plan's size number is stale. |
| **§3B** TemplateSource engine (local/gcs) + index | **Yes** | `src/platform_engines/template_source.py:94-211` (`LocalTemplateSource`/`GcsTemplateSource`, one factory `:324-354`); index shape D4 built by `scripts/publish_templates.py:124-175`. | — |
| **§3B** publish without redeploy | **Yes** | `publish_templates.py:178-227` uploads archives then `index.json` LAST (atomic); backend flips to gcs via `TEMPLATES_BUCKET` env (`settings.py:198-201`). Ongoing publish = upload only. | One-time engine flip needs a revision (acknowledged in D2); ongoing publish needs none — criterion met. |
| **§4.3 / §3B** listing READ-ONLY | **Yes** | REST `list`/`get` only call `source.list()/get()` (`api.py:829-878`), no row writes; backend SA `objectViewer` only (`deploy/terraform/main.tf:114-118`), no write grant. Test `test_rest_list_ok_through_gcs_source`. | — |
| **§3C** hosted fork gate lifted + real materialization | **Yes** | gate raise deleted; `fork_from_template` parameterizes destination (`workspace_for` on cloud) + materialization (`source.materialize`) — `templates.py:452-492`; `TemplatesUnavailable` fully removed (0 refs repo-wide). | — |
| **§3C** hosted fork = real owner-scoped session + fresh chat (parity) | **Yes** | `tests/test_hosted_fork.py:178-222` (`test_hosted_fork_happy_path`): files materialized, `sessionId` cleared, `netlist_path` re-derived fork-local, provenance file+store, `count_threads==1`, owned by alice, invisible to bob, template store read-only. REST: `test_rest_hosted_fork_succeeds_and_chip_reads_from_store:613-639`. | — |
| **§3D** GCS-down → "unable to connect" | **Yes** | `GcsTemplateSource._load_index:186-202` last-good TTL then raises `TemplateStoreUnavailable`; REST → 503 "Template gallery is unreachable" (`api.py:838-839, 875-878`); `Launcher.tsx:391-419` renders `examples-unavailable` + Retry. Tests `test_rest_list_returns_503_when_store_unavailable`, `test_fresh_instance_with_dead_store_raises_not_empty`. | — |
| **§3D** not-fetched GDS → honest "re-run synthesis" | **Yes** | `api.py:2533-2569` layouts returns `{layouts, missing_binaries}`; `LayoutArtifact.tsx:65-77` "GDS not present … re-run synthesis, or fetch the example binaries". Test `frontend/test/layoutArtifact.missing.test.tsx`. | — |
| **§3D** existing sessions unaffected when store down | **Yes** | forked files live in the user's OWN workspace (provider), independent of the template store; only new browse/fork paths hit it. | — |
| **§4.1** self-host never needs cloud | **Yes** | `LocalTemplateSource` touches no cloud; `GcsObjectStore` google import lazy (`workspace_provider.py:190-195`); `template_source.py:40` imports only the class. `fetch_examples.py` is stdlib-only (`urllib`+`tarfile`). Local factory path never constructs Gcs. | — |
| **§4.4** honest state everywhere | **Yes** | never fake-empty (503 not empty 200); TTL is declared last-good/SWR (A14). | — |
| **§4.5** twelve-factor | **Yes** | templates leave the image (git-light); gallery+fork served from bucket/provider so any instance completes a fork (`workspace_for`+`sync` last). | — |
| **§4.6** manifest source of truth | **Yes** | `manifest.json` copied verbatim; `_clear_manifest_session_id:219-234` blanks only `sessionId`; reconcile re-seeds. | — |
| **§4.7** netlist_path rewrite | **Yes** | `_rewrite_run_meta_netlists:294-328` re-derives fork-local; A15 split-out-but-absent gate netlist → `None` not `inputs/` RTL (`_run_has_split_out_netlist:271-291`). Test `test_binary_less_fork_forces_netlist_none_not_inputs_rtl:230-246`. | — |
| **§4.7** manifest sessionId / provenance / copy2 / rollback | **Yes** | provenance file + durable store copy (`_write_provenance:331-346`, `set_source_template` both stores); `copytree_guarded` reused; `_rollback_fork:381-401` = `delete_workspace` (drops manifest) + `delete_session`; `CloudWorkspaceProvider.delete_workspace:729-751`. Tests `test_rollback_on_{materialize,sync}_failure`, `test_gcs_missing_binaries_fails_all_or_nothing`, `..._corrupt_binaries_fails_sha_verify`. | — |
| **§4.8** self-host vs hosted parity | **Yes** | same rewrites both engines; destination and materialization are independent axes; mixed-combo tests `test_cloud_workspace_local_source_degrades_and_syncs:366-384`, `test_local_workspace_gcs_source:387-402` (A6 ruling honored). | — |
| **§4.3 tenancy** cross-tenant + no user→official write | **Yes** | `create_session` atomic `insert_session` (`session_manager.py:154-170`, `metadata_store.py:290-302,702-716`) + `DuplicateSession`; A17 refork-after-delete purge + A18 concurrent race. Tests: `test_cross_tenant_fork_..._isolates_owner_and_workspace:485-522` (no leak, no clobber — asserts `alice_manifest_gen` unchanged), `test_concurrent_..._race_insert_arbitrates:525-564`, `test_tenancy_all_writes_under_fork_prefix_template_store_read_only:410-436`. | — |
| **§6** non-goals NOT built (no publish/moderation/public-write) | **Yes** | no user-publish path; `publish_templates.py` is an operator tool with its OWN creds (`:275-282`); backend SA has NO write (`main.tf:114-118`); `tier:"official"` (`publish_templates.py:171`) + `official/` prefix reserve room for `community/`. | Correctly deferred, room left. |
| **§5** regression tests present & proving | **Yes** | 114 targeted tests pass (`test_hosted_fork.py`, `test_template_source.py`, `test_split_bundle_binaries.py`, `test_fetch_examples.py`, `test_publish_templates.py`, `test_templates_fork.py`, `test_persistence.py`); old gate tests rewritten (A8); REST 503/500 mappings proven (`:642-663`). | — |
| Module docstring accuracy | **Partial** | `src/utils/templates.py:26-28` still states "Level 1 is self-host ONLY … fork HARD-GATES to non-cloud … The hosted gallery is a later wave. [A5]" — contradicts the shipped hosted fork. | **MINOR doc-honesty defect.** Update the docstring to describe the two-axis engine design. No functional impact. |

## Findings

1. **[MINOR — doc honesty]** `src/utils/templates.py:26-28` module docstring is stale:
   it declares the fork hard-gates to non-cloud and "the hosted gallery is a later
   wave," which directly contradicts the now-shipped hosted fork
   (`fork_from_template:452-492`). CLAUDE.md prizes honest state; fix the docstring.

2. **[OBSERVATION — not a gap]** The plan's "repo → ~2.3 MB" (D1) is stale: actual
   git-tracked `examples/` is ~3.8 MB because `orfs_logs/*.json` + `*.rpt` are
   deliberately kept (A1, for byte-identical self-host PPA/stage-status). This is a
   sound trade-off; only the plan's number is off. §5 "KB-scale" is loosely met.

3. **[OBSERVATION — correctly deferred]** Item 4 (live migration: terraform apply,
   real publish, live hosted-fork verify) is owner-run and NOT executed this wave —
   explicitly documented as needing prod creds. Honest deferral, per §8/§5.

All other requirements are met completely and with the right intent.

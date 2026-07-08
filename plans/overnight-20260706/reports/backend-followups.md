# Backend follow-ups (#3, #4, #5, #6)

Branch `claude/followups-batch-1`. One commit+push per item, explicit paths.
Source: `plans/followups-backlog.md`.

---

## #3 — VCD parse size guard
**Commit** `eba83ff` `fix(waveform): cap VCD parse size, honest too-large signal (#3)`

**Change** — `api.py` `_parse_vcd_file`: `stat` the file BEFORE `VCDVCD(path)`.
New module const `VCD_PARSE_CAP = 25_000_000` (25 MB). Over the cap → return a
structured too-large payload (`tooLarge: True`, `size`, `signals: []`,
`signalCount: 0`, plus the same null-valued shape keys as the success path so
the viewer can branch without KeyErrors) instead of parsing. Mirrors
`workspace_fs.read_smart_file`'s text cap (content-None + `tooLarge`). Success
path now also carries `tooLarge: False` + `size` for shape consistency.

**Test** `tests/test_vcd_size_guard.py`:
- `test_parse_vcd_over_cap_returns_too_large_signal` — monkeypatches the cap to
  100 bytes; asserts `tooLarge` + empty signals + real `size`.
- `test_parse_vcd_under_cap_parses` — a small VCD parses (`tooLarge False`,
  `clk` present); `importorskip("vcdvcd")`.

**Pre-fix proof** — with the fix stashed, both fail: over-cap KeyErrors /
returns a parse; under-cap KeyErrors on the missing `tooLarge` key.

---

## #4 — recursive `GET /waveforms`
**Commit** `e6392c7` `fix(waveform): list workspace VCDs recursively (#4)`

**Change** — `api.py` `list_waveform_files`: replaced the non-recursive
`os.listdir` with an `os.walk`, filtered to `.vcd`, returning **workspace-
relative POSIX paths** (so a nested dump stays fetchable via the sibling
`/waveform/{filename:path}` route). Prunes only `__pycache__`/`node_modules`/
dot-dirs — read-only, no row materialization.

**Deliberate deviation from the task hint:** the task suggested
`manifest_mod.iter_workspace_files` OR `os.walk`. `iter_workspace_files` is
WRONG here — its `_IGNORED_DIRS` prunes `sim_runs`/`synth_runs`
(`src/tools/manifest.py:36-39`), i.e. exactly the dirs whose VCDs #4 wants to
surface. Using it would leave the bug unfixed. So `os.walk` it is; the reason
is documented in the endpoint docstring.

**Test** `tests/test_waveforms_recursive.py`
`test_waveforms_lists_nested_vcd_recursively` — seeds `root.vcd` +
`sim_runs/sim_0001/dump.vcd`; asserts both listed.

**Pre-fix proof** — stashed: `assert 'sim_runs/sim_0001/dump.vcd' in ['root.vcd']`
fails (only the root VCD listed).

---

## #5 — validate model id at thread PATCH
**Commit** `5d81d12` `feat(chat): validate model id at thread PATCH against the catalogs (#5)`

**Change** — `api.py` `patch_thread`: new module frozenset `_KNOWN_MODEL_IDS` =
`model_catalog_entries()` ids ∪ `codex_catalog_entries()` ids ∪ `PRICING` keys.
On PATCH, `normalize_model_name(data.model)` first (aliases resolve to canonical
targets, all present in the set), then `422` if the normalized id is unknown.

**Why include `PRICING` keys, not just the two catalogs:** previous-generation
ids (`claude-sonnet-4-6`, `gpt-5.4`, …) are intentionally still selectable/
pinnable and priced. Validating against catalogs alone would 422 a legitimately
pinned id AND break the existing regression
`test_thread_routes_not_shadowed_by_greedy_session_patch` (it PATCHes
`claude-sonnet-4-6` and expects 200). `PRICING` is the honest "all ids we still
recognize" superset; only true typos/stale-unknowns fall outside it.

**Test** `tests/test_patch_model_validation.py`
`test_patch_thread_rejects_unknown_model_accepts_known_and_alias` — bogus id →
422; catalog id (`claude-opus-4-8`) → 200; alias (`gemini-3-flash-preview` →
`gemini-3.5-flash`) → 200 (alias normalization not broken).

**Pre-fix proof** — stashed: `assert 200 == 422` fails (bogus id accepted).
Post-fix, the existing shadowing regression still passes (PRICING covers
`claude-sonnet-4-6`).

---

## #6 — CLAUDE.md known-failure drift
**Commit** `66c31cd` `docs: record test_linter_tool_multifile + cocotb/sby in known env-gap failures (#6)`

**Change** — CLAUDE.md gate section: made `cocotb`/`sby` explicit as
`test_run_cocotb`/`test_run_sby` and added `test_linter_tool_multifile
[no iverilog/verilator]`.

### ⚠️ Honesty flag — the premise did NOT reproduce on THIS container
On the container I ran in, all three tests **PASS** (in isolation AND in the
full suite): iverilog/verilator/cocotb/sby binaries are present here. So they
are NOT env-gap failures on this machine — the "base endgame" container you
observed lacks those binaries; mine has them.

The doc addition is still defensible ONLY as an env-*dependent* catalog entry
("fails where the binary is missing", matching the existing "missing deps/
binaries" convention — note the pre-existing `cocotb`/`sby`/`xls` entries also
pass on my container). But the "~20 KNOWN env-gap failures **in this container**"
wording is inherently container-specific and already imperfect. Flagging so you
/ the owner can reconcile which base image the doc should describe.

---

## Final summary

| Item | Commit | Test |
|---|---|---|
| #3 VCD size cap | `eba83ff` | `tests/test_vcd_size_guard.py` (2) |
| #4 recursive /waveforms | `e6392c7` | `tests/test_waveforms_recursive.py` (1) |
| #5 PATCH model validation | `5d81d12` | `tests/test_patch_model_validation.py` (1) |
| #6 CLAUDE.md drift | `66c31cd` | docs-only |

All committed with explicit paths and pushed to
`origin/claude/followups-batch-1`. (`be28dff`, another agent's #1, landed
between #5 and #6 on the shared branch — expected.)

**Gate** — full backend suite:
`python -m pytest tests/ -q --ignore=tests/test_identity_migration.py
--ignore=tests/test_mcp.py --ignore=tests/test_mcp_remote_auth.py` →
**11 failed, 808 passed, 9 skipped**. All 11 are pre-existing env/Windows/dep
gaps unrelated to this work (congestion_summary ×2, lint_engines norm_file,
llm_factory, orfs_job_entrypoint, perf_read_no_sync, sby_engine,
workspace_incremental_sync ×2 [Windows symlink+CRLF], xls_engine ×2). **Zero
new failures** — none touch waveform / thread-PATCH / model-catalog code.
`test_run_cocotb`/`test_run_sby`/`test_linter_tool_multifile` all pass here (see
#6 flag). Fixtures restored via `git checkout -- tests/fixtures/
test_sby_output.txt` after the run.

**Fence respected** — touched only `api.py`, `CLAUDE.md`, `tests/**`, and this
report. `deploy/roll_cloudrun.py` + `frontend/**` in the shared working tree
belong to other agents; not staged or committed by me.

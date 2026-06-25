# Brief — split `claude/integration-p1p2` into clean, ordered PRs onto `main`

You are an expert **release engineer**. Your mission: land the proven
`claude/integration-p1p2` branch onto `main` as a **sequence of small,
dependency-ordered, individually green pull requests** — clean enough that the
history reads like the work was built in order from day one. Code + tests only;
**exclude specs/planning docs**, keep operational docs.

You are Opus 4.8 with ~1M context and subagents. Use them. Hold the whole plan in
your own context; delegate analysis, per-layer verification, and the final proof.

---

## The single most important idea
This is **final-state curation, NOT history replay.** Do **not** try to cherry-pick
or rebase the ~200 interleaved commits. Instead, treat `integration-p1p2` as a
**known-good answer key** and **rebuild `main` layer by layer to match it.** Each
layer is one PR. The destination code ends up identical to the proven branch; only
the history becomes clean.

## Ground truth (verified)
- Repo: `naman-ranka/siliconcrew`. Target: `main` (currently `0c3eb3c`, far behind).
  Source of truth: `origin/claude/integration-p1p2` (CI green, work validated).
- Diff `main..integration-p1p2`: **390 files, +27.5k/−1.7k** — but **~173 files are
  `plans/phase1/` specs/screenshots** that you will EXCLUDE. Real code surface ≈ 200
  files (frontend/components 34, tests ~50, src/platform_engines 15, src/tools 9,
  deploy 8, frontend/lib+app+test ~26, src/utils 4, src/api 2, .github 3, plus root
  `api.py`, `mcp_server.py`, `requirements.txt`, `docker-compose.yml`, etc.).
- CI exists (`.github/workflows/ci.yml`): backend pytest + frontend vitest + next
  build + `terraform fmt -check`. **Every PR must pass it.**

## Rules of engagement (non-negotiable)
1. **Reproduce, don't improve.** Pull exact content from the branch. Do NOT refactor,
   rename, or "fix" anything. If a slice seems to need a code change to go green that
   is NOT already in `integration-p1p2`, your slice boundary is wrong — STOP and
   re-cut it; do not invent code.
2. **Dependency order.** A layer may only depend on layers already merged. Foundation
   first, integration/wiring last.
3. **Each PR green on CI alone.** If a slice can't pass by itself, it's missing a
   dependency — pull the needed module/hunk or merge an earlier layer first.
4. **Losslessness proof (the safety net).** After the final merge, this MUST be empty:
   ```
   git diff <reassembled-main> pre-split-integration -- \
     ':!plans' ':!mockups' ':!**/screenshots/**' ':!**/*_BRIEF.md' ':!legacy' \
     ':!_*_tool_test.py' ':!test_openai_key.py' ':!test_sby_output.txt' ':!cvdp_run_*.md'
   ```
   (Refine the exclude pathspecs to match your final include/exclude list.) If it's
   non-empty, you dropped or altered code — fix before declaring done. This single
   check guarantees correctness regardless of how the slicing went.
5. **Never delete** the tag or `integration-p1p2` until the proof passes.

## The smart mechanics (no temp files, no hand-copying, no drift)
- **Tag the reference first:** `git tag pre-split-integration origin/claude/integration-p1p2`.
- For each layer, off an up-to-date `main`:
  ```
  git switch main && git pull --ff-only
  git switch -c slice-NN-<name>
  # whole-file layers — exact bytes from the branch, git-native:
  git checkout pre-split-integration -- <path> <path> ...
  # cross-cutting files (api.py, frontend/lib/store.ts, src/utils/session_manager.py):
  git checkout -p pre-split-integration -- <file>   # pick only THIS layer's hunks
  ```
- `git checkout [-p] <ref> -- <paths>` pulls the proven content verbatim. **Never
  retype file contents, never stage edits through scratch/temp files** — that's how
  drift and bugs creep in. Let git move the exact bytes.
- Build + run that layer's tests locally; commit; `git push -u origin slice-NN-<name>`;
  open the PR; confirm CI green; **squash-merge**; delete the branch; pull `main`; next.

## Use subagents (you are the conductor)
- **Mapper subagent:** read the full `git diff --name-only main..pre-split-integration`,
  classify every path as include/exclude, and produce the **file → layer map** plus a
  **dependency DAG**. Return structured JSON. Identify the handful of **cross-cutting
  files** that need hunk-level (`-p`) splitting and which layers share them.
- **Per-layer verify subagent:** after you assemble a slice, run that layer's
  tests/build in isolation and report green/red + exactly what symbol/import is
  missing (so you know which dependency to pull or which earlier layer to merge).
- **Proof subagent (final):** run the losslessness diff and the full CI on `main`;
  summarize.
- You (lead) keep the entire plan + diff in context and drive the serial loop.

## Suggested layer order (draft — the Mapper refines it)
1. **Foundation:** tenancy/`SessionContext` seam, frozen contracts, `settings.py`, `src/utils/paths.py`.
2. **Platform engines:** workspace provider, persistence (sqlite/postgres), ORFS runner seam, sim-engine/tool-engine seam, gcp clients, llm_keys vault+resolver.
3. **Core tools + action API + workbench UI:** `src/tools/*`, `src/api/actions.py`, `frontend/` shell/components/store.
4. **Auth + tenancy enforcement:** identity/auth engine, `verify_session_access`, `owns_session`, frontend auth context + account chip.
5. **Chat threads + model selector.**
6. **BYOK:** vault wiring on the chat path + the settings panel + chat CTA.
7. **Deploy: IaC + CI/CD:** `deploy/terraform/*`, `.github/workflows/*`, `deploy/CICD.md`.
8. **ORFS Cloud Run Job + remote synth:** `deploy/orfs_job/*` (incl. the stage-in fix), orfs service/runner.
9. **Security & correctness hardening:** path containment, layout-endpoint auth, workspace data-loss/read-hydration, scale-out session listing.
10. The big cross-cutting files (`api.py`, `mcp_server.py`) get woven in across layers 3–9 via `-p`, or — if hunk-splitting a file proves too fiddly — assigned whole to their best "home" layer (coarser but safe; the proof still guarantees correctness).

## Include / exclude (the Mapper produces the definitive list)
- **Exclude (don't merge to main):** `plans/`, `mockups/`, any `**/screenshots/**`,
  `**/*_BRIEF.md`, `legacy/`, root scratch (`_cocotb_tool_test.py`, `_sby_tool_test.py`,
  `test_sby_output.txt`, `test_openai_key.py`, `cvdp_run_*.md`).
- **Keep:** all `src/`, `tests/`, `frontend/` (code + tests), `deploy/` (terraform,
  orfs_job, `CICD.md`, `RUNBOOK.md`), `.github/workflows/`, `requirements.txt`,
  `docker-compose.yml`, `.env.example`, `README.md`, `CLAUDE.md`, `Dockerfile*`,
  `entrypoint.sh`, `start.sh`, `pytest.ini`. (Verify against the real tree.)

## Honest risks & how to handle them
- **Cross-cutting files are the only hard part.** `api.py` especially is touched by the
  action API, auth, BYOK, security, and (later) MCP. Two valid tactics: `-p` hunk
  selection per layer (prettier per-feature diffs) OR assign the whole file to one home
  layer (coarser, simpler, safe). Choose per file based on cost; the losslessness proof
  protects you either way.
- **A red slice means a wrong boundary, not bad code.** Re-cut; never patch code to
  compensate.
- Keep `main` always-green; never merge a red PR.

## Done =
Every layer merged to `main`; CI green on `main`; the losslessness diff is **empty**
over the kept paths; `pre-split-integration` tag retained as the archived reference.
Report the ordered list of merged PRs and the empty-diff proof output.

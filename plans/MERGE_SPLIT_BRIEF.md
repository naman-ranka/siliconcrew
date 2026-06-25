# Brief — rebuild `main` cleanly from `claude/integration-p1p2` (staging branch; owner merges)

You are an expert **release engineer**. Your mission: take the proven
`claude/integration-p1p2` branch and reproduce it onto a **staging branch that is a
copy of `main`**, as a **clean, ordered sequence of commits** — one per architectural
layer — so the history reads like the work was built in order from day one. Code +
tests only; **exclude specs/planning docs**, keep operational docs.

**You do NOT touch `main`, and you do NOT open pull requests.** When you are done,
the owner reviews the staging branch and performs the single final merge to `main`
themselves. Your deliverable is a verified, clean-history staging branch plus the
proof that its code equals the proven branch.

You are Opus 4.8 with ~1M context and subagents. Use them. Hold the whole plan in
your own context; delegate analysis, per-layer verification, and the final proof.

---

## The single most important idea
This is **final-state curation, NOT history replay.** Do **not** cherry-pick or
rebase the ~200 interleaved commits. Treat `integration-p1p2` as a **known-good
answer key** and **rebuild a clean copy of `main` layer by layer to match it.** Each
layer becomes **one clean commit** on the staging branch. The destination code ends
up identical to the proven branch; only the history becomes clean.

## Ground truth (verified)
- Repo: `naman-ranka/siliconcrew`. Base: `main` (currently `0c3eb3c`, far behind).
  Source of truth: `origin/claude/integration-p1p2` (CI green, work validated).
- Diff `main..integration-p1p2`: **390 files, +27.5k/−1.7k** — but **~173 files are
  `plans/phase1/` specs/screenshots** that you will EXCLUDE. Real code surface ≈ 200
  files (frontend/components 34, tests ~50, src/platform_engines 15, src/tools 9,
  deploy 8, frontend/lib+app+test ~26, src/utils 4, src/api 2, .github 3, plus root
  `api.py`, `mcp_server.py`, `requirements.txt`, `docker-compose.yml`, etc.).
- CI exists (`.github/workflows/ci.yml`): backend pytest + frontend vitest + next
  build + `terraform fmt -check`. The binding CI run happens when the owner merges
  the staging branch to `main`; you make it pass by verifying each layer locally.

## Rules of engagement (non-negotiable)
1. **Reproduce, don't improve.** Pull exact content from the branch. Do NOT refactor,
   rename, or "fix" anything. If a layer seems to need a code change to go green that
   is NOT already in `integration-p1p2`, your layer boundary is wrong — STOP and
   re-cut it; do not invent code.
2. **Dependency order.** A layer may only depend on layers already committed before
   it. Foundation first, integration/wiring last.
3. **Each layer commit must build + pass its tests on its own** (verified locally by a
   subagent at that commit). A red layer means a wrong boundary — re-cut; never patch
   code to compensate.
4. **Losslessness proof (the safety net).** At HEAD of the staging branch, this MUST
   be empty:
   ```
   git diff release/clean-main pre-split-integration -- \
     ':!plans' ':!mockups' ':!**/screenshots/**' ':!**/*_BRIEF.md' ':!legacy' \
     ':!_*_tool_test.py' ':!test_openai_key.py' ':!test_sby_output.txt' ':!cvdp_run_*.md'
   ```
   (Refine the exclude pathspecs to match your final include/exclude list.) If it's
   non-empty, you dropped or altered code — fix before declaring done. This single
   check guarantees the staging branch's code equals the proven branch.
5. **Never touch `main`, never open PRs, never delete** the tag or `integration-p1p2`.
   The owner does the final merge.

## Commit message rules (important)
- Clean, conventional commits — imperative mood, one logical layer per commit, a
  short title + a body explaining what the layer contains and why. This history is
  the product; make it read well.
- **Do NOT append any `Co-Authored-By: Claude …` or `Claude-Session: …` trailers, and
  do not mention Claude/AI in commit messages.** Keep authorship clean.

## The smart mechanics (no temp files, no hand-copying, no drift)
- **Tag the reference and create the staging branch:**
  ```
  git fetch origin
  git tag pre-split-integration origin/claude/integration-p1p2
  git switch -c release/clean-main origin/main
  ```
- For each layer, in order, build it directly on `release/clean-main`:
  ```
  # whole-file layers — exact bytes from the branch, git-native:
  git checkout pre-split-integration -- <path> <path> ...
  # cross-cutting files (api.py, frontend/lib/store.ts, src/utils/session_manager.py):
  git checkout -p pre-split-integration -- <file>   # pick only THIS layer's hunks
  # verify (subagent runs that layer's tests/build), then:
  git add -A && git commit   # clean message, NO Claude trailers
  ```
- `git checkout [-p] <ref> -- <paths>` pulls proven content verbatim. **Never retype
  file contents and never stage edits through scratch/temp files** — that's how drift
  and bugs creep in. Let git move the exact bytes.
- No per-layer pushes-as-PRs. When all layers are committed and the proof passes,
  push the branch once: `git push -u origin release/clean-main`. Then STOP.

## Use subagents (you are the conductor)
- **Mapper subagent:** read the full `git diff --name-only main..pre-split-integration`,
  classify every path include/exclude, and produce the **file → layer map** + a
  **dependency DAG**. Return structured JSON. Identify the cross-cutting files that
  need hunk-level (`-p`) splitting and which layers share them.
- **Per-layer verify subagent:** after you assemble a layer commit, run that layer's
  tests/build in isolation and report green/red + exactly which import/symbol is
  missing (so you know which dependency to pull or which earlier layer to extend).
- **Proof subagent (final):** run the losslessness diff and the full test suite at
  staging HEAD; summarize.
- You (lead) keep the entire plan + diff in context and drive the serial loop.

## Suggested layer order (draft — the Mapper refines it)
1. **Foundation:** tenancy/`SessionContext` seam, frozen contracts, `settings.py`, `src/utils/paths.py`.
2. **Platform engines:** workspace provider, persistence (sqlite/postgres), ORFS runner seam, sim/tool-engine seam, gcp clients, llm_keys vault+resolver.
3. **Core tools + action API + workbench UI:** `src/tools/*`, `src/api/actions.py`, `frontend/` shell/components/store.
4. **Auth + tenancy enforcement:** identity/auth engine, `verify_session_access`, `owns_session`, frontend auth context + account chip.
5. **Chat threads + model selector.**
6. **BYOK:** vault wiring on the chat path + settings panel + chat CTA.
7. **Deploy: IaC + CI/CD:** `deploy/terraform/*`, `.github/workflows/*`, `deploy/CICD.md`.
8. **ORFS Cloud Run Job + remote synth:** `deploy/orfs_job/*` (incl. stage-in fix), orfs service/runner.
9. **Security & correctness hardening:** path containment, layout-endpoint auth, workspace data-loss/read-hydration, scale-out session listing.
- Big cross-cutting files (`api.py`, `mcp_server.py`) get woven across layers 3–9 via
  `-p`, or — if hunk-splitting a file proves too fiddly — assigned whole to their best
  "home" layer (coarser but safe; the proof still guarantees correctness).

## Include / exclude (the Mapper produces the definitive list)
- **Exclude (do NOT bring over):** `plans/`, `mockups/`, any `**/screenshots/**`,
  `**/*_BRIEF.md`, `legacy/`, root scratch (`_cocotb_tool_test.py`, `_sby_tool_test.py`,
  `test_sby_output.txt`, `test_openai_key.py`, `cvdp_run_*.md`).
- **Keep:** all `src/`, `tests/`, `frontend/` (code + tests), `deploy/` (terraform,
  orfs_job, `CICD.md`, `RUNBOOK.md`), `.github/workflows/`, `requirements.txt`,
  `docker-compose.yml`, `.env.example`, `README.md`, `CLAUDE.md`, `Dockerfile*`,
  `entrypoint.sh`, `start.sh`, `pytest.ini`. (Verify against the real tree.)

## Honest risks & how to handle them
- **Cross-cutting files are the only hard part.** `api.py` especially is touched by the
  action API, auth, BYOK, security, and (later) MCP. Two valid tactics: `-p` hunk
  selection per layer (prettier per-feature commits) OR assign the whole file to one
  home layer (coarser, simpler, safe). Choose per file; the losslessness proof
  protects you either way.
- **A red layer means a wrong boundary, not bad code.** Re-cut; never patch code.

## Done =
`release/clean-main` contains the full set of clean, ordered layer commits (no Claude
trailers); the full test suite passes at its HEAD; the losslessness diff over the kept
paths is **empty**; the branch is pushed; `pre-split-integration` tag retained.
**Report:** the ordered list of layer commits (hash + title) and the empty-diff proof
output. Then STOP — the owner reviews the branch and merges it to `main`.

## Running this to completion with `/goal` (optional but recommended)
This task pairs well with Claude Code's `/goal` (it keeps working across turns until a
condition holds) **because it can't hurt `main`** — all work is on the throwaway
`release/clean-main`. Set the completion condition to the Option-A end state, e.g.:

```
/goal release/clean-main contains all layers as clean ordered commits with no Claude
trailers, the full test suite passes at its HEAD, and `git diff release/clean-main
pre-split-integration` over the kept paths is empty — without ever modifying main or
opening any PR
```

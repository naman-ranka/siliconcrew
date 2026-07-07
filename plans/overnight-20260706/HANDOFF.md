# HANDOFF — overnight showcase run (Fable 5 → Fable 5)

Session 1 ended mid-flight; this is the single "start here" for the continuation.
Read `MISSION.md` (mission), `FINDINGS.md` (live ledger F1–F18 + deploys + D1–D3),
and `reports/*.md` (per-topic detail). Branch: `claude/overnight-showcase`.

## State at handoff (accurate as of HEAD 441342b)

**Deployed & live-confirmed:**
- backend **rev 00059** = F1 tenancy fix (list/delete owner-scope + pre-dispatch gate). Live-confirmed (list=own-only).
- backend **rev 00060** = + F9 `LEC_CHECK=0` (hosted-gated). Confirmed: fresh run's `config.mk` carries the line → GDS dependable by construction.
- frontend still **rev 00049** (landing NOT deployed yet — deliberate, see below).

**Committed, NOT yet deployed (batch into the final backend roll):**
- F2 (codex latency: read-only tools skip GCS sync) `f095fcb` — audited, policy-guard test, gates green.
- F16/F17 (Wave 11 review fixes: sanitizer redaction + patch_session provenance) `8e90f1b`.

**Landing page:** code-complete + verified honest (store-driven gallery, no fabricated cards, gates green, e2e preserved, both themes, correct posture). Deploy HELD until the gallery had real content.

**Showcase bundles (`examples/`):** `sync_fifo` (sim-only, real fail→fix→pass trajectory) + `seq_detector_0011` (**real GDS**, flagship, landed at HEAD 441342b). `impl-templates` may still be adding more (lfsr8 / counter / traffic_light) — check `reports/bundles-authored.md`.

**Wave 11 templates/forks:** done, adversarially reviewed SAFE, review fixes applied.
**Tenancy sweep:** CLEAN (F1 was the only hole). **Skills:** gcp_logs + ui_navigation authored+verified (in gitignored `.agents/` — see D1).

## Immediate next actions (the endgame)

1. Check in-flight agents' outputs: `reports/bundles-authored.md` (more bundles?) and `reports/gds-verify.md` (final hosted GDS verdict — it was confirming on rev 00060 via UI).
2. When bundle authoring + gds-verify are done: run the FULL gate suite on final HEAD — backend `python -m pytest tests/ -q --ignore=…` vs the 9-known baseline (ZERO new); frontend `npx tsc --noEmit` · `npx vitest run` (1 known pre-existing failure `chat.threads.store.test.ts`) · `npx next build` · Playwright. Re-verify every `examples/*` bundle is clean (no `C:\Users` host-path leak — F16).
3. DEPLOY from the reviewed tip (Wave 11 is reviewed now, so no more minimal-overlay needed): backend HEAD (F1+F9+F2+Wave11+F16/17) AND frontend HEAD (landing + gallery), together. Use the deploy skill; roll via a backend-only + frontend script (see `deploy/roll_cloudrun.py` and the F1/F9 roll pattern in this session's scratchpad). Time it when NO MCP-driven agent is mid-run (every backend deploy breaks the claude.ai MCP connector until manual reconnect — F15).
4. Live-verify (Playwright, test acct rockstarme.the5@gmail.com / claude@test): landing renders + GitHub/Issues links; gallery lists the REAL bundles (incl. the GDS one); fork behaves honestly per mode (hosted = self-host-only per A5/D3); GDS still works; `list_sessions` still owner-scoped.
5. Write `MORNING_REPORT.md`.

## Deferred / owner-only
- Python analysis wave (low priority, not started). Agent-panel (Gemini) exploration (browser was busy). Codex F3/F4 latency follow-ups + the F2 live [CODEX-TIMING] before/after (needs the MCP connector reconnected).
- **Owner decisions D1 (.agents gitignored — commit skills?), D2 (flagship bundle path — partly resolved by the local GDS bundle), D3 (hosted fork = self-host-only).**
- **Owner-only:** reconnect the claude.ai "Silicon crew" MCP connector (stale since a deploy, F15).

## Deploy facts
gcp-key.json at repo root (project siliconcrew, us-central1). Skill: `.agents/skills/gcp_deployment/SKILL.md`. Live backend base for minimal overlays was `ccdb6e0`; full-HEAD deploy is now fine since everything is reviewed. Log-fetch skill: `.agents/skills/gcp_logs/fetch_logs.py`.

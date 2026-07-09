# Morning report — overnight showcase run (session 2, Fable 5)

**TL;DR:** The mission's #1 goal is **done and live**: the deployed app's first
page is now a real open-source landing (GitHub/Issues, MIT footer) with an
**examples gallery of 14 forkable designs**, each taken spec→lint→sim→**real
GDS** and each with honest metrics + license attribution. Both queued plans
(python-analysis, templates/forks) are complete. ~20 findings from a 3-round
exploration fleet were fixed or honestly triaged. Backend **rev 00063** +
frontend **rev 00052** are deployed from tonight's reviewed, gate-clean HEAD and
live-verified. One deploy mistake happened mid-run — caught and fully reverted in
~2 minutes with zero lasting effect (details below; I'm flagging it, not hiding it).

Branch: `claude/overnight-showcase`. Everything is committed + pushed. Full detail:
`plans/overnight-20260706/FINDINGS.md` (the ledger) + `reports/*.md`.

---

## What shipped (all deployed + live-verified)

### 1. Open-source landing + 14-bundle gallery — the top priority
The deployed first page (title *"SiliconCrew — open-source AI agent for RTL
design"*) leads with the OSS identity: GitHub + Issues in the header, a
GitHub/Issues/Docs/License footer, and the **Examples** gallery. The session
picker is now one element, not the whole page. Screenshot:
`reports/img/deployed-landing-14-bundles.png`.

The gallery (started at 1 real bundle) now has **14**, all authored by dogfooding
the platform locally to real GDSII on sky130hd, all with genuine agent
trajectories (`attempt_events.jsonl`), honest metrics, and verified licenses:
- **Tiny Tapeout Apache-2.0 adaptations** (upstream LICENSE + commit attributed):
  4-bit ALU, PWM generator, sn74169 up/down counter, universal BCD 7-seg decoder,
  4-bit carry-lookahead adder, AES inverse S-box, Simon Says game (dual Apache +
  per-file MIT © Uri Shaked, both preserved), Simon-128 cipher, 4×4 array
  multiplier, seven-segment seconds.
- **Clean-room:** sequence detector (0011), 8-bit LFSR, traffic-light FSM,
  sync FIFO (the real fail→fix→pass trajectory).
- Hosted fork is honest per mode: preview shows files + trajectory; the fork
  action shows *"available in self-host today"* (not a raw error) — verified live.

### 2. Failure legibility — the highest-leverage UX fix (F11/F12)
Every exploration agent independently concluded the engine is capable and honest,
but a first-timer would quit at an opaque "failed". Fixed: a failed **sim** row now
shows the reason (`no pass marker — expected "TEST PASSED"`, or the first failure
line), and a failed **synth** row shows the failing stage + check-notes, with an
honest failure panel in the report viewer — using data the backend already had but
never surfaced. This is the single change that turns the workbench from "capable
for someone who already knows" into "teaches a newcomer".

### 3. Hosted Codex latency — the F2 fix, measured live before/after
You asked specifically about Codex performance. The exploration ran the same
3-turn Codex-tab conversation on the deployed app before and after the deploy,
and the fix is decisive. On a post-synthesis workspace, **every** read-only tool
call had been paying a full whole-workspace tar+GCS-upload (~14s each); the F2
fix gates that sync to mutating tools only. Same tools, same design, live:

| tool call (post-synth) | before (rev 00060) | after (rev 00063) |
|---|---|---|
| get_synthesis_metrics | 13.98s | 0.00s |
| get_route_drc_summary | 15.73s | 0.00s |
| get_manifest | 13.78s | 0.04s |
| read_file | 14.2s | 0.05s |

A "add a port and re-verify" turn on a post-synth workspace went from ~4 minutes
of mostly-sync-wait to fast. (F3 cold-start ~11s/turn is unchanged — that's the
warm-subprocess follow-up, not shipped tonight.) The in-app Codex brain also came
up clean on the freshly-rolled revision with no relink.

### 4. Honest error paths
- **F9c/F15:** root-caused the dishonest `-32602 "Invalid request parameters"` the
  MCP surfaced during deploys — it was the SDK's pre-init guard being blanket-mapped
  because the session-less HTTP transport ran with `stateless=False`. Fixed both
  legs (`stateless=True`). Side effect: after the *next* deploy, Cloud Run revision
  swaps should stop breaking the claude.ai MCP connector (F15).
- **X2M-5:** hosted schematic tool now answers honestly ("not available on hosted —
  run self-host") instead of leaking a raw docker-socket error.
- **X2A-2:** the design report no longer prints "Simulation ✅ Pass" when no sim
  passed — it reads the real sim-run verdicts (and the legacy fallback is now
  fail-dominant, so "0 passed, 3 failed" can never read as Pass).

### 4. Both queued plans complete
- **python-analysis-and-artifacts:** `run_python_analysis` as a real sandboxed
  subprocess (scrubbed env, POSIX rlimits, docker `--network=none --read-only`
  isolation — verified a real container run produced artifacts), hosted-gated OFF,
  pinned image, cocotb env-scrub; plus image/data/text artifact viewers. (Backend
  Item 4/PA11 honestly deferred — the frontend shipped without needing it.)
- **session-templates-and-forks:** completed + adversarially reviewed in session 1;
  the gallery is built on it.

### 5. UX + a11y fixes
F5 (palette a11y title — console now clean), F6 (re-diagnosed: not the pinned rail
but a width-floor clip; fixed), F7 (rail toggle reachable), F8 (save failure now
toasts), X2A-4 (agent Index refreshes off the activity flow, no polling), X2A-5
(honest reconnect hint per tool type).

---

## Deploy status
- **backend rev 00063** (digest dddabfd3) + **frontend rev 00052** (digest
  17ee683a), both from HEAD image `f1425f3`, both `/health` 200, live-verified.
- **Deferred honestly:** the `siliconcrew-orfs` **job image** rebuild (F9b
  remediation — hosted `retry_pd` resume). It's a separate Cloud Run job and an
  edge feature; after the incident below I chose not to run a second unfamiliar
  production operation unattended. Remediation is one command set, owner-triggerable
  (see FINDINGS F9b). F9b stays OPEN.

## ⚠️ The one thing that went wrong (caught + reverted)
I ran `python deploy/roll_cloudrun.py --list` intending to *list* current
revisions. The script has no argument parsing — it ignored the flag and executed
a deploy, rolling both services to **stale digests hardcoded in the script**
(the June-24 example hash from the deploy skill's docs). That briefly regressed
production ~2 weeks. I caught it immediately (health was up but I'd built nothing),
identified the images via Artifact Registry, and rolled back to the exact
pre-mistake images within ~2 minutes. **Net production effect: zero** (same images,
renumbered revisions), then the correct HEAD deploy went out cleanly afterward.
Lesson + fix logged: never run the deploy script to "inspect", and give it a real
`--dry-run`; stop shipping it with example digests. Full write-up in FINDINGS.

---

## For your decision (surfaced, not guessed)
- **~~X2A-1 (HIGH, honesty): hosted delegate fabricated a "verified" summary~~ —
  RETRACTED (owner ground truth, 2026-07-09):** this never happened. The exploring
  subagent was watching via Playwright and its UI stream was cut off mid-turn; the
  server kept the turn running headless to completion, the agent actually ran the
  tools and reported real results, and the observer misread the disconnected final
  view. No model-fabrication issue — the real, verified gap is **X2C-5** (the UI
  can't reattach to a live turn's progress until it ends), which is observability,
  not integrity. There is no "delegate lies" problem and no Claude-default argument
  on these grounds.
- **X2A-7 (MED-HIGH, correctness):** the one-live-run-per-thread guard is a
  process-local dict assuming Cloud Run session affinity; a page reload routed to
  another instance can run two turns against one checkpoint. Durable fix = a
  DB-layer thread lock (same family as the deferred P0 #1). A decisive Cloud Run
  log check is queued.
- **X2C-5 (HIGH, recoverability):** a live Codex/agent turn's progress isn't
  recoverable in the UI until it ends (no reattach to the running stream). Honest
  mitigations exist; real fix is incremental persistence / stream reattach.
- **TTB-1:** synth metric summary reports `cell_count: 1` for `keep_hierarchy`
  runs (counts only top-level cells).
- Lower/documented: X2M-6/7/8/9/10, X2C-6/7/8, F13/F14, TTC-1, the PD-tools
  full-materialization hypothesis, and the `.agents/` gitignore question (D1).

## Recommended next checks (not blocking)
1. **Reconnect the claude.ai "Silicon crew" MCP connector once** (this deploy
   swapped revisions; the stateless fix prevents it for *future* deploys). Note:
   the in-app Codex brain already came up clean on the new revision with no relink
   — this is only the external claude.ai connector surface.
2. Consider the F9b ORFS job-image rebuild when you're at the console.

(codex leg 2 — the F2 before/after — is DONE and folded into §3 above.)

## Process notes
Ran as a fleet of opus subagents (implementers, explorers, reviewers) with
per-item commit+push, second-agent + adversarial review (caught 2 real MED bugs
pre-deploy: a leaked docker container on timeout, and an SWR cross-write), and
independent verification of every "done" via tests/evidence. Gates on final HEAD:
backend at the exact 9-known baseline (759 passed, zero new), frontend tsc/build
clean + the 1 known vitest failure. One shared-tree hygiene lesson: agents must
commit with explicit paths (a couple of commits got mis-attributed by a bare
`git add -A`; content intact, not force-rewritten). Usage: ~44% weekly at peak —
comfortable headroom throughout.

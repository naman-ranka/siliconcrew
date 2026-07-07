# Overnight showcase run — 2026-07-06

Owner brief (verbatim in spirit): make SiliconCrew's first page a real
open-source landing (GitHub, issues, examples) — the session picker is one
element, not the whole page. Templates users can fork to see the files, the
agent trajectory, the transcripts. Along the way: run exploration agents
through every product surface, find and fix real issues, and leave behind a
mature agent infrastructure (skills, delegable contracts) for future runs.

Branch: `claude/overnight-showcase` (off `endgame`). Per-item commit+push.
CLAUDE.md governs process; plan Amendments are authoritative over plan bodies.

## Priorities (owner-ordered)

1. **Open-source landing page** (top end-state; gets main-loop attention).
2. **Session templates & forks** (`plans/session-templates-and-forks-wave.md`)
   — the showcase mechanism. Curate real templates: ASU problems, CVDP,
   Tiny Tapeout candidates.
3. **Exploration fleet** → findings → **fixes** (continuous).
4. Agent infra: skills for UI navigation, GCP logs, deploys.
5. Python analysis wave (`plans/python-analysis-and-artifacts.md`) — low
   priority, one-shot delegation; defer honestly if it doesn't land.

## Resources

- Hosted frontend: https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app/
  (test user rockstarme.the5@gmail.com / claude@test — AuthKit password page)
- Hosted MCP: connected as the same test user (claude.ai Silicon_crew server).
- GCP: `gcp-key.json` (repo root), project `siliconcrew`, us-central1;
  services `siliconcrew-backend`, `siliconcrew-frontend`. Deploy skill:
  `.agents/skills/gcp_deployment/SKILL.md` + `deploy/roll_cloudrun.py`.
- ASU problems: `ASU-Spec2Tapeout-ICLAD25-Hackathon/problems/visible/`
  (p1, p5, p7, p8, p9 yaml) + `example_problem/` + `solutions/`.
- Latest CVDP worktree: `C:\Users\naman\Desktop\Projects\RTL_AGENT_worktree_claude`
  (branch feature/cvdp-automate-refactor).
- Usage pacing: `agy --conversation 0b444de8-d6a2-46ff-afb4-dd25e677ff30 -p
  "get the latest claude usage"` — throttle when weekly limits get tight.

## Fleet rules

- Opus subagents by default; precise written contracts; file-disjoint — never
  two agents in the same files; commit WIP before delegating.
- Findings go to `FINDINGS.md` (ledger) + `reports/<name>.md` (detail);
  subagents return short summaries, files carry the bulk.
- Only ONE agent drives the Playwright browser at a time (single instance).
- Verify subagent "done" via tests/evidence, never their word.
- Live-site checks against the deployed app; deploys only from gate-clean
  pushed commits.

## Findings ledger

See `FINDINGS.md`. Classification: fix-now (invariant/correctness, with
regression test), defer (documented), or design-question (for the owner).

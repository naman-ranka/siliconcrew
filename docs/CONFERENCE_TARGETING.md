# SiliconCrew — Publication Venue Analysis

*Prepared 2026-07-10. All deadlines verified against public CFPs as of this date; re-confirm on the official sites before submitting.*

This document analyzes where SiliconCrew's research fits in the conference landscape, starting
with ICLAD/LAD (the venue purpose-built for this work), then mapping every other realistic venue
with an open or upcoming deadline, and ending with a concrete submission strategy.

---

## 1. What SiliconCrew has to publish

Before matching venues, it helps to be precise about what the publishable contributions actually
are. There are three distinct papers hiding in this repository, and they fit different venues
differently:

### Paper A — The analysis paper (strongest)
**"The self-verification gap: why agent-authored oracles fail on under-specified hardware specs."**
From `cvdp-pipeline/research/CVDP_FINAL_RESULTS.md`:

- 60/92 (65%) on NVIDIA's CVDP `no_commercial` agentic split, pass@1, single-shot, every verdict
  graded in the pinned reference container — with a **leak detector** that invalidated contaminated
  runs and forced sealed re-runs (the score was *deliberately lowered* from 63 to 60 for integrity).
- The central empirical finding: **76% of failures are one mechanism** — the agent encodes the same
  spec misreading into both the RTL and its self-authored golden model/cocotb/formal, so it
  self-verifies green but is wrong ("shared blind spot").
- Self-verification precision is only ~66–70%, degrading to a 58% false-positive rate on hard
  problems — a structural argument that self-derived oracles cannot catch comprehension errors.
- A clean difficulty gradient (88% easy / 65% medium / 45% hard) and a task-shape effect
  (modification 73% vs. integration 58% at medium tier).

This is the most defensible and novel contribution: it is a *measured, mechanistic* result about
agent self-verification, plus a benchmarking-integrity methodology (leak gating) that the
LLM-for-EDA community currently lacks and demonstrably needs.

### Paper B — The system paper
**"SiliconCrew: an autonomous agent from natural-language spec to GDSII."**
Spec-first workflow, self-checking testbench generation, waveform-based debugging (VCD inspection
at the failure point instead of guess-and-fix), SymbiYosys formal integration, OpenROAD flow to
SkyWater 130nm with PPA extraction, XLS/DSLX HLS frontend, and a dual-interface architecture
(Next.js streaming UI + MCP server sharing one tool backend with auto-discovery).

Crowded space in 2026 (many spec→RTL agents exist), but the differentiators are real: closed-loop
*waveform-grounded* debugging, the full spec→GDSII scope (most agents stop at simulation), and the
MCP tool-interface design study (`docs/TOOL_DESIGN_DECISIONS.md` is effectively a paper section on
"what tool interfaces enable effective LLM-driven EDA automation").

### Paper C — The methodology/short paper
**"Leak-gated benchmarking of agentic EDA systems"** (from `AUDIT_XLS_TOOLING_LEAK.md` +
`leak_detector.py`) — a short/WIP-length contribution on contamination in agentic benchmarks,
where the agent can read grader files from inside its workspace. Timely, small, and honest;
ideal for an invited/short/WIP track or an ML-workshop submission.

---

## 2. ICLAD / LAD — the primary venue

### What it is
The **IEEE International Conference on LLM-Aided Design** — launched as **ICLAD 2025** (Stanford,
first edition), running in 2026 as **LAD 2026** (2nd IEEE International Conference on LLM-Aided
Design), sponsored by IEEE CEDA, proceedings submitted to IEEE Xplore. It grew out of the
LLM-Aided Design workshop community and is the *only* conference whose entire scope is this
repository's topic.

- **LAD 2026**: July 30–31, 2026, Stanford, CA.
- **LAD 2026 deadlines**: abstract March 2, 2026; paper March 9, 2026 (OpenReview) — **passed**.
- Regular papers: 6 pages, IEEE conference format.
- **2026 stated theme**: *"agentic optimization and scaling inference-time methods"* — i.e.,
  exactly the SiliconCrew problem statement.

### Topic-by-topic fit

| LAD topic area | SiliconCrew coverage |
|---|---|
| Agentic workflows for design automation & optimization | Core of the system: LangGraph agent, spec→RTL→verify→fix→GDSII loop |
| LLMs for EDA: RTL, HLS, physical design, EDA scripting | RTL generation, XLS/DSLX HLS frontend, OpenROAD physical design, PPA knob exploration |
| New methodologies, tools, datasets, benchmarks | CVDP pipeline, leak detector, failure taxonomy, self-verification-gap metric |
| LLMs for reasoning/logic in the design process | Waveform-grounded debugging; golden-model-first verification discipline |
| Computational efficiency of LLM-aided design tools | Cost accounting in the results ($7.31/problem, $11.21/pass, turn counts) |

Direct peer papers at ICLAD 2025 confirm the fit: *OpenROAD Agent* (self-correcting script
generation — SiliconCrew drives OpenROAD as one tool among many), *An Agentic HLS Perspective*,
*Spec2RTL-Agent*, *AssertionForge*, *HiVeGen*, *TPU-Gen*, *DeepCircuitX* (dataset/PPA). SiliconCrew
would have been at home in that program; the self-verification-gap analysis would arguably have
been one of the more novel results there, since most accepted work reports capability, not
verified failure mechanisms.

### Verdict
**Best-fit venue in existence, but the 2026 edition is closed** (deadline passed March 2; the
conference itself runs in three weeks). The realistic play:

1. **Attend LAD 2026 (July 30–31, Stanford)** if feasible — it is the community that will review
   every future submission of this work, and CVDP/agentic-benchmark integrity will certainly be a
   hallway topic.
2. **Target LAD 2027 as the flagship submission** — expect the CFP around Dec 2026–Jan 2027 with a
   deadline near early March 2027, mirroring 2026. Paper A (self-verification gap) as a regular
   6-page paper, with Paper B as a second submission or demo.
3. Post an **arXiv preprint now** to timestamp the leak-gating methodology and the 65% result
   before the field moves.

---

## 3. Other venues, in deadline order (from 2026-07-10)

### 🔴 ASP-DAC 2027 — abstract due **TOMORROW** (July 11, 2026, 5 PM AoE)
- 32nd Asia and South Pacific Design Automation Conference, **Tokyo (Hitotsubashi Hall), Jan 25–28, 2027**.
- **Abstract registration: July 11, 2026 · full PDF: July 18, 2026 · notification: Sept 4, 2026.**
- ACM/IEEE-sponsored, established venue with active LLM-for-EDA / AI-for-CAD sessions.
- Fit: strong for either Paper A or B. The abstract deadline is title + abstract + authors only;
  the paper PDF has a further week. Registering an abstract costs nothing and preserves the
  option; the real question is whether a submission-quality paper can be produced by July 18.
  The CVDP results document is already ~80% of a results section, so Paper A in a week is
  aggressive but not absurd.

### 🟠 ICCAD 2026 Student Research Competition — abstract due **July 31, 2026**
- ICCAD 2026: **San Jose, Nov 8–12, 2026**. Main paper deadline (April 14) has passed, but the
  **SRC abstract deadline is July 31, 2026**, poster session Nov 9.
- As a student project (single-author, MIT-licensed research prototype), SiliconCrew is exactly
  what the SRC exists for: poster + presentation at the premier CAD conference, ACM SRC travel
  support, and a pipeline to the ACM SRC Grand Finals. Low effort (extended abstract), high
  networking value, does **not** burn publication novelty for a later full paper.

### 🟡 DATE 2027 — abstract **Sept 13, 2026**, paper **Sept 20, 2026** (firm)
- Design, Automation and Test in Europe, spring 2027. Registration (title/abstract/authors)
  Sept 13 AoE; full paper Sept 20 AoE.
- Top-tier EDA venue with dedicated AI/ML-for-design tracks; DATE has been receptive to
  LLM-agent and benchmark/analysis papers.
- **This is the primary realistic near-term target for Paper A**: two months of runway is enough
  to turn `CVDP_FINAL_RESULTS.md` into a polished 6-page paper, possibly with one added
  experiment (e.g., the "externally-sourced check" lever from §9 of the results doc as a
  mitigation study — turning a taxonomy paper into a taxonomy-plus-fix paper).

### 🟡 ICLR 2027 — full paper **Sept 24, 2026**
- ML flagship (April 2027, Brazil). Fit only for Paper A reframed for an ML audience:
  "self-verification is structurally blind to comprehension errors in agentic code generation" —
  a general claim about LLM agents, with hardware as the domain. Higher risk/reward than DATE;
  reviewers will demand more than one benchmark. Only worth it if extending beyond CVDP.

### 🟡 NeurIPS 2026 workshops (e.g., ML for Systems) — CFPs Aug–Sept, deadlines ~late Aug–Sept 2026
- Workshops run Dec 11–13, 2026 (Sydney/Paris/Atlanta). The **ML for Systems** workshop is a
  recurring, well-matched home for Paper C (leak-gated benchmarking) or a condensed Paper A.
  Non-archival at most workshops, so it does not consume novelty — a good "get feedback before
  DAC/LAD" move. Watch mlforsystems.org for the 2026 CFP.

### 🟢 DAC 2027 — research deadline expected **~mid-November 2026**
- The flagship "Chips to Systems" conference (summer 2027). DAC 2026's research deadline was
  November 2025, so expect ~Nov 2026 for DAC 2027 (CFP not yet posted as of this writing).
- DAC also offers **Late-Breaking Results** (~Feb 2027), **PhD Forum**, and an AI/design track
  that has been saturated with LLM-for-EDA content — competitive, but Paper A's
  integrity-and-failure-analysis angle differentiates against the capability-claims crowd.

### 🟢 LAD 2027 — expected deadline **~early March 2027**
- See §2. The flagship target; plan for the strongest version of Paper A (+ mitigation results).

### ⚪ Missed for this cycle (for reference)
- **MLCAD 2026** (Jeju, Sept 7–9, 2026): paper deadline May 16, 2026 — passed. MLCAD 2027 is a
  natural fit (ACM/IEEE Symposium on ML for CAD; deadline ~May 2027).
- **NeurIPS 2026 main / Datasets & Benchmarks**: May 2026 deadline — passed. The D&B track would
  have suited the leak-gated CVDP pipeline; NeurIPS 2027 (~May 2027) remains an option.
- **ICCAD 2026 main track**: April 14, 2026 — passed; ICCAD 2027 deadline ~April 2027.

### Journals (rolling, no deadline)
- **IEEE TCAD** and **ACM TODAES** both accept LLM-for-EDA work and TODAES in particular has run
  special issues on ML/LLM for design automation. A journal version of Paper A+B combined
  (system + analysis) is the right long-form home after the conference version lands.

---

## 4. Recommended strategy

| When | Action | Venue | Which paper |
|---|---|---|---|
| **Tonight (Jul 10–11)** | Register title+abstract (free option; decide on the PDF by Jul 18) | ASP-DAC 2027 | A |
| **By Jul 31** | Submit SRC extended abstract | ICCAD 2026 SRC | B (system, as student research) |
| **Jul 30–31** | Attend / network if possible | LAD 2026, Stanford | — |
| **Now → Aug** | Post arXiv preprint of the CVDP results + leak-gating methodology | arXiv | A/C |
| **Sept 13 / 20** | Primary submission | **DATE 2027** | A (+ mitigation experiment) |
| **Sept 24** | Optional, only with multi-benchmark evidence | ICLR 2027 | A (ML framing) |
| **~Late Aug–Sept** | Workshop paper for feedback | NeurIPS 2026 ML-for-Systems | C |
| **~Nov 2026** | Flagship EDA submission | DAC 2027 | A or B (whichever isn't at DATE) |
| **~Mar 2027** | Best-fit flagship | **LAD 2027** | Strongest evolved version |

Two rules to keep the plan coherent:
1. **Don't double-submit the same paper** — EDA conferences (DAC/DATE/ICCAD/ASP-DAC/LAD) prohibit
   concurrent submission of substantially similar work. The A/B/C split above is designed so each
   venue gets a distinct paper. arXiv preprints are fine for all of them.
2. **The self-verification-gap result is the crown jewel** — spend it at the venue with the best
   audience (DATE 2027 now, or hold the strongest version for LAD 2027/DAC 2027), not at the
   first deadline that happens to be open.

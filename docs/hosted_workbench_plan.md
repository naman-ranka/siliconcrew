# Hosted Workbench Plan

Planning document for `siliconcrew.example.com` — an online sky130 chip-design
environment with an AI assistant on demand. Captures intent, target users,
product shape, UI wireframes, hosted-deployment architecture, and the
implementation phasing.

This is a planning doc. Scope and details will evolve as the work is done.
Cross-references: `docs/pd_orfs_stage_tooling_plan.md`,
`docs/pd_knob_catalog.md`, `docs/pd_stage_implementation_status.md`.


## Intent

Make SiliconCrew the best open-source agentic layer over open-source EDA tools,
lowering the *knowledge* barrier to chip design for students, educators, and
practitioners who do not already have ORFS installed.

Not commercial. Not industrial. The mission is **accessibility**: someone with
a browser and curiosity should be able to design, simulate, synthesize, and
inspect a sky130 chip without first learning OpenROAD, Docker, or YAML
specs.

The local clone path stays the production-grade endpoint. The hosted version
is the on-ramp.


## Target audiences

| Audience | Why they care | What they need |
|---|---|---|
| **Students** taking a digital-design course | Want to try their homework RTL through a real flow without installing ORFS | Upload RTL, run lint/sim/synth, see waveforms and PPA, get debug help |
| **Educators** running labs | Want to demo "spec to GDSII" in 5 minutes during class | One-click examples, transparent agent reasoning, sharable session URLs |
| **Hobbyists** doing TinyTapeout-class designs | Have RTL, want PPA and DRC checks fast | BYO RTL, fast synth, downloadable GDSII |
| **AI-curious developers** | Want to see what LLM-driven chip design feels like | Chat-driven flow, transparent tool calls |
| **MCP power users** | Already use Claude Desktop / VS Code / Codex | Remote MCP endpoint, paste one URL into existing config |

Note: not aiming at industrial EDA users. Designs at industrial scale
(>10k cells, multi-clock, complex floorplans) belong on the local clone.


## Product shape

Two interaction modes inside **one** product, not two separate apps.

**Mode A — Agentic spec→GDS**:
*"Describe what you want, the agent designs it."* User talks, agent writes RTL,
TB, runs the flow. Existing main-line flow.

**Mode B — Online IDE workbench**:
*"Bring your own RTL. Click buttons to run lint/sim/synth. Ask the agent when
stuck."* User uploads files, drives the flow manually, the agent is a sidebar
that uses the same tools on the same workspace when asked.

Both modes share the same backend, same tools, same workspace, same artifacts.
The mode is implicit — there's no toggle. Whether the chat or the user is
driving, the tools and the file state are the same.


## Why hybrid (not agentic-only)

- **Audience expansion**: agentic-only tops out at learners. Hybrid serves
  practicing engineers too — the people whose endorsement legitimizes the
  project in EDA circles.
- **Pedagogical sweet spot**: "AI helps you fix existing RTL" is a more
  honest and more valuable claim than "AI writes chips from scratch." It
  is also more credible to engineers skeptical of AI hype.
- **Differentiation**: EDA Playground exists for simulation. No
  browser-based sky130 synthesis-to-GDS with PPA exists. Filling that gap
  AND adding an AI assistant is the unique offering.
- **Existing tool surface supports it**: the 22 LangChain `@tool` entries
  in `src/tools/wrappers.py` operate on the workspace, not on the agent's
  intent. They work identically whether files came from `write_file`
  (agent) or upload (user). The hybrid UI is mostly a frontend change.


## Wireframes

ASCII; not visual-final. Source of truth for layout intent. Translate to
React/Tailwind in `frontend/components/workbench/` or to Claude Design.

### 1. Landing page

```
+--------------------------------------------------------------------------------------+
|  SiliconCrew                            [About]  [Docs]  [GitHub]  [Sign in with G]  |
+--------------------------------------------------------------------------------------+
|                                                                                      |
|                    Design chips in your browser. Free. Open source.                  |
|                                                                                      |
|             Sky130 RTL-to-GDSII flow with an AI assistant on demand.                 |
|                                                                                      |
|                                                                                      |
|         +---------------------------------+  +---------------------------------+     |
|         |                                 |  |                                 |     |
|         |   Start with a spec             |  |   Bring your own RTL            |     |
|         |                                 |  |                                 |     |
|         |   Describe what you want,       |  |   Upload Verilog files, run     |     |
|         |   the agent designs it.         |  |   lint / sim / synthesis,       |     |
|         |                                 |  |   ask the agent when stuck.     |     |
|         |     [ Start designing > ]       |  |     [ Open workbench > ]        |     |
|         |                                 |  |                                 |     |
|         +---------------------------------+  +---------------------------------+     |
|                                                                                      |
|                                  - or -                                              |
|                                                                                      |
|   Use it from your existing AI tool (Claude Desktop / VS Code / Codex):              |
|                                                                                      |
|     {                                                                                |
|       "mcpServers": {                                                                |
|         "siliconcrew": {                                                             |
|           "url": "https://mcp.siliconcrew.dev",                                      |
|           "auth": "<token from your dashboard>"                                      |
|         }                                                                            |
|       }                                                                              |
|     }                                                                                |
|                                                                                      |
|   [ Examples ]  [ Tutorial ]  [ How it works ]                                       |
|                                                                                      |
+--------------------------------------------------------------------------------------+
```

Notes:
- Two CTAs make "two modes" explicit on first impression.
- MCP config snippet on landing teaches the reader the project is more than
  a web UI. This is the differentiation moment.
- Sign-in is non-modal — anonymous trial is allowed; sign-in only required
  when the user tries to run synthesis or save sessions.


### 2. Empty workspace — entry-point fork

```
+--------------------------------------------------------------------------------------+
| SiliconCrew    Session: my-first-design        [naman@asu.edu]  Quota: 8/10 runs    |
+--------------------------------------------------------------------------------------+
| Files                  |  Workspace                                                  |
|                        |                                                             |
|  (empty)               |  +------------------------------------------------------+   |
|                        |  |                                                      |   |
|  [+ Upload]            |  |          What do you want to do?                     |   |
|  [+ New file]          |  |                                                      |   |
|                        |  |   > Design from a spec                               |   |
|  ----                  |  |     The agent writes RTL + testbench for you.        |   |
|  Actions               |  |                                                      |   |
|                        |  |   > Upload existing RTL                              |   |
|  [Run Lint]   disabled |  |     You bring the files, click buttons to run.       |   |
|  [Run Sim]    disabled |  |     The agent helps when you ask.                    |   |
|  [Run Synth]  disabled |  |                                                      |   |
|                        |  |   > Try an example                                   |   |
|  ----                  |  |     - counter_4bit       (2 files, 30 sec)           |   |
|  Sessions              |  |     - fifo_8x8           (2 files, 1 min)            |   |
|  > my-first-design     |  |     - fir_filter_8tap    (2 files, 2 min)            |   |
|    counter-demo        |  |     - simple_cpu         (5 files, 5 min)            |   |
|    fir-attempt         |  |                                                      |   |
|                        |  +------------------------------------------------------+   |
|                        |                                                             |
+--------------------------------------------------------------------------------------+
|  AI Assistant                                                                [^]     |
|                                                                                      |
|  Type a message or try: "design me a 4-bit counter"                            [>]   |
+--------------------------------------------------------------------------------------+
```

Notes:
- Three entry points are visually equal — let users self-select.
- Examples library is a third option, not a "wow look at this." Shortest
  path from "interested" to "GDSII on screen."
- Quota indicator (`8/10 runs`) always visible. Sets honest expectations.
- Chat is always available at the bottom, collapsed to one line until
  clicked.


### 3. Active workbench — user-driven, sim just failed

```
+--------------------------------------------------------------------------------------+
| SiliconCrew    Session: my-fifo-debug          [naman@asu.edu]  Quota: 7/10 runs    |
+--------------------------------------------------------------------------------------+
| Files                  | [Editor] [Wave] [Schem] [Layout] [Report]  > my_fifo.v      |
|                        |                                                             |
|  > my_fifo.v           |   1  module my_fifo (                                       |
|    my_fifo_tb.v        |   2      input clk, rst,                                    |
|                        |   3      input wr_en, rd_en,                                |
|  [+ Upload]            |   4      input [7:0] data_in,                               |
|  [+ New file]          |   5      output reg [7:0] data_out,                         |
|                        |   6      output full, empty                                 |
|  ----                  |   7  );                                                     |
|  Actions               |   8      reg [7:0] mem [0:7];                               |
|                        |   9      reg [2:0] wr_ptr = 0;                              |
|  [Run Lint]    ok      |  10      reg [2:0] rd_ptr = 0;                              |
|  [Run Sim]     FAIL    |  11      reg [3:0] count = 0;                               |
|  [Run Synth]   disabled|  12      ...                                                |
|                        |  -------------------------------------------------------    |
|  ----                  |  Sim output:                                                |
|  Latest                |    t=240 ERROR: expected data_out=0xAA got 0xBB             |
|  lint passed (2 warn)  |    t=250 ERROR: full flag asserted late                     |
|  sim FAILED @ 240ns    |    TEST FAILED: 2 errors                                    |
|                        |                                                             |
|                        |  [Open waveform at t=240 >]                                 |
|                        |                                                             |
+--------------------------------------------------------------------------------------+
|  AI Assistant                                                                [^]     |
|                                                                                      |
|  Click [^] to open chat, or try: "why is my sim failing?"                       [>]  |
+--------------------------------------------------------------------------------------+
```

Notes:
- Top tabs (Editor / Wave / Schem / Layout / Report) reuse the existing
  artifact viewers in `frontend/components/artifacts/`.
- "Latest" panel shows current state at a glance, no scrolling output.
- `[Run Synth] disabled` until sim passes — guides the workflow without
  nagging.
- `[Open waveform at t=240 >]` is contextual deep linking: a hyperlink in
  the sim output that jumps the user to the right place in the waveform
  viewer.
- Chat panel collapsed; one-liner invites a question but does not
  interrupt.


### 4. Same workspace, agent chat expanded — the debug demo

```
+--------------------------------------------------------------------------------------+
| SiliconCrew    Session: my-fifo-debug          [naman@asu.edu]  Quota: 7/10 runs    |
+--------------------------------------------------------------------------------------+
| Files     | Editor   > my_fifo.v               | AI Assistant                  [v]   |
|           |                                    |                                      |
| > my_fifo | 13  always @(posedge clk)          | You: why is sim failing?             |
|   ...tb.v | 14    if (rst) begin               |                                      |
|           | 15      wr_ptr <= 0;               | Agent: Investigating...              |
| [+ Upload]| 16      rd_ptr <= 0;               |                                      |
|           | 17    end else begin               |   > read_file(my_fifo_tb.v)          |
| ----      | 18      if (wr_en)                 |   > waveform_tool(t=240ns,           |
| Actions   | 19   >    count <= count + 1;     |       signals=[full,wr_en,count])    |
| [Lint] ok | 20      if (rd_en)                 |                                      |
| [Sim] FAIL| 21        count <= count - 1;     | Found it. The `full` flag is         |
| [Synth]   | 22    end                          | derived combinationally from         |
|           |                                    | `count == 8`, but the TB checks it   |
| ----      |                                    | the same cycle `wr_en` deasserts.    |
| Latest    |                                    | One-cycle race: `count` is still 7   |
| sim FAIL  |                                    | when `full` should be high.          |
|   @ 240ns |                                    |                                      |
|           |                                    | Fix options:                          |
|           |                                    |  1. Register `full` (1 cycle delay,  |
|           |                                    |     simplest, matches TB).            |
|           |                                    |  2. Change TB to check `count == 7   |
|           |                                    |     && wr_en` (no RTL change).        |
|           |                                    |                                      |
|           |                                    |   [Apply fix #1]  [Show me first]    |
|           |                                    |                                      |
|           |                                    | Type a follow-up...             [>]  |
+--------------------------------------------------------------------------------------+
```

Notes:
- Chat panel expansion narrows the editor; 3 columns.
- Tool calls appear inline as badges: `> read_file(...)`, `> waveform_tool(...)`.
  Users see *what* the agent is doing without clicking each call open.
  This is the agent's reasoning being transparent — pedagogically valuable.
- Agent gives multiple fix options with a one-line tradeoff, never
  auto-applies.
- `[Apply fix]` / `[Show me first]` — user always approves changes.


### 5. After synthesis — PPA view with parent-vs-child comparison

```
+--------------------------------------------------------------------------------------+
| SiliconCrew    Session: my-fifo-debug          [naman@asu.edu]  Quota: 5/10 runs    |
+--------------------------------------------------------------------------------------+
| Files                | [Editor] [Wave] [Schem] [Layout] [Report]  > synth_0003       |
|                      |                                                               |
| > my_fifo.v          | +-----------------------------+   PPA Summary                 |
|   my_fifo_tb.v       | |                             |                               |
|                      | |  [ layout image rendered ]  |   Area:    1842 um^2          |
| ----                 | |   sky130hd, std-cell grid   |   Cells:   312                |
| Actions              | |   routing visible           |   WNS:     +0.18 ns  met      |
|                      | |                             |   TNS:     0 ns               |
| [Lint]  ok           | |                             |   Fmax:    108 MHz            |
| [Sim]   ok           | |                             |   Power:   1.42 mW            |
| [Synth] ok           | |                             |                               |
|                      | +-----------------------------+   Target: 10 ns @ 100 MHz     |
| ----                 |                                   Achieved: 8% slack margin   |
| Run history          |                                                               |
| > synth_0003 ok now  | Stage status:                                                 |
|   synth_0002 FAIL    |   constraints ok  synth ok  floorplan ok  place ok            |
|   synth_0001 FAIL    |   cts ok  grt ok  route ok  finish ok                         |
|                      |                                                               |
|                      | vs synth_0002 (prior attempt):                                |
|                      |   Area: 1842 down from 2104 um^2   (-12%)                     |
|                      |   WNS:  +0.18 up from -0.40 ns     (closed)                   |
|                      |   Power: 1.42 down from 1.61 mW    (-12%)                     |
|                      |                                                               |
|                      | [ Download GDSII ]  [ Download netlist ]  [ View report ]     |
|                      |                                                               |
+--------------------------------------------------------------------------------------+
|  AI Assistant                                                                [^]     |
|                                                                                      |
|  "How can I push to 200 MHz?" or "Why did area drop?"                          [>]   |
+--------------------------------------------------------------------------------------+
```

Notes:
- Comparison panel is the natural UI surface for `compare_pd_runs`. Now
  it's not just an agent-only feature — it's visible to anyone using
  the workbench.
- Run history with ok/FAIL status, sorted by recency. Click to switch
  context.
- Layout image is the existing artifact viewer.
- Download buttons make the outcome tangible.
- Chat prompt suggests reasonable follow-ups based on current state.


## Cross-cutting UX design principles

| Decision | Rationale |
|---|---|
| 3-column layout (file/actions sidebar + main + chat) | Mirrors VS Code mental model; familiar to dev users |
| Chat is always available, never in the way | Collapsed by default; one-line invitation; no popup nag |
| Manual buttons sit next to the chat path | Validates "agent on tap, not in control" framing |
| Status badges on action buttons (ok / FAIL / disabled / running) | Immediate feedback without scrolling output |
| Contextual deep links ("Open waveform at t=240 >") | Reduces cognitive load — the UI knows what you'd want next |
| Tool calls visible in chat as inline badges | Transparent agent reasoning; pedagogically valuable |
| Quota indicator always visible | Honest about hosted-tier constraints |
| Run history in sidebar with comparison | Surfaces compare_pd_runs to non-agent users |
| Anonymous-tier → signed-in-tier ladder | First touch has no friction; sign-in only when value is delivered |
| Editor read-only in MVP | Defer Monaco IDE features; user edits by reupload or via agent |
| Educational design-size limits enforced server-side | Aligns hosted experience with accessibility mission |


## Hosted deployment architecture

```
+-------------------------------------------------------------+
| Cloudflare / static (free) -> siliconcrew.example.com       |
|   Landing page, demo videos, docs, "Try Online" button      |
+----------------------------+--------------------------------+
                             |
            +----------------+----------------+
            |                                 |
            v                                 v
+-------------------------+    +-------------------------------+
| Cloud Run (backend)     |    | Cloud Run (MCP SSE endpoint)  |
| FastAPI + WebSocket     |    | python mcp_server.py --sse    |
| Auth, session, quotas   |    | Token-authed, BYOK            |
| Scales 0..N, free idle  |    | Same backend, MCP transport   |
+----------+--------------+    +----------+--------------------+
           |                              |
           +-------------+----------------+
                         |
            +------------+------------+
            v                         v
+-------------------------+    +-------------------------------+
| Cloud SQL (Postgres)    |    | Cloud Storage                 |
| Sessions, users,        |    | Workspaces (per-session       |
| quotas, run metadata    |    | prefixes), GDSII, logs,       |
| ~$10-20/month           |    | reports                       |
+-------------------------+    +-------------------------------+
                         |
                         v (job submission)
+-------------------------------------------------------------+
| Cloud Run Jobs (per-synthesis-run ORFS executor)            |
| Pulls openroad/orfs:latest from Artifact Registry           |
| Mounts workspace from Cloud Storage                         |
| Pay-per-second-of-execution, scales to N parallel           |
| ~$0.05-0.10 per typical educational run                     |
+-------------------------------------------------------------+
```

Stack rationale:
- **Cloud Run for backend** = $0 idle, scales to thousands of users
- **Cloud Run Jobs for ORFS** = pay-per-use, parallel by default; 60-min
  cap is fine for educational designs and aligns with the design-size
  limit framing
- **Cloud SQL** for relational data (sessions, users, quotas) — keeps
  the existing SQLite session_manager logic with minimal change
- **Cloud Storage** for artifacts replaces local `workspace/` —
  content-addressable, cheap, browser-downloadable
- **Artifact Registry** caches the 6.46 GB ORFS image (no repeated
  Docker Hub pulls)


### Credit budget (rough estimate, 90 days)

Assumes $300 GCP free credit, modest viral growth.

| Service | Estimated cost |
|---|---|
| Backend Cloud Run idle | ~$0 (scales to 0) |
| Backend Cloud Run active (10-50k requests over 3 months) | ~$15-30 |
| Cloud Run Jobs for ORFS (1000 runs, avg 5 min) | ~$50-100 |
| Cloud SQL (smallest postgres) | ~$30-50 over 3 months |
| Cloud Storage | ~$5-10 |
| Egress (downloads) | ~$10-30 |
| **Total over 90 days** | **~$110-220** |

Realistic capacity: 500-2000 unique users, 1000-3000 synthesis runs.
The bigger risk is *abuse* (one user retry-looping), not raw demand.
Per-user quotas + rate limits mitigate this.

After credits expire, options: migrate to Hetzner (~$10/month for a
beefy VM with Docker), university hosting, GitHub Sponsors, or sunset
the hosted version with the code path preserved for self-hosting.


## Backend changes required (before going live)

Roughly sequenced; some can parallel.

| Change | Description | Estimate |
|---|---|---|
| 1. **Auth layer** | Google OAuth via fastapi-users or hand-rolled. Token-based auth for MCP endpoint. | 2-3 days |
| 2. **Workspace path externalization** | Today many places hardcode workspace paths and Docker volume mounts. Refactor to a `WorkspaceProvider` abstraction (local filesystem locally; Cloud Storage in hosted mode). **The biggest single piece.** | 3-5 days |
| 3. **ORFS runner abstraction** | Today `_run_orfs` shells out to `docker run`. For hosted mode, submit a Cloud Run Job instead. Same input/output contract. | 2-3 days |
| 4. **Per-user quotas + rate limits** | slowapi or equivalent. Limits: 10 synth runs/day, 60 min compute/month, 1 concurrent job. | 1-2 days |
| 5. **BYOK plumbing** | Frontend asks for LLM API key on first run; encrypted server-side. Backend reads from session, not env. | 2 days |
| 6. **MCP token auth** | Token middleware on `mcp_server.py`. User signs in to web, generates token, pastes into their MCP config. | 1 day |
| 7. **Containerize backend + MCP server** | Dockerfile.backend, Dockerfile.mcp, GCP build config. | 1-2 days |
| 8. **CI/CD** | GitHub Actions to Artifact Registry, then deploy to Cloud Run. | 1 day |

**Total realistic estimate: 3-4 weeks of focused work.**


## Frontend changes required

| Change | Description | Estimate |
|---|---|---|
| 1. **File upload UI** | Drag-drop or paste-text to workspace; uses existing `write_file` tool path. | 1 day |
| 2. **File tree sidebar** | List files in workspace; click to view in editor tab. | 1 day |
| 3. **Read-only editor view** | Monaco editor in read-only mode; defer write/autocomplete. | 1 day |
| 4. **Run-action buttons** | Lint / Sim / Synth buttons that call existing tools directly. Status badges. | 2 days |
| 5. **Examples library** | Curated 5-10 designs with one-click load. Mostly content, not code. | 1-2 days |
| 6. **Tool-call badges in chat** | Render agent's `> read_file(...)` style lines inline. Existing message component, new style. | 1 day |
| 7. **Run history + comparison view** | Surface `compare_pd_runs` results in the PPA view. | 1-2 days |
| 8. **Landing page** | Two-CTA hero, MCP config snippet, examples grid. | 1-2 days |
| 9. **Auth UX (anonymous → signed-in ladder)** | Sign-in gate on synth, not on lint/sim. Quota indicator in header. | 1 day |

**Total realistic estimate: 1.5-2 weeks of frontend work.**


## Deployment phasing

### Phase 1 — host the web UI only, BYOK, gated demo (1.5 weeks)

- Auth + per-user sessions + quotas
- Cloud Run for backend
- ORFS runner abstraction + Cloud Run Jobs
- Cloud Storage workspace
- Launch as "early access, sign up for invite"
- Limits abuse risk while iteration continues

### Phase 2 — open public access + remote MCP (1 week)

- Drop invite gate
- Add MCP SSE endpoint with token auth
- Documentation: "use it in your Claude Desktop"
- Public launch (HN / Reddit / Twitter / EDA mailing lists)

### Phase 3 — sustainability planning (parallel, ongoing)

- Cost dashboard, weekly burn check
- If usage is healthy, plan migration to Hetzner / university hosting
  before credits expire
- If usage is low, sunset the hosted version, keep code path for
  self-hosting


## MVP scope (build order)

If sequencing greenfield, build in this order to maximize early value:

1. **Wireframe 2** (entry-point fork + examples library) — biggest single
   UX win, lowest engineering cost; library is mostly content
2. **Wireframe 3** (manual workbench with run buttons) — translates
   existing tool calls into UI buttons; ~3-4 days
3. **Wireframe 5** (PPA / comparison view) — already half-built; expose
   `compare_pd_runs` results
4. **Wireframe 4** (chat sidebar + tool-call badges) — the magical demo;
   chat can ship before inline badges
5. **Wireframe 1** (landing page) — last; you want to see what you're
   marketing before designing the marketing page


## Explicitly out of scope (defer or skip)

- Multi-file projects with include graphs / library management
- Monaco autocomplete, syntax variants, formatting
- Full collaborative editing (Google-Docs-style multi-cursor)
- Mobile responsive UI (acknowledge; defer)
- Asap7 / multi-PDK support on hosted version (sky130 only)
- Industrial-scale designs (> 2000 LOC or > 30 min synthesis)
- "Designer mode" custom styling beyond shadcn/ui defaults
- Local-LLM path on the hosted version (BYOK only; local fallback is
  for self-hosted)
- Auto-save of every run (sessions are ephemeral on anonymous tier)


## Open questions to decide before launch

- **Anonymous tier limits.** What can users do without signing in?
  Suggested: view examples, run lint, run sim. *Cannot*: synthesis,
  save sessions, use MCP.
- **Default LLM model for BYOK.** When the user provides a Gemini /
  OpenAI / Anthropic key, do we pick model defaults per provider or
  let them choose? Suggested: provider-best default with override.
- **Session expiry.** How long do anonymous sessions live? Signed-in
  sessions? Suggested: 24 hours anonymous, indefinite signed-in
  (with a manual delete button).
- **IP/data policy wording.** Be explicit and prominent: ephemeral by
  default, deletable on demand, never used for training, never shared.
  Match TinyTapeout's tone.
- **Examples curation.** Which 5-10 designs ship in the examples
  library? Suggested: counter_4bit, mux_4to1, fifo_8x8, fir_8tap,
  simple_alu, edge_detector, pwm_generator, uart_tx, single-cycle
  CPU. Each must build cleanly at a documented clock.
- **MCP rate limits.** How aggressive? Suggested: same as web quota
  (10 synth runs/day, 60 min compute/month) shared across both
  interfaces.
- **TinyTapeout integration.** Out-of-scope for v1, but consider as
  Phase 4: a `tinytapeout` synth target that produces submission-ready
  bundles.


## What this unlocks

The hosted version is the single biggest accessibility lever the
project has. Without it, reach is bounded by who's willing to install
Docker + ORFS. With it, reach is anyone with a browser and an LLM key.

The remote-MCP angle is the unfair advantage. Hosted MCP servers in
the EDA space are essentially nonexistent. Launch story:
*"SiliconCrew now hosted at siliconcrew.example.com — design chips in
your browser, or paste one URL into Claude Desktop to design chips
from your existing AI assistant."* That's a launch worth sharing.


## Strategic re-frame after building this

Project positioning changes from:

> "LLM agent for chip design"

to:

> "Online sky130 EDA environment with an AI assistant"

The second positioning is more credible, more honest, and ages better
as the broader market gets more skeptical of AI hype. "AI assistant
*in* an EDA environment" is a defensible claim that survives
post-hype scrutiny. "AI agent *replaces* the EDA flow" does not.


## Related docs

- `docs/pd_orfs_stage_tooling_plan.md` — design intent for the
  staged-PD retry tooling
- `docs/pd_knob_catalog.md` — validated ORFS knobs the agent should
  use
- `docs/pd_stage_implementation_status.md` — current implementation
  state and real-ORFS validation evidence
- `prompts/architect/architect_prompt_v2.md` — system prompt with
  the PD diagnosis + retry guidance


## Appendix: Concurrency, Editor & Git Implementation Notes (Gemini Discussion)

### 1. Simple Concurrency Resolution (The Editor Lock + Diff)
To resolve conflicts between user edits (Mode B) and agent edits (Mode A) without the initial overhead of CRDTs:
* **UI State Lock**: When the agent begins editing, set the Monaco Editor to `readOnly: true` and display a loading overlay (e.g., *"Silicon Codex is analyzing and refactoring..."*).
* **Monaco Diff Viewer**: Instead of overwriting the user's workspace silently, render a side-by-side proposed diff using `<MonacoDiffEditor />`. Provide clear **[Keep Mine]** and **[Use AI Proposed Fix]** CTAs.

### 2. Lightweight Starter Stack
* **Frontend**: React + `@monaco-editor/react` (incredibly simple wrapper, zero webpack configuration needed).
* **Backend**: FastAPI WebSockets for streaming simulator outputs (Cocotb/Verilator) to the frontend.
* **State**: Keep standard React state arrays for active files.

### 3. Scalable Base for Future Upgrades
This architecture is modular and allows drop-in upgrades as the product matures:
* **Collaborative AI Typing**: Swap standard Monaco state for **Yjs** (`y-monaco`) to support Google-Docs style live cursor tracking and multi-cursor typing.
* **Git Safety Net**: Initialize a hidden `.git` repository inside each session's workspace folder. The agent commits its changes to separate branches, letting the user inspect proposed changes via standard Git diffs.
* **Wasm Simulators**: Compile Icarus Verilog or Verilator to WebAssembly and run them directly in the user's browser, bypassing Cloud Run Job compute costs for simple lints/simulations.


## Document status

Plan, not commitment. Revise as the work proceeds. Update phasing estimates with actual numbers once Phase 1 ships.


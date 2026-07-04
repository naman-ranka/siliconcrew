# Session Templates, Forking, and Publish-to-Gallery Roadmap

## Intent

The purpose of session templates and forking is to turn completed SiliconCrew runs into reusable, inspectable, and safely extensible product experiences. A user should be able to open a curated session that already demonstrates a design moving from specification through RTL generation, verification, synthesis, and artifacts, then fork that session into an isolated workspace where future changes do not mutate the source.

This is primarily an onboarding, education, demo, benchmark, and reproducibility capability. It lets SiliconCrew show the full design process, not just the final files. Users can inspect how the LLM used tools, where it failed, how it recovered, what artifacts were generated, and what evidence supports the final design state.

The core design rule is: source sessions must remain stable; experimentation happens in forks.

## Why This Matters

Blank workspaces are powerful but not self-explanatory. A first-time user may not know what a successful SiliconCrew workflow looks like, what artifacts to expect, how synthesis runs are represented, or how to continue an existing project. Pre-saved sessions solve that by providing complete, concrete examples.

A template session can function as:

- an interactive tutorial;
- a product demo;
- a benchmark result with full provenance;
- a regression example;
- a TinyTapeout-style starter design;
- a reusable starting point for further exploration.

The user experience should be closer to opening a finished engineering notebook than opening a static code sample. The user should see the files, generated artifacts, chat/tool trajectory, and final results, then choose to fork if they want to continue.

## Current Session Model

A session is not just a folder and not just a database row. A complete session spans multiple pieces of state:

- session metadata: owner, display name, project, model, timestamps, token and cost counters;
- workspace contents: specs, RTL, testbenches, simulation outputs, waveforms, synthesis runs, logs, reports, layouts, generated images, and manifests;
- chat threads: one or more conversations under the same workspace;
- LangGraph checkpoint state keyed by chat thread id;
- run/attempt metadata persisted in the workspace;
- hosted workspace storage state when running in cloud mode.

A production-quality fork must define which of those pieces are copied, which are rewritten, and which remain historical evidence.

## Template vs Fork Semantics

A template is a stable source session. It may be platform-curated, benchmark-generated, or later submitted by a user for publication. It should be treated as immutable from the perspective of normal users.

A fork is a new user-owned session derived from a source. The fork should be writable, independent, and safe to mutate. Any new chat messages, file edits, simulation runs, synthesis runs, and reports belong to the fork only.

This distinction avoids a common failure mode: users accidentally continuing a public demo and corrupting the canonical example.

## Product Flow

The intended product flow is:

1. A user opens a gallery, examples page, benchmark page, or onboarding flow.
2. The user selects a completed source session.
3. SiliconCrew shows a read-only preview of the workspace, artifacts, runs, and optionally chat/tool history.
4. The user clicks fork or create from template.
5. SiliconCrew creates a new user-owned session from that source.
6. The user is redirected into the fork.
7. The user can now ask the LLM to understand the project, modify it, rerun simulation, compare synthesis runs, or continue the design.

The source session remains unchanged.

## Implementation Scope Levels

There are three useful implementation levels.

### Level 1: Workspace-Only Template Fork

Copy the template workspace into a new session and create a fresh chat thread.

This gives users all visible design assets and generated artifacts, but does not preserve the original chat as a continuation point. It is the lowest-risk first implementation and is enough to validate the onboarding and gallery experience.

### Level 2: Full Session Fork

Copy the workspace, session metadata, chat thread rows, and LangGraph checkpoint state with rewritten ids and ownership.

This provides the strongest continuity: the fork can show the original conversation/tool history and allow the user to continue from that context. This is more valuable but requires careful checkpoint copying and failure handling.

### Level 3: Hosted, Versioned, Large-Artifact Templates

Support production template operations in hosted mode, including immutable source sessions, template versions, cloud-storage-efficient copies, provenance tracking, large synthesis artifacts, quotas, and admin review/publish flows.

This is the scalable version needed for curated demos, benchmark galleries, and eventually user-submitted sessions.

## Technical Assessment

This feature does not require a fundamental rewrite of the session architecture. The existing model already has session-scoped workspaces, metadata, threads, and checkpoint-backed chat state. The work is mainly about formalizing template/fork semantics and making the copy operation reliable.

The complexity is not uniform:

- workspace-only forks are straightforward;
- full forks with chat/checkpoint continuity are moderate complexity;
- hosted template galleries with large artifacts, versioning, and publish/review flows are higher complexity.

The critical implementation areas are ownership, checkpoint remapping, artifact storage, provenance, and failure recovery.

## Checkpoint and Thread Handling

The most sensitive part of a full fork is chat/checkpoint state. Chat threads and LangGraph checkpoints must not collide with the source session. A robust implementation should generate new thread ids for the fork, copy chat thread metadata to the new session, and copy checkpoint rows by rewriting old thread ids to new thread ids.

The fork operation should avoid half-created states. If files are copied but checkpoint copying fails, the product should either roll back, mark the fork as workspace-only, or clearly communicate that chat continuity was not preserved.

## Workspace and Artifact Handling

Workspace copying is conceptually simple but can be operationally expensive. Some sessions may include large synthesis directories, GDS files, logs, waveforms, generated plots, and report trees.

For local mode, a filesystem copy is acceptable for small examples. For hosted mode, the implementation should eventually use object-storage-native copy operations or a more granular artifact storage model instead of repeatedly downloading and re-uploading entire workspace archives.

Historical logs should generally remain truthful. Active metadata may need controlled rewriting if it contains old session ids or absolute paths that future tools consume. Blind search-and-replace across the whole workspace is risky, especially with binary artifacts and historical logs.

## Local Mode Strategy

Local/self-hosted mode should not depend on hosted state by default. Small curated templates should be stored in the repository or in a repo-managed examples bundle so a local developer can clone the repo and immediately create sessions from examples.

Recommended local behavior:

- ship lightweight examples with the repo;
- copy a selected example into `workspace/<new_session_id>/`;
- create normal local session metadata;
- start with a fresh chat for Level 1, or import bundled chat/checkpoint data only if the bundle format explicitly supports it;
- avoid silently pulling hosted templates unless the user explicitly imports them.

Large completed examples should generally not live directly in the repo if they include heavy synthesis artifacts.

## Hosted Mode Strategy

Hosted mode can support richer examples because large artifacts can live in platform storage. Templates can be represented as platform-owned immutable sessions or as template bundles stored outside normal user session lists.

Recommended hosted behavior:

- expose curated templates through a gallery or onboarding flow;
- allow read-only preview;
- fork templates into user-owned sessions;
- track source template id and version;
- optimize storage copies for large sessions;
- prevent mutation of the canonical template.

## TinyTapeout-Style Examples

TinyTapeout-style projects are a strong fit for this workflow. A completed template might include:

- the initial design prompt or spec;
- generated RTL;
- wrapper/top-level integration files;
- testbenches or cocotb tests;
- passing simulation output;
- waveforms;
- constraints;
- synthesis logs and reports;
- layout/GDS artifacts if available;
- a final design report.

Examples could include a PWM generator, UART transmitter, SPI block, small FIFO, VGA pattern generator, tiny ALU, or TinyTapeout-ready wrapper. A user could fork one and ask the LLM to change parameters, add features, rerun verification, or compare synthesis results.

## Benchmark and Showcase Sessions

Benchmark sessions should be treated as inspectable evidence. Instead of publishing only a pass/fail result, SiliconCrew can show the complete path:

- the original benchmark prompt/spec;
- all generated files;
- tool calls and outputs;
- failed attempts and fixes;
- final passing verification;
- synthesis attempts and final metrics;
- final reports and artifacts.

These benchmark sessions should usually be read-only canonical records. Users who want to experiment should fork them. That preserves benchmark integrity while still making the examples interactive.

## Future Requirement: User Publish to Deployed Gallery

A later requirement is for a user to push one of their own sessions into the deployed examples/gallery directory. This is not real-time collaboration and not direct user-to-user sharing. It is closer to a publish flow:

1. A user completes a useful session.
2. The user chooses to submit or publish it.
3. SiliconCrew packages the session workspace and selected metadata.
4. The platform stores it in a deployed gallery, examples directory, or review queue.
5. Other users can later preview it and fork it like any other template.

This should not be treated as unrestricted sharing. It needs product controls:

- decide whether publishing is immediate or requires review;
- scrub or warn about secrets, private prompts, API keys, proprietary files, and large artifacts;
- decide whether chat history is included, redacted, or omitted;
- record the source user and template provenance where appropriate;
- version the published session;
- ensure published sessions are immutable once accepted;
- allow admins or maintainers to remove outdated or unsafe templates.

For local mode, the equivalent could be an export/import bundle: a user exports a session bundle and another local install imports it as a template. For hosted mode, publishing can write into the platform-managed template/gallery storage.

## Non-Goals for the Initial Work

The initial template/fork work should not attempt to implement live multi-user collaboration, simultaneous editing, shared writable sessions, or real-time co-piloting. Those features introduce different complexity around concurrency, permissions, cost attribution, and conflict handling.

The first practical target should be read-only source sessions with user-owned forks.

## Recommendation

Implement this in phases:

1. Start with curated read-only templates and workspace-only forks.
2. Add full session forks with chat/checkpoint continuity once the UX is proven.
3. Add hosted template versioning and efficient large-artifact copying.
4. Add user publish-to-gallery as a controlled future workflow, not as unrestricted sharing.

The strategic intent is to make successful SiliconCrew sessions reusable as learning material, reproducible evidence, and starting points for new work while preserving the integrity of the original runs.

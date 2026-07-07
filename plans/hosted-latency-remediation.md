# Hosted latency remediation — requirements & intent

**Status:** IMPLEMENTED (4B, 4C quick cuts, 4A) on
`claude/hosted-latency-remediation-obkib4`; 4C warm-keep deferred to its own
plan as §4C intended. This section is authoritative over the body below.

**What shipped (in landing order):**

1. **4B — Codex once-per-turn background sync.** The extension-turn branch in
   the chat WS handler now fires the same turn-end background workspace sync
   the native path uses (it previously `continue`d past it — Codex never got a
   parent-side sync). The Codex engine sets
   `SILICONCREW_MCP_DEFER_WORKSPACE_SYNC=1` for its bound MCP subprocess, which
   then skips the per-mutating-tool blocking upload; parent and subprocess
   share the scratch dir, so the turn-end sync persists everything. Decision on
   the §9 open question: once-per-turn (native parity) is sufficient — same
   crash exposure as the native agent. Non-Codex MCP clients are unchanged.
2. **4C quick cuts.** `SILICONCREW_SCHEMA_READY=1` (set by the engine for the
   subprocess; parent provisioned at boot) skips `init_schema()` DDL; WorkOS
   token verification resolves signing keys through a TTL'd (600s) file-cached
   JWKS on instance-local disk (kid miss forces one refresh; verification
   itself unchanged, fail-closed); `src.agents.architect` is imported lazily in
   mcp_server (it only backs the prompt-file fallback; ~0.1s warm, more cold).
3. **4A — incremental sync.** Answer to §9: per-file **content-addressed
   blobs** (`workspaces/<sid>/.sc_blobs/<sha256>`) + one small **manifest
   object written LAST** as the atomic commit point (its content hash is the
   cache token — no new generation API). Blobs are immutable, so any manifest
   names an internally consistent tree; a crash mid-sync leaves orphan blobs
   but consistent readable state; deletes/renames propagate because a cold
   instance reconstructs exactly the manifest's tree. Manifest records
   mode/mtime_ns/symlinks/empty dirs (tree-faithful hydration — the mtime
   sharp edge). A git-index-style stat-cache sidecar (racy-timestamp guard)
   skips re-hashing; uploads stage through hashed snapshots so concurrent
   writes can never store bytes under a mismatched hash (review finding). A
   no-change sync costs zero writes. Legacy tar workspaces hydrate as before,
   convert on first sync, and the stale tar is deleted; stores without the
   raw-object surface keep tar behavior; self-host untouched.

**Deferred (documented, not dropped):** 4C warm-keep (own plan, per §8.4);
blob GC for superseded content (joins run retention/GC); live-deploy
measurement of the §6 numbers (the F2-style before/after on rev N+1 — the
regression tests prove the mechanism, the deploy proves the wall-clock);
GoogleOAuthVerifier keeps google-auth's own fetching (WorkOS is the hosted
path).

**Rollout note (one-time, per session):** during a mixed-revision deploy
window, an old-code instance reads the legacy tar, which is stale (or deleted)
for sessions already converted by new code. Warm old instances keep serving
their materialized scratch; only a cold old instance could see a stale/empty
view until the rollout completes. Convertions happen on first post-deploy
mutating sync, so the exposure is sessions actively written during the flip.

---

The original direction document follows, unchanged.

This is a *direction* document — it states the
problem, the evidence, who is affected, the intent of the fix, and the hard
constraints any implementation must honor. It deliberately does **not** prescribe
the implementation (data structures, function signatures, diffs). The reviewing
agent should turn this into an implementation-grade plan (file:line consumer
sweep, test list, do-NOT fences) per the CLAUDE.md process; the implementing
agent builds from that.

**Owner intent, verbatim in spirit:** the deployed app feels slow in exactly two
ways — a long pause before a hosted agent turn starts, and multi-second latency on
every file write / tool call. Both are *infrastructure* costs, not model costs.
Fix them the boring, industry-standard way. Nothing here may change behavior,
results, or the honesty guarantees — this is purely about speed.

---

## 1. The two problems (root causes, with evidence)

Both are **hosted-mode only**. Self-host is unaffected by construction (see §3).

### Problem A — Full-workspace re-upload on every write ("15s to save a file")
The hosted workspace is persisted to object storage as **one gzipped tar blob per
session**. On every write-back, the provider tars *and* gzips the entire scratch
workspace and uploads the whole thing — even to persist a one-line file edit.

- `CloudWorkspaceProvider.sync()` → `put_tree(key, scratch)` uploads the whole
  tree (`src/platform_engines/workspace_provider.py:325-338`).
- `_tar_dir_to_bytes()` walks and gzips the **entire** scratch dir into one blob
  (`workspace_provider.py:63-68`).
- After synthesis a workspace holds the GDS, all ORFS run dirs (ODB/DEF/SPEF/
  reports), waveforms — tens to hundreds of MB. So a small edit re-uploads all of
  it. That is the observed ~14–16s on `write_file` / mutating tools.
- A per-object seam **already exists but is unused for this path**: `put_file`
  "stores one small raw object (no tarring)" (`workspace_provider.py:~35`).

This is the naive design. The fix is to stop uploading the whole world on every
write.

### Problem B — Cold worker per Codex turn ("~11s before the first token")
The Codex agent is a separate brain reached over MCP. Every user turn throws the
whole thing away and rebuilds it:

- `stream_turn` does `async with sdk_factory(config=config)` **per turn**
  (`src/agents/codex/codex_engine.py:331`); `run_turn` recreates the engine each
  turn (`src/agents/codex/codex_runtime.py:145`).
- That cold-spawns a fresh Python MCP subprocess (`--transport stdio`,
  `startup_timeout_sec=20`, `codex_engine.py:434-457`), which pays, every spawn:
  - a multi-second cold import of the whole tool stack — measured **~2.3s** for
    `import mcp_server` on a warm local box, more on a cold Cloud Run container
    (`mcp_server.py:47` pulls `src.tools.wrappers`, the full LangChain/engine set);
  - **unconditional** DB schema DDL — `SessionManager.__init__` →
    `init_schema()` on a fresh Cloud SQL connection every spawn
    (`src/utils/session_manager.py:29`; DDL in `metadata_store.py`);
  - an identity/token verify with a cold JWKS cache — `_resolve_identity()` →
    `auth_engine.authenticate` per spawn (`mcp_server.py:198,221-225`).
- This is the `[CODEX-TIMING] elapsed_setup` bucket, live-measured at **10.96s**
  on rev 00060/00063 (reports/explore2-codex.md).

Note the two problems are independent and stack on Codex: a Codex turn pays B once
(cold start) and A many times (once per tool call).

---

## 2. What last night's deploy already did (so we don't re-solve it)
The F2 fix (`f095fcb`, live on rev 00063) gated the per-call sync to **mutating**
tools, so hosted **reads** no longer sync at all — read-only Codex/human calls
dropped from ~14s to sub-ms (measured, reports/explore2-codex.md §Leg 2). That is
done. It does **not** help **writes**: a mutating tool still runs the full-tar
`sync()`. Problem A is specifically the remaining write path. Problem B was never
touched.

---

## 3. Who is affected (verified across all surfaces)
The per-call full-sync scope (`run_in_session`) is Codex-only
(`mcp_server.py:925`), but the human IDE and native agent call the *same*
`provider.sync()` at different cadences:

| Surface | Slow first token (B)? | Slow writes (A)? | Evidence |
|---|---|---|---|
| **Self-host (any actor)** | Minor — local SQLite, no Cloud SQL/JWKS | **None** — `LocalWorkspaceProvider` has no upload; the dir *is* the workspace | `src/utils/session_context.py:109-118` (no `sync`); `get_workspace_provider` self-host branch `workspace_provider.py:397-409` |
| **Hosted — native in-app agent** | None — runs in-process, no per-turn subprocess | **No, effectively** — syncs **once per turn**, in the **background** after the "done" frame, so the user never waits | `api.py:1892-1898` (background, non-blocking) |
| **Hosted — human in the IDE** | N/A — no "turn" | **Yes** — each mutating gesture (save/lint/sim/synth-dispatch) runs the full-tar sync **blocking** the response; ~15s once the workspace is heavy | `save_code` → `run_scoped(mutates=True)` → `actions.py:459-461` (awaited) |
| **Hosted — Codex** | **Yes (~11s/turn)** | **Yes, worst** — full-tar sync **per mutating tool call**, many per turn | `mcp_server.py:925` → per-call scope → `request_scope.py` finally sync |

**Takeaways for scoping:**
- Problem A (incremental sync) is the **broad** win — it helps hosted Codex, the
  hosted human IDE, and shrinks the native agent's background uploads. Self-host
  needs nothing.
- Problem B (cold start) is **Codex-only**. The human IDE and native agent do not
  cold-start.
- The native agent is the existing reference for "good": in-process + background,
  once-per-turn sync. The others should converge toward that behavior.

---

## 4. Intent — what "fixed" looks like (direction, not implementation)

### 4A. Incremental / differential workspace sync  ← highest value, do first
**Intent:** a write-back should cost time proportional to *what changed*, not to
the total workspace size. Saving one small file should be a small, fast upload.

High-level direction (the reviewer/implementer chooses among these — do **not**
treat any as decided):
- Persist the workspace as **many per-file objects** (the `put_file` seam already
  exists) instead of one tar blob, and on sync upload only files whose content/
  mtime changed since the last sync; propagate deletes.
- OR keep a manifest of content hashes and upload only changed objects
  (content-addressed / rsync-style delta).
- Whatever the shape, the read/hydrate side (`workspace_for`, currently a
  download-untar) must stay consistent with the new write side, and a cold
  instance must still be able to reconstruct the exact workspace (see §5).

This is the standard approach everywhere (git, `rsync`, `aws s3 sync`, cloud
IDEs). We are moving *to* the standard, not away from it. It is also the piece
with the most surface area and the most correctness risk (§5), which is why it
gets a full plan + review before code.

### 4B. Codex write-back cadence  ← cheap, big Codex win, can ship before 4A
**Intent:** Codex should not block each tool result on a network upload, and
should not upload once per tool call. Converge it toward the native agent's proven
pattern: sync **once per turn**, in the **background**, non-blocking — or, if
per-tool durability is required for crash-safety, make the per-tool sync
non-blocking/coalesced. This removes most of the felt Codex write-lag even without
4A, and 4A then makes each such upload cheap too.

### 4C. Codex cold-start (time-to-first-token)  ← Codex-only, second priority
**Intent:** stop paying a full cold boot before every Codex turn.
- **Quick, low-risk cuts** (help turn 1, safe): skip the redundant `init_schema()`
  when the schema is already provisioned (cheap sentinel/guard); reuse the
  caller's already-resolved identity instead of re-verifying per spawn; trim/lazy
  the MCP import surface so cold import is cheaper.
- **The real fix (bigger, own follow-up):** keep the Codex app-server + its MCP
  child **warm across turns** for a thread, so only turn 1 pays cold start and
  every later turn is near-instant. This is a lifecycle change (hold the
  subprocess, idle-timeout cleanup, crash recovery, memory bounds) and deserves
  its own small plan.

---

## 5. Hard constraints (any implementation MUST honor these)
These are the invariants that make the naive-but-simple current design *safe*;
the fix must preserve every one. Violating any is a bug, not a trade-off.

1. **Twelve-factor / instance-agnostic (invariant 9).** Nothing durable lives on
   instance disk. ANY instance must be able to hydrate the workspace and finalize
   a run from object storage. Incremental sync must leave storage in a state a
   *different, cold* instance can fully and correctly reconstruct — no reliance on
   local state that only the writing instance has.
2. **Atomicity / no torn state.** A reader (or a crash mid-sync) must never see a
   half-written workspace. The current single-blob put is atomic by accident;
   per-object sync must define its own consistency story (ordering, temp-then-
   swap, or a generation/manifest that flips last).
3. **Deletes and renames propagate.** A file removed locally must not linger in
   storage (the tar approach got this free; per-object must handle it explicitly).
4. **Tenancy (invariant 8).** Object keys stay owner/workspace-scoped exactly as
   today; no widening of what a key exposes.
5. **Honest state (invariant 4) & the run-dir-is-the-database (invariant 5).**
   `run_meta.json`/artifacts remain authoritative; the speed change must not
   create a window where a completed run looks unfinished or vice-versa.
6. **Self-host untouched.** `LocalWorkspaceProvider` stays a no-op upload; the
   engine-selection idiom stays intact; self-host must never gain a cloud
   dependency.
7. **Behavior/results identical.** Same files, same sims, same GDS, same manifest,
   same event log. This is a performance change only.
8. **Warm-keep (4C) must not leak across tenants or threads.** A warmed subprocess
   is bound to one session/identity; it must never be reused for another
   owner/session, and must be torn down on session end/idle.

---

## 6. Success criteria (how we'll know it worked)
- **A:** on a post-synthesis hosted workspace, a one-file `write_file` (Codex) and
  a human Monaco save complete in **well under 1s** (today ~15s). Measured the
  same way as the F2 delta — `[CODEX-TIMING]` per-tool elapsed + wall-clock from
  the UI. A regression test proves a single-file write uploads only that file (not
  the whole tree).
- **B/4C:** Codex `elapsed_setup` drops materially on the quick cuts, and to
  ~0 on turns 2+ once warm-keep lands.
- **No regressions:** the full gate suite stays at the known baseline; a
  cross-instance test proves a workspace written incrementally by instance X is
  correctly, completely hydrated by a cold instance Y (the §5.1 invariant); a
  delete/rename test proves propagation (§5.3).
- Self-host gate behavior and timings unchanged.

---

## 7. Non-goals / do-NOT (for this work)
- Do **not** re-solve reads — F2 already made reads skip sync.
- Do **not** touch self-host persistence.
- Do **not** change tool behavior, manifest semantics, the event log, or any
  honesty/verdict logic.
- Do **not** couple 4A and 4C — they are independent and independently shippable
  (4B/4C can even land first for a fast Codex win while 4A is designed).
- Do **not** optimize the inherent stdio/IPC hop (§4 low-priority in the latency
  report) — not worth it next to A/B.

---

## 8. Suggested sequencing (reviewer may re-order)
1. **4B — Codex background/once-per-turn sync** (small, mirrors an existing proven
   pattern; big felt Codex win; low risk).
2. **4C quick cuts** — skip redundant `init_schema`, reuse identity, trim imports
   (small, safe, helps turn 1).
3. **4A — incremental sync** (the broad win; needs the full plan + review because
   of §5; helps everyone on hosted).
4. **4C warm-keep** — the lifecycle change for near-zero first-token on turns 2+
   (own plan).

---

## 9. Open questions for the design/review pass
- 4A: per-file objects vs content-hash manifest — which fits the existing
  `TarBlobStore`/GCS key scheme with the least new surface, while satisfying §5.1–3?
- 4A: what is the atomic "commit point" a cold reader keys off (a generation
  number? a manifest object written last)? Today it's implicit in the single blob.
- 4B: is per-tool durability actually required for Codex crash-safety, or is
  once-per-turn (like native) sufficient? If per-tool is needed, can it be
  non-blocking + coalesced?
- 4C warm-keep: where does the warm subprocess live (per-thread in the runtime
  registry?), what is the idle-timeout / memory bound, and how does it interact
  with Cloud Run instance recycling (a warmed process dies with its instance —
  acceptable, just re-cold-start)?
- Measurement: confirm the A win the same way F2 was confirmed (a big-workspace
  before/after on `write_file`), so the result is evidence, not assertion.

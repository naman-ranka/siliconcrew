# Follow-ups backlog (deferred, not dropped)

Owner-reviewed findings after the sidebar/Codex-picker/VCD wave (PR #27, merged
into `endgame`). Ordered by how much they matter. Each is TODO — none block the
current staging build. "Happy to take any — say which."

---

## P1 — do next

### 2. The "Thinking" heuristic hides real assistant prose  ⟵ user-facing every day
`frontend/components/chat/MessageList.tsx` — `isThinkingBlock()` treats **any**
text block that is followed by a tool call as "thinking" and collapses it into a
toggle the user probably never opens. So when the agent writes a genuine
explanation ("I'll fix the reset polarity because…") and then calls a tool, that
explanation renders as a collapsed "Thinking" block — silently eaten in *every*
tool-using turn. Real reasoning already arrives as dedicated reasoning blocks, so
the heuristic is both **redundant and lossy**.
- **Fix:** stop treating "text-then-tool-call" as thinking; rely on the real
  reasoning-block stream. Revisit what (if anything) should still collapse.

### 3. No size guard on VCD parsing  ⟵ foot-gun the VCD-open change made easier to hit
`api.py` `_parse_vcd_file` loads the whole VCD into memory via `VCDVCD(path)` and
serializes every signal transition to JSON. Sim-tool VCDs are small, but the new
"open any workspace VCD" feature lets a user open a long-running dump (hundreds of
MB) → stalls a request thread and blows up the response.
- **Fix:** an honest size cap, like the smart file reader already has for text —
  "waveform too large to render — download instead" past a threshold.

---

## Blocked on a live account (owner action)

### 1. Codex model picker is decorative under a connected ChatGPT account  ⟵ invariant-4 honesty
`src/agents/codex/codex_engine.py:381` —
`effective_model = turn.model_name if turn.api_key else None` — deliberately omits
the model under **account** auth (an unknown name silently returns 0 tokens). So
with a ChatGPT account connected, picking a model in the new `CodexModelPicker`
changes nothing; Codex uses its account default. (True before this wave too, but
now that there's a curated `CODEX_CATALOG` of known-good ids, it reads as quietly
dishonest — exactly what invariant 4 guards.)
- **Fix:** under account auth, pass the model **only when the id is in
  `CODEX_CATALOG`**. Needs **one manual test from the owner** with a live ChatGPT
  login to confirm which Codex ids are account-valid (can't be verified without it).

---

## Opportunistic (lower priority)

### 4. `GET /waveforms` only lists root-level VCDs
`api.py:2218` uses a non-recursive `os.listdir`, so the legacy store-driven
waveform dropdown never sees `sim_runs/**` or subdirectory VCDs. Low priority (the
v2 tab model bypasses it), but the endpoint says "list VCD files in the workspace"
and doesn't — a small dishonesty.
- **Fix:** make it recursive (or narrow the docstring).

### 5. Model ids validated only at turn time
Thread PATCH accepts any model string (only alias-normalized); a stale/typo'd id
fails when the user **sends a message**, not when they **pick**. With the catalogs
now serving both pickers, PATCH could validate against them and **422 early**.

### 6. CLAUDE.md's known-failure list has drifted
The documented env-gap set omits `test_linter_tool_multifile` (fails without
iverilog/verilator, which this container lacks). Cheap doc fix so the next agent
doesn't re-derive it via worktree baselines. (Related: this session also found
`test_run_cocotb` + `test_run_sby` fail as env-gap on base `endgame` — worth
folding into the documented baseline too.)

### 7. Small ones
- **Stale tab keys:** tabs persisted from before the VCD change keep old
  `code:foo.vcd` keys, so an old session can show the same file in Monaco **and**
  the waveform viewer side by side. Cosmetic; self-resolves as tabs close.
- **WaveArtifact fallback:** for a cleaned-up run it says "run isn't in the list"
  when it could fall back to opening the VCD by path via the new `wavefile:` key.

---

## Round-2 (surfaced while implementing/verifying batch-1 — mostly resolved; two new small ones)

Batch-1 (branch `claude/followups-batch-1`) resolved #1–#7 above (see the
review-batch1-* and verify-codex-model-live reports). #1 was implemented by
gating on the account's live `model/list` (NOT CODEX_CATALOG — the default
`gpt-5.3-codex` isn't account-valid). #7's literal `wavefile:` fallback proved
infeasible (VCD filename is per-run discovered, not a convention) so the honest
cached-or-empty version shipped instead. Two new small follow-ups remain:

### 8. Codex picker initial label inherits the native model
The CodexModelPicker's INITIAL button label shows the session's native
`model_name` (e.g. "gemini-3.5-flash") until the user picks a Codex model;
selecting one fixes it. Cosmetic residual of X2C-6. Fix: default the Codex
picker's displayed label to the Codex default, not the native model_name.

### 9. No model-attribution line in Codex turn logs
The turn logs prove nonzero tokens but carry no "model=<id>" attribution, so
logs can't distinguish "picked model applied" from "omitted → account default"
(both are correct behavior for #1, but not provable from logs). Fix: one
`[CODEX-TIMING] … model=<effective_model or 'account-default'>` line if we ever
want the applied-model provable post-hoc.

---

## Codex auth security (from the defensive review — reports/codex-auth-review.md)

At-rest storage is MATURE (not a concern): BYOK keys AND the reused ChatGPT
auth.json are both envelope-encrypted (per-secret random DEK, DEK wrapped by a
Cloud-KMS KEK), owner-scoped, nothing plaintext persisted, no secrets in logs.
Browser-side storage was evaluated and rejected (SDK is a server-side subprocess
+ prewarm needs the token before the user acts; browser-per-turn is net worse —
XSS/transit + token still hits the server). The gaps are the working copy +
multi-instance lifecycle:

### 10. Refresh-token rotation race (HIGH) — fix before real concurrency
auth.json is a ROTATING refresh token OpenAI says never to share across
concurrent machines, but we share one durable blob across all instances with
last-writer-wins persist (codex_auth.py:217-232). Two instances serving the SAME
user can rotate-and-clobber → invalidate/lock the user out of their own ChatGPT
account. Same multi-instance theme as X2A-7. Fix: per-uid single-flight/lease
around read-rotate-persist. Low probability with a few distinct test users (needs
same user on two instances at once); becomes real under concurrency.

### 11. Plaintext live auth.json on instance disk (HIGH) — needs instance-disk compromise
The encrypted blob is decrypted to a plaintext working file on the instance for
the SDK to read (codex_auth.py:206, codex_engine.py:566/649), bypassing at-rest
encryption for the LIVE set. Transient; only exposed if an instance disk is
compromised. Fix: stage on tmpfs + wipe after the turn.

### 12. Single KEK wraps every tenant's DEK (MED) — defense-in-depth
One KEK/master compromise = total blast radius, and no rotation path (the "v":1
version field is unused). Fix: KEK rotation; harden the self-host SHA-256(master)
path. Only matters on KEK/master compromise.

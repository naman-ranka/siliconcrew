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

# X2M-2 (PD-tools -32602) + X2M-5 (schematic hosted honesty)

Branch `claude/overnight-showcase`. Baseline backend gate = 9 known failures;
after these changes still exactly 9 (zero new).

---

## ITEM A — X2M-2: the five PD tools' -32602. **Schema hypothesis DISPROVEN. No fix applied (per instruction: don't guess-fix).**

The five tools (`get_synthesis_metrics`, `read_stage_report`, `get_cts_summary`,
`get_congestion_summary`, `get_route_drc_summary`) returned JSON-RPC `-32602` on
hosted for a COMPLETED run, while `get_synthesis_status` /
`search_logs_tool` / `save_metrics_tool` / `generate_report_tool` worked in the
same minute. Tested hypothesis first: their generated MCP inputSchema is
something the SDK/connector validation genuinely rejects.

### Disproof (empirical, no live probing)
Built each tool's `model_json_schema()` locally and validated canonical payloads:

1. **All five schemas are well-formed** (`Draft202012Validator.check_schema`
   passes) and **every canonical payload validates** — `{}` and
   `{"run_id": "synth_0001"}` for the run_id-only tools; `{"stage": "finish"}`
   etc. for `read_stage_report`. Nothing a normal caller sends is schema-rejected.
2. **The killer:** the run_id-only failing tools' schemas are **byte-identical
   (modulo `title`/`description`) to `generate_report_tool`'s**, which WORKED on
   hosted. Concretely both are
   `{"properties":{"run_id":{"default":null,"title":"Run Id","type":"string"}},"type":"object"}`
   with no `required`. `get_synthesis_status` (worked) is likewise identical to
   `compare_pd_runs`'s parent shape.

Identical schema → opposite outcome. A schema-validation cause would treat two
identical schemas the same way. Therefore **the `-32602` is not caused by these
tools' generated schema.** (`run_id: str = None` does emit a slightly loose
`{"type":"string","default":null}`, but it is IDENTICAL across the working and
failing tools, so it cannot explain the split.)

Also confirmed structurally: our `call_tool` catches tool-execution exceptions
and returns them as `TextContent` (a successful RESULT), never `-32602`. So the
`-32602` cannot originate in these tools' server-side execution either — it comes
from the SDK/receive-loop layer, pre- or around dispatch.

### What the evidence DOES support (the real cause — not fixed here)
`-32602` is the F9c framework mis-map (`shared/session.py` blanket-maps any
receive-loop exception to "Invalid request parameters"), fired under the
post-synth backend degradation X2M-1/X2M-3 describe: after the heavy synth the
whole session flapped (`read_spec`/`list_files_tool`/`get_current_session` also
`-32602`; `get_synthesis_status`/`wait_for_synthesis` hung >300s). The "family"
appearance is temporal — the five PD tools were called during/after the
degradation onset — not a property of their signatures. The relevant real fixes
are already in flight and are OUTSIDE a "schema fix":
- **F9c** hosted `stateless=True` (task #10, applied) — stops the
  restart/not-initialized `-32602`.
- **F2** sync gating (FIXED f095fcb) — stops the whole-workspace tar+PUT on
  reads that X2M-1 fingers as the balloon/stall source.
- A plausible remaining sensitivity (UNVERIFIED, flagged for the owner, NOT
  guess-fixed): the PD-summary tools read ORFS report FILES from the workspace,
  so on hosted they may force a full workspace **materialization** from GCS
  (huge post-synth), whereas `get_synthesis_status` reconciles from the run
  store. If confirmed, the fix is a read-path that avoids full materialization
  for single-file reads — an architectural change in the workspace provider /
  session scope (excluded files), worth its own small plan.

### Durable guard added (labeled honestly — it is NOT the X2M-2 fix)
`tests/test_mcp_tool_schemas.py`: every registered MCP tool's schema is
well-formed and accepts a canonical payload (parametrized over `mcp_tools`), plus
an explicit assertion that the failing PD tools' schemas equal
`generate_report_tool`'s. This encodes the disproof durably AND would catch a
FUTURE genuinely-malformed tool schema family-wide — the guard the item asked
for, kept even though the hypothesis it was meant to catch didn't apply here.

---

## ITEM B — X2M-5: schematic_tool honest hosted answer. **FIXED.**

`schematic_tool` needs local Docker (Yosys), absent on Cloud Run, so on hosted it
leaked `failed to connect to the docker API at unix:///var/run/docker.sock…` to
the external app. Added a hosted gate at the top of the wrapper (mirrors the
`run_python_analysis` pattern): when `get_settings().hosted`, return
> "Schematic generation isn't available on the hosted platform yet — it needs a
> local Yosys/Docker toolchain. Run SiliconCrew self-host for schematics."

No stack trace, no docker-socket string. Self-host is unchanged (the gate is
hosted-only). `tests/test_schematic_hosted_gate.py`: hosted returns the honest
message with no `docker.sock`/`traceback` leak; self-host does not short-circuit
(a missing file still reaches the normal "does not exist" path, proving the gate
is hosted-only without needing docker).

**Deferred (owner decision):** hosted schematic SUPPORT — a non-docker Yosys
backend or an isolated-job path (like ORFS/XLS/SBY have) — is a feature decision,
not covered here. This item only makes the CURRENT hosted behavior honest.

---

## Gates
- New: `test_mcp_tool_schemas.py` (39 parametrized + 1 structural) + 
  `test_schematic_hosted_gate.py` (2) → 41 pass (with jsonschema present;
  importorskip otherwise).
- Full backend gate: **9 failed, 755 passed, 9 skipped** — exact known baseline,
  zero new. `git checkout -- tests/fixtures/ test_sby_output.txt` after.

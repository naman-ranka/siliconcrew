# Multi-Runtime SDK Requirements Plan (High-Level)

## Goal
Support multiple agent runtimes in one app:
- `langgraph` (keep as stable baseline)
- `openai_sdk`
- `anthropic_sdk`

without breaking current MCP tools, session history, or usage visibility.

## Why We Are Doing This
- Reduce lock-in to one orchestration stack.
- Get vendor-native improvements (tool use, streaming, reliability) faster.
- Let users choose runtime/model per session based on cost, speed, or quality.
- Keep our tool layer stable while modernizing orchestration.

## What We Need (Requirements)
1. Runtime abstraction layer
- Define one internal turn contract: input messages -> model/tool loop -> output messages.
- Implement each runtime as an adapter behind this contract.

2. Common message + tool schema
- Normalize roles/messages/tool calls/tool results into one internal format.
- Keep provider-specific formats only inside adapters.

3. Session-level routing
- Persist `runtime`, `provider`, `model` in session metadata.
- Route each turn to the selected adapter.
- Default to `langgraph` unless explicitly changed.

4. Observability parity
- Keep consistent metrics across runtimes: tokens, latency, tool calls, failures.
- Preserve existing transcript and reporting behavior in frontend.

5. Guardrail parity
- Apply the same limits/policies regardless of runtime (timeouts, retries, step limits, tool policy).
- No adapter should bypass safety checks.

6. Safe rollout controls
- Feature flags per runtime.
- Automatic fallback to `langgraph` on adapter failure.
- Simple rollback path at config level.

## High-Level Plan (Flexible, Not Rigid)
1. Foundation
- Add adapter interface and registry.
- Move current LangGraph flow behind the interface first.

2. First SDK integration
- Integrate one SDK runtime end-to-end (recommend: OpenAI first or Anthropic first based on team priority).
- Implement tool loop, streaming, and usage capture.

3. Second SDK integration
- Add second provider adapter with the same contract and telemetry fields.

4. Frontend/session wiring
- Add runtime/provider/model selector in session config (or config-only initially).
- Surface runtime metadata in traces.

5. Validation
- Run side-by-side evals on representative design tasks.
- Compare completion rate, tool reliability, latency, and token cost vs LangGraph baseline.

6. Gradual rollout
- Internal usage first, then limited exposure, then broader default options.
- Keep quick fallback to LangGraph through all phases.

## Non-Goals (Initial Scope)
- Rewriting MCP tools.
- Removing LangGraph immediately.
- Perfect feature parity on day 1.

## Complexity (Practical Estimate)
- Moderate to high, mostly integration complexity.
- Main risk is behavior/telemetry drift across runtimes, not tool logic itself.
- Lowest-risk approach is incremental adapters + strict normalization + staged rollout.

# Build brief — model selector (per chat thread)

Work on `claude/integration-p1p2`. **Do this AFTER chat threads**
(`plans/phase1/CHAT_THREADS_BRIEF.md`) — the model is stored **on the thread**.

## Goal
A standard, polished model picker in the workbench chat rail. Each chat thread
can use a different model; new threads inherit the last-used. The backend bones
exist — `src/model_catalog.py` (registry + `normalize_model_name` + pricing) and
`src/llm/factory.py` (provider inferred from the model id) — and the WS handler
already does `normalize_model_name(model_name) → create_architect_agent(model_name=…)`.
So this is a polished picker + a thin "available models" endpoint + storing the
choice on the thread. No agent/tool changes.

## Backend
- `GET /api/models` → list for the UI: per model
  `{id, label, provider, tier ("fast"|"balanced"|"capable"), pricing?, available}`.
  Derive from `model_catalog`. Set `available` from which provider keys are usable
  for THIS request — env keys in self-host; BYOK/hosted via the Phase 2
  `LlmKeyProvider`/auth in hosted mode — so we never offer a model that will 500.
  Owner-checked + tenant-scoped like the other endpoints.
- Store `model` **on the chat thread** (add the column to `chat_threads` from the
  threads brief; default = the session's last-used or `DEFAULT_MODEL`). Set it via
  the thread PATCH endpoint (or a small `PUT .../threads/{tid}/model`).
- The WS handler reads the **active thread's** model (not the session's) and feeds
  it to `normalize_model_name → create_architect_agent`. New threads inherit the
  creator's last-used model.

## Frontend (chat rail)
- A compact model button at the **bottom-left of the composer** showing the
  current model + a provider glyph. Click → a popover **grouped by provider**
  (Anthropic / OpenAI / Google); each row = display name + a one-line
  capability/speed hint (+ cost if known) + a checkmark on the current model.
- **Unavailable models greyed with "needs key."**
- Selecting updates the **active thread's** model and the next message uses it;
  persists across reload (read back from the thread).
- Optional, behind an "Advanced" gear (off by default): temperature /
  reasoning-effort. Do not clutter the main bar.
- Honor `plans/phase0/ui-design-language.md` (warm palette; status colors separate
  from the orange brand) and a11y (focus-visible, aria, keyboard-selectable rows,
  Escape / click-outside to close).

## Guardrails
- No changes to the action API, auth/tenancy, or the one write path.
- Same chat rail as the threads work — since you build it right after threads on
  the same branch, integrate cleanly (the picker sits next to the thread switcher).
- Keep all tests green.

## Verify
- Unit: `GET /api/models` reflects configured providers (the `available` flag
  flips with keys); setting a model on a thread persists and the WS uses it; a
  second thread can hold a different model.
- Playwright (live): open the picker, switch model, send a message with the new
  model, reload → it stuck; a different thread keeps its own model. Screenshot the
  grouped popover (capability hints, unavailable greyed) under
  `plans/phase1/screenshots/model-picker/`.

## Deliver
Commit per slice, push to `claude/integration-p1p2`; summarize the endpoint shape,
that the model lives on the thread, and the picker behavior.

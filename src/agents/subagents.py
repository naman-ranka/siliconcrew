"""Subagents — two built-in roles, one delegating mechanism, no spawner.

What this is
------------
Some work is naturally fan-out: five sweep points, four testbenches. Done in
one conversation it is a serial slog that spends the turn's step budget on
bookkeeping and fills the context with five nearly identical transcripts. Done
here, each point is a CHILD: its own short conversation, its own tool set, its
own answer, and only the answer comes back.

What this is NOT: a general agent spawner. There are exactly two roles, they
are declared in ``config/tool_sets.yaml``, and a child cannot delegate again
(``DEPTH_LIMIT = 1``). A tree of agents is a debugging surface nobody in this
repo has asked for; two flat fan-outs are the work that actually exists.

Roles are SKILLS, not a new file format
---------------------------------------
Four harnesses encode subagents four incompatible ways (``.claude/agents/*.md``,
``.codex/agents/*.toml``, opencode's md-or-JSON, deepagents' dict). There is no
standard to adopt, so we adopt none: a role is a tool set plus the bodies of
skills that already ship in ``skills/``. The procedure a child follows is the
same text the parent would read for the same job, which is the only way the two
cannot drift.

Native agent only, and stated plainly
-------------------------------------
A subagent needs a LOOP — a model that calls tools until it is done. An MCP
client is not a loop; it is a tool caller on the other side of a wire, and its
model is not ours to drive. So these tools exist ONLY on the in-process
architect (they are built by ``create_architect_agent`` and never enter
``ALL_TOOLS``). MCP clients do not get subagents. That is not an oversight and
it is not a roadmap item.

Why they are not registry tools: every registry tool has one stable identity
that MCP and the Command Surface can advertise ahead of time. The delegation
tool cannot — it closes over the request-scoped LLM key and the pinned model
resolved for THIS turn, which is exactly how a child is prevented from spending
outside the parent's accounting (see ``_charge`` and ``subagent_tools``).

Spend
-----
A child spends the user's money. It therefore:

* never resolves a key and never picks a model — both are passed in from the
  parent's already-resolved ``LlmKey`` (BYOK → env → capped hosted) and its
  already-applied hosted model pin, through the same ``create_llm`` call;
* has a hard step ceiling of its own (``subagent_recursion_limit``);
* is charged to the same session token/cost row the parent's turn is charged
  to, before the parent's turn closes;
* is OFF on hosted. The hosted free-tier limiter is an in-process object owned
  by ``api.py``'s request path, and a child does not run in that path. Rather
  than account for hosted spend approximately, hosted has no children until the
  limiter is passed in. One sentence, one setting, no fiction.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.api.tool_catalog import (
    ToolSetError,
    subagent_roles,
    tool_names_in_set,
    tools_in_set,
)
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.utils.session_context import SessionContext, get_current_session, session_scope

#: A child may not delegate. The structural guarantee is that a child's tool
#: set comes from ``config/tool_sets.yaml`` and the delegation tool is not in
#: any registry, so it cannot appear there. This context variable is the belt
#: to that pair of braces: it is set inside every child, and checked before any
#: child is built.
DEPTH_LIMIT = 1
_depth: ContextVar[int] = ContextVar("siliconcrew_subagent_depth", default=0)

#: Source prefix written to ``attempt_events.jsonl`` for a child's tool calls.
#: ``src/api/activity.py`` splits this back into a ``subagent`` actor plus the
#: role, so the activity dock can tell a child's work from its parent's.
SUBAGENT_SOURCE_PREFIX = "subagent"


class SubagentActivityMiddleware(AgentMiddleware):
    """The ONE choke point: every child tool call lands in the parent's log.

    Invariant 3 says every actor's tool calls land in ``attempt_events.jsonl``.
    A child is an actor. Doing that per call site would mean trusting whoever
    adds the next role to remember; doing it in ``wrap_tool_call`` means the
    invariant holds by construction — a tool the child calls is a tool this
    hook wrapped, because that is what the hook IS.

    ``wrap_tool_call`` is wrap-style, so it costs no graph step (a node-style
    hook would cost one per model call and quietly shrink the child's budget).
    Both the sync and async forms are implemented: LangChain raises
    NotImplementedError on whichever one you did not define, and children are
    driven synchronously from a tool that is itself called from both an async
    (``api.py``) and a sync (``reporter.py``) parent.

    Tool-call ids are prefixed with the role and the child's index. Two children
    running the same tool at the same second would otherwise write two events
    whose ids came from two different models with no coordination, and the
    activity feed pairs calls to results BY ID.
    """

    def __init__(self, role: str, child_index: int, ctx: SessionContext):
        super().__init__()
        self.role = role
        self.child_index = child_index
        self.ctx = ctx

    def _begin(self, request) -> tuple:
        call = request.tool_call or {}
        name = call.get("name") or "unknown"
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        cid = f"{self.role}#{self.child_index}:{call.get('id') or name}"
        log_tool_call(
            workspace=self.ctx.workspace,
            session_id=self.ctx.session_id,
            source=f"{SUBAGENT_SOURCE_PREFIX}:{self.role}",
            tool=name,
            arguments=args,
            tool_call_id=cid,
        )
        return name, args, cid

    def _finish(self, name, args, cid, result=None, error=None) -> None:
        text = getattr(result, "content", None)
        status = "error" if error is not None else getattr(result, "status", "success")
        log_tool_result(
            workspace=self.ctx.workspace,
            session_id=self.ctx.session_id,
            source=f"{SUBAGENT_SOURCE_PREFIX}:{self.role}",
            tool=name,
            result=str(text) if text is not None else None,
            status="error" if status == "error" else "success",
            error=str(error) if error is not None else None,
            tool_call_id=cid,
            arguments=args,
        )

    def wrap_tool_call(self, request, handler):
        name, args, cid = self._begin(request)
        try:
            result = handler(request)
        except Exception as exc:
            self._finish(name, args, cid, error=exc)
            raise
        self._finish(name, args, cid, result=result)
        return result

    async def awrap_tool_call(self, request, handler):
        name, args, cid = self._begin(request)
        try:
            result = await handler(request)
        except Exception as exc:
            self._finish(name, args, cid, error=exc)
            raise
        self._finish(name, args, cid, result=result)
        return result


def _skill_bodies(names: List[str]) -> str:
    """The role's procedure, straight out of the shipped skill store."""
    from src.utils.skills import skills_by_name

    store = skills_by_name()
    parts = []
    for name in names:
        skill = store.get(name)
        if skill is None:
            raise ToolSetError(
                f"subagent role names skill {name!r}, which the store does not have. "
                f"Available: {', '.join(sorted(store)) or 'none'}"
            )
        parts.append(f"## {skill.name}\n\n{skill.body}")
    return "\n\n".join(parts)


def child_prompt(role: str, spec: Dict[str, Any], task: str) -> str:
    """The child's whole system prompt: who it is, the procedure, the contract.

    A child has no chat history, so there is nothing for progressive disclosure
    to disclose: the skill bodies are pasted in full.
    """
    return (
        f"You are a SiliconCrew {role} subagent, working inside a design session "
        "someone else opened. You have one job and no conversation: do the task "
        "below with the tools you have, then answer once.\n\n"
        "You cannot delegate, and you cannot ask a question — there is nobody "
        "to answer it. If the task cannot be done, say so and say why.\n\n"
        f"# Procedure\n\n{_skill_bodies(list(spec.get('skills') or []))}\n\n"
        f"# Your answer\n\n{(spec.get('output') or '').strip()}\n\n"
        f"# Your task\n\n{task}"
    )


def _trailing_json(text: str) -> Optional[dict]:
    """The JSON object a child was asked to end with, or None.

    None is a real answer: it means the child did not honour the contract, and
    the caller reports its prose instead. Inventing a number to fill the shape
    would be the one thing worse than an unstructured result.
    """
    end = (text or "").rstrip().rfind("}")
    if end == -1:
        return None
    # Earliest opening brace first, so a nested object parses as the whole
    # answer rather than as its own last field.
    for start in (m.start() for m in re.finditer(r"\{", text[:end])):
        try:
            value = json.loads(text[start:end + 1])
        except ValueError:
            continue
        return value if isinstance(value, dict) else None
    return None


def _usage(messages) -> tuple:
    """(input, output) tokens actually reported by the provider for a child."""
    tokens_in = tokens_out = 0
    for msg in messages or []:
        usage = getattr(msg, "usage_metadata", None)
        if isinstance(usage, dict):
            tokens_in += int(usage.get("input_tokens") or 0)
            tokens_out += int(usage.get("output_tokens") or 0)
    return tokens_in, tokens_out


def _charge(ctx: SessionContext, model_name: str, tokens_in: int, tokens_out: int) -> None:
    """Add a fan-out's tokens to the session row the parent's turn also writes.

    Same row, same units, same price table (``src.model_catalog.PRICING``) —
    the child's spend is not a separate ledger, it is more of the user's one
    ledger. This runs before the delegation tool returns, so the parent's
    end-of-turn read-modify-write sees it and adds its own tokens on top.

    Best effort by design: a bookkeeping failure must not lose completed work.
    """
    if tokens_in <= 0 and tokens_out <= 0:
        return
    try:
        from src.model_catalog import DEFAULT_MODEL, PRICING, normalize_model_name
        from src.utils.session_manager import SessionManager

        base_dir = os.environ.get("RTL_WORKSPACE") or os.path.dirname(ctx.workspace)
        data_dir = os.environ.get("RTL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".siliconcrew")
        manager = SessionManager(base_dir=base_dir, db_path=os.path.join(data_dir, "state.db"))
        meta = manager.get_session_metadata(ctx.session_id, user_id=ctx.user_id)
        if not meta:
            return
        new_in = meta.get("input_tokens", 0) + tokens_in
        new_out = meta.get("output_tokens", 0) + tokens_out
        rates = PRICING.get(normalize_model_name(model_name), PRICING[DEFAULT_MODEL])
        cost = (new_in / 1_000_000 * rates["input"]) + (new_out / 1_000_000 * rates["output"])
        manager.update_session_stats(
            ctx.session_id, new_in, new_out, meta.get("cached_tokens", 0), cost,
            user_id=ctx.user_id,
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping never eats the result
        print(f"[WARN] subagent token bookkeeping failed: {exc}")


def _run_one(role, spec, task, index, ctx, model_name, api_key, read_only) -> Dict[str, Any]:
    """One child, start to finish, inside the parent's session scope."""
    from src.agents.architect import ReasoningStripMiddleware
    from src.llm import create_llm
    from src.platform_engines.settings import get_settings

    with session_scope(ctx):
        token = _depth.set(_depth.get() + 1)
        try:
            graph = create_agent(
                model=create_llm(model_name=model_name, temperature=0.0, api_key=api_key),
                tools=tools_in_set(spec["tool_set"], read_only=read_only),
                system_prompt=child_prompt(role, spec, task),
                middleware=[
                    ReasoningStripMiddleware(),
                    SubagentActivityMiddleware(role, index, ctx),
                ],
            )
            state = graph.invoke(
                {"messages": [("user", task)]},
                {"recursion_limit": get_settings().subagent_recursion_limit},
            )
        finally:
            _depth.reset(token)

    messages = state.get("messages") or []
    text = str(getattr(messages[-1], "content", "") if messages else "")
    tokens_in, tokens_out = _usage(messages)
    return {
        "task": task,
        "result": _trailing_json(text),
        "report": text[-2000:],
        "tokens": {"input": tokens_in, "output": tokens_out},
    }


def run_role(role: str, tasks: List[str], *, model_name: str, api_key, read_only: bool = False) -> Dict[str, Any]:
    """Fan ``tasks`` out to one child each and return their answers.

    Refuses — loudly, before spending anything — when there is no session to
    act in, when a child tried to delegate, or when the deployment is hosted.
    """
    from src.platform_engines.settings import get_settings

    settings = get_settings()
    roles = subagent_roles()
    if role not in roles:
        raise ToolSetError(f"no subagent role named {role!r}; available: {sorted(roles)}")
    if _depth.get() >= DEPTH_LIMIT:
        raise ToolSetError("a subagent may not delegate (depth limit 1)")
    ctx = get_current_session()
    if ctx is None or not ctx.workspace:
        raise ToolSetError("subagents run inside a session; none is bound to this call")
    if settings.hosted:
        raise ToolSetError(
            "subagents are off on the hosted deployment: a child's tokens are not "
            "visible to the hosted free-tier spend limiter."
        )
    tasks = [t for t in (tasks or []) if str(t).strip()]
    if not tasks:
        raise ToolSetError("give at least one task; one child runs per task")
    tasks = tasks[: settings.subagent_max_children]

    spec = roles[role]
    with ThreadPoolExecutor(max_workers=min(len(tasks), settings.subagent_max_children)) as pool:
        futures = [
            pool.submit(_run_one, role, spec, task, i, ctx, model_name, api_key, read_only)
            for i, task in enumerate(tasks)
        ]
        results = []
        for i, future in enumerate(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # one child failing is data, not a turn failure
                results.append({"task": tasks[i], "result": None, "error": str(exc)[:500],
                                "tokens": {"input": 0, "output": 0}})

    tokens_in = sum(r["tokens"]["input"] for r in results)
    tokens_out = sum(r["tokens"]["output"] for r in results)
    _charge(ctx, model_name, tokens_in, tokens_out)
    return {"role": role, "children": results,
            "tokens": {"input": tokens_in, "output": tokens_out}}


class RunSubagentsArgs(BaseModel):
    role: str = Field(description="Which built-in role to run. See the tool description.")
    tasks: List[str] = Field(
        description="One task per child, each a complete instruction on its own — "
                    "a child sees only this text, never the conversation."
    )


def subagent_tools(*, model_name: str, api_key, read_only: bool = False) -> List[Any]:
    """The delegation tool, bound to THIS turn's model and key. Native agent only.

    Returns an empty list when the roles cannot be offered — hosted, or the
    feature switched off — so the caller adds nothing rather than advertising a
    tool that refuses.
    """
    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if settings.hosted or not settings.subagents_enabled:
        return []
    roles = subagent_roles()
    if read_only:
        # Derived, not decided here: a role survives read-only mode only if its
        # own tool set needs nothing that mutates. Both roles shipped today are
        # doing (dispatch a run, write a testbench), so read-only offers none —
        # but a future reading role would come through untouched, because the
        # rule asks the data rather than naming a role.
        roles = {
            name: spec for name, spec in roles.items()
            if tool_names_in_set(spec["tool_set"]) == tool_names_in_set(spec["tool_set"], read_only=True)
        }
    if not roles:
        return []

    menu = "\n".join(f"- {name}: {(spec.get('description') or '').strip()}"
                     for name, spec in roles.items())

    def _run(role: str, tasks: List[str]) -> str:
        try:
            return json.dumps(run_role(role, tasks, model_name=model_name,
                                       api_key=api_key, read_only=read_only), indent=2)
        except ToolSetError as exc:
            return f"❌ {exc}"

    return [StructuredTool.from_function(
        func=_run,
        name="run_subagents",
        description=(
            "Run one short-lived child agent per task, in parallel, and get their "
            "answers back. Use it for fan-out work where the tasks are independent "
            "and only the results matter — one sweep point per child, one testbench "
            "per child. Each child starts fresh: it sees your task text and nothing "
            "else, so write each task to stand alone. Children cannot delegate.\n"
            f"Roles:\n{menu}"
        ),
        args_schema=RunSubagentsArgs,
    )]


def subagent_tool_names() -> tuple:
    """The names this module can add to an agent. Derived, so the rename guard
    in tests/test_tool_name_drift.py stays complete without a typed list."""
    return ("run_subagents",)

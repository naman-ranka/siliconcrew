"""The tool platform's single source of truth — catalog, policy, execution.

Fundamental design: the LangChain ``@tool`` wrappers in ``src/tools/wrappers.py``
already carry machine-readable schemas (``args_schema``) and docstrings — the
exact metadata the MCP server serves to external clients. This module
introspects that SAME registry so the web UI's Command Surface, the agent, and
MCP clients all speak one contract with zero drift:

  * ``build_catalog()``     — every UI-invocable tool: name, description,
                              category, JSON Schema for args, policy flags.
  * ``validate_and_execute``— schema-validate arguments with the tool's own
                              pydantic model, then run the SAME wrapper
                              function the agent runs, inside the caller's
                              session scope. Two rules apply on THIS surface
                              only: file arguments stay in the workspace, and a
                              blocking wait is clamped to zero (invariant 6).

Policy (what is NOT derivable from schemas) is declared ON each tool, once, at
its definition site (``@policy(...)`` in ``src/tools/wrappers.py``). This module
DERIVES the views everything else reads — ``TOOL_CATEGORIES``,
``PROTECTED_TOOLS``, ``ASYNC_TOOLS``, ``MUTATING_TOOLS``, ``EXCLUDED_FROM_UI``,
``DISABLED_WHEN_BOUND`` — from those declarations. ``mcp_server`` imports the category/protected policy
FROM here, so there is one policy, not two, and adding a tool means editing one
file.

No heavy imports at module load — ``wrappers`` (LangChain) is imported lazily
inside functions so the action router stays importable/testable without the
agent stack.
"""
from __future__ import annotations

import os
from types import MappingProxyType
from typing import Any, Dict, List, Optional

from src.utils.paths import is_within

# --- Policy (DERIVED from the tools — never hand-maintained here) -------------
#
# Policy is declared at each tool's definition site (``@policy(...)`` in
# src/tools/wrappers.py). Everything below is a VIEW of those declarations,
# computed once per process. The historical names (TOOL_CATEGORIES,
# PROTECTED_TOOLS, ASYNC_TOOLS, MUTATING_TOOLS, EXCLUDED_FROM_UI) still exist
# and still mean the same thing, so every existing consumer keeps working — but
# they are now derived values, and every one of them is immutable: editing this
# file to change a tool's policy is no longer possible, which is the point.
#
# They are exposed through a module-level ``__getattr__`` (PEP 562) so importing
# this module stays free of the LangChain tool stack; the registry is imported
# on FIRST ACCESS to a derived name, exactly like ``build_catalog()``.

# Presentation order for the Command Surface's groups (the frontend renders
# catalog categories in first-seen order). Pure presentation — not policy, and
# not a tool list. A category missing here is caught by tests/test_tool_policy.py
# rather than silently sorting last.
CATEGORY_ORDER = (
    "essential", "manifest", "verification", "synthesis",
    "editing", "reporting", "analysis", "hls",
    # MCP-only: the session tools never reach the Command Surface (the web UI
    # has its own session management), so this group is always empty there.
    "session",
    # Agent + MCP: reading the skill store is the agent's own business, and the
    # web UI has no skills surface yet, so this group is empty there too.
    "skills",
)

_DERIVED_NAMES = frozenset({
    "TOOL_CATEGORIES", "PROTECTED_TOOLS", "ASYNC_TOOLS", "MUTATING_TOOLS",
    "EXCLUDED_FROM_UI", "DISABLED_WHEN_BOUND",
})


class UnknownToolError(KeyError):
    """Asked for the policy of a name no registered tool answers to.

    Deliberately loud. The previous behaviour returned permissive defaults for
    any unknown name (no sign-in required, does not mutate), which would have
    made a mis-typed or unregistered tool an unauthenticated write whose
    changes are never synced to object storage.
    """


_policies: Optional[Dict[str, Any]] = None
_derived: Optional[Dict[str, Any]] = None


def _load_policies() -> Dict[str, Any]:
    """{tool name: ToolPolicy} for every registered tool, from the registry.

    Lazy import (LangChain): callers surface an ImportError honestly rather
    than this module dragging the agent stack into the action router.
    """
    global _policies
    if _policies is None:
        from src.tools.wrappers import ALL_TOOLS, tool_policy

        _policies = {t.name: tool_policy(t) for t in ALL_TOOLS}
    return _policies


def policy_for(name: str):
    """The declared :class:`ToolPolicy` for ``name``. Raises for anything else."""
    try:
        return _load_policies()[name]
    except KeyError:
        raise UnknownToolError(name) from None


def _derive() -> Dict[str, Any]:
    global _derived
    if _derived is None:
        policies = _load_policies()
        by_category: Dict[str, List[str]] = {}
        for name, p in policies.items():
            by_category.setdefault(p.category, []).append(name)
        order = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
        categories = {
            cat: tuple(by_category[cat])
            for cat in sorted(by_category, key=lambda c: (order.get(c, len(order)), c))
        }
        _derived = {
            "TOOL_CATEGORIES": MappingProxyType(categories),
            "PROTECTED_TOOLS": frozenset(n for n, p in policies.items() if p.protected),
            "ASYNC_TOOLS": frozenset(n for n, p in policies.items() if p.async_job),
            "MUTATING_TOOLS": frozenset(n for n, p in policies.items() if p.mutates),
            "EXCLUDED_FROM_UI": frozenset(n for n, p in policies.items() if "ui" not in p.surfaces),
            "DISABLED_WHEN_BOUND": frozenset(
                n for n, p in policies.items() if p.disabled_when_bound
            ),
        }
    return _derived


def __getattr__(name: str) -> Any:
    """PEP 562: the derived policy views, computed on first access."""
    if name in _DERIVED_NAMES:
        return _derive()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def reset_caches() -> None:
    """Drop every cached view of the registry (tests that alter it)."""
    global _policies, _derived, _catalog_cache, _tools_by_name
    _policies = _derived = _catalog_cache = _tools_by_name = None


def category_of(tool_name: str) -> str:
    return policy_for(tool_name).category


def requires_session(tool_name: str) -> bool:
    """Whether the tool needs an active session/workspace to run.

    This is what the MCP server's session gate reads before every call. It is
    False for the session tools themselves — a stranger has to be able to call
    create_session_tool with no session yet — and True for everything else,
    which is why that gate can be blanket without naming a single tool.
    """
    return policy_for(tool_name).requires_session


def tools_with_attempt_parser(parser) -> frozenset:
    """Every tool whose results ``parser`` reads (declared in its ``@policy``).

    Lets a consumer ask "which tool produces a lint verdict?" instead of
    hardcoding ``"linter_tool"`` — the same question the attempt log asks.
    """
    return frozenset(
        n for n, p in _load_policies().items() if p.attempt_parser is parser
    )


# --- Catalog (introspected once per process) ----------------------------------

_catalog_cache: Optional[List[Dict[str, Any]]] = None
_tools_by_name: Optional[Dict[str, Any]] = None


def _load_tools() -> Dict[str, Any]:
    """The UI-invocable tools, keyed by name. Lazy-imports the agent tool
    registry (LangChain); raises ImportError when the agent stack isn't
    installed — callers surface that honestly. Membership is the tools' own
    ``surfaces`` declaration, not a list kept here."""
    global _tools_by_name
    if _tools_by_name is None:
        from src.tools.wrappers import tools_on_surface

        _tools_by_name = {t.name: t for t in tools_on_surface("ui")}
    return _tools_by_name


def _clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Strip pydantic title noise; keep types/enums/defaults/required intact."""
    schema = dict(schema)
    schema.pop("title", None)
    props = schema.get("properties")
    if isinstance(props, dict):
        cleaned = {}
        for key, prop in props.items():
            if isinstance(prop, dict):
                prop = {k: v for k, v in prop.items() if k != "title"}
            cleaned[key] = prop
        schema["properties"] = cleaned
    return schema


def build_catalog() -> List[Dict[str, Any]]:
    """One entry per UI-invocable tool, straight from the live registry."""
    global _catalog_cache
    if _catalog_cache is None:
        entries: List[Dict[str, Any]] = []
        for name, t in _load_tools().items():
            if t.args_schema is not None:
                schema = _clean_schema(t.args_schema.model_json_schema())
            else:
                schema = {"type": "object", "properties": {}}
            p = policy_for(name)
            entries.append({
                "name": name,
                "description": (t.description or "").strip(),
                "category": p.category,
                "argsSchema": schema,
                "requiresSignIn": p.protected,
                "async": p.async_job,
                "mutates": p.mutates,
            })
        # Stable order: catalog category order, then registry order within.
        cat_rank = {cat: i for i, cat in enumerate(_derive()["TOOL_CATEGORIES"])}
        entries.sort(key=lambda e: cat_rank.get(e["category"], 99))
        _catalog_cache = entries
    return _catalog_cache


def tool_flags(name: str) -> Dict[str, bool]:
    """The gate flags for one REGISTERED tool. Raises UnknownToolError
    otherwise — an unknown name must never resolve to permissive defaults."""
    p = policy_for(name)
    return {
        "requiresSignIn": p.protected,
        "mutates": p.mutates,
        "async": p.async_job,
    }


def is_invocable(name: str) -> bool:
    try:
        return name in _load_tools()
    except ImportError:
        return False


# --- Validation + execution ----------------------------------------------------

class ToolArgumentError(Exception):
    """Argument rejected before execution (validation or containment)."""

    def __init__(self, message: str, details: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.details = details or []


# Defense in depth: wrapper functions resolve file-name arguments relative to
# the session workspace, but not all of them re-check containment (the write
# path does via file_ops; some read paths don't). Any argument that names a
# file must stay inside the workspace, whatever the tool does with it.
# Suffixes first, then exact names. ``_path`` is here because an argument that
# says "path" is exactly as dangerous as one that says "file" — the spec adopter
# took ``yaml_path`` and matched nothing, so it was the one file argument this
# rule never saw.
_FILE_ARG_SUFFIXES = ("_file", "_files", "_path")
_FILE_ARG_NAMES = ("filename", "file_path")


def _looks_like_file_arg(key: str) -> bool:
    return key.endswith(_FILE_ARG_SUFFIXES) or key in _FILE_ARG_NAMES


def enforce_file_containment(workspace: str, arguments: Dict[str, Any]) -> None:
    for key, value in (arguments or {}).items():
        if not _looks_like_file_arg(key):
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if not isinstance(v, str) or not v:
                continue
            if not is_within(workspace, os.path.join(workspace, v)):
                raise ToolArgumentError(f"Path escapes the workspace: {v}")


# Invariant 6: the UI is a viewer, not an actor. A tool may offer to BLOCK for
# an agent's turn economy (get_synthesis_status' wait_sec is the only one), but
# this path serves a browser: a request that sits on a worker for two minutes is
# the UI acting, and the answer it would get is the answer it already has. Same
# shape as the containment rule above — an argument-name rule applied on this
# surface only, not a list of tool names kept here.
_BLOCKING_ARG_KEYS = ("wait_sec",)


def clamp_blocking_waits(arguments: Dict[str, Any]) -> None:
    for key in _BLOCKING_ARG_KEYS:
        if key in (arguments or {}):
            arguments[key] = 0


def validate_and_execute(name: str, workspace: str, arguments: Optional[Dict[str, Any]]) -> Any:
    """Validate ``arguments`` against the tool's own schema, then run the SAME
    function the agent runs. Must be called inside a bound session scope
    (``run_scoped``) so ``get_workspace_path()`` resolves the right workspace.

    Raises KeyError (unknown tool), ToolArgumentError (bad args), or whatever
    the tool itself raises.
    """
    tool = _load_tools()[name]
    args = dict(arguments or {})
    enforce_file_containment(workspace, args)
    clamp_blocking_waits(args)

    if tool.args_schema is not None:
        try:
            model = tool.args_schema(**args)
        except Exception as exc:  # pydantic.ValidationError, kept import-light
            details = getattr(exc, "errors", lambda: [])()
            compact = [
                {"field": ".".join(str(p) for p in e.get("loc", [])), "message": e.get("msg", "")}
                for e in (details if isinstance(details, list) else [])
            ][:20]
            raise ToolArgumentError(str(exc).splitlines()[0], compact) from exc
        kwargs = model.model_dump()
    else:
        kwargs = {}

    fn = getattr(tool, "func", None)
    if fn is None:
        raise ToolArgumentError(f"Tool '{name}' has no synchronous entrypoint.")
    return fn(**kwargs)

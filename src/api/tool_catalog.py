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
                              session scope.

Policy (what is NOT derivable from schemas) lives here as small explicit sets:
categories, sign-in gating, async-ness, workspace mutation. ``mcp_server``
imports the category/protected policy FROM here, so there is one policy, not
two.

No heavy imports at module load — ``wrappers`` (LangChain) is imported lazily
inside functions so the action router stays importable/testable without the
agent stack.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.utils.paths import is_within

# --- Policy (explicit, reviewed — everything else is introspected) -----------

TOOL_CATEGORIES: Dict[str, List[str]] = {
    "essential": [
        "write_spec", "read_spec", "write_file", "read_file",
        "linter_tool", "simulation_tool", "run_isolated_simulation",
        "list_files_tool",
    ],
    "manifest": [
        "get_manifest", "update_manifest",
    ],
    "verification": [
        "waveform_tool", "cocotb_tool", "sby_tool",
    ],
    "synthesis": [
        "start_synthesis", "retry_pd", "get_synthesis_job", "wait_for_synthesis",
        "get_synthesis_metrics", "read_stage_report", "get_route_drc_summary",
        "get_cts_summary", "get_congestion_summary", "compare_pd_runs",
        "get_stage_status", "search_logs_tool", "schematic_tool",
    ],
    "editing": [
        "apply_patch_tool", "edit_file_tool", "load_yaml_spec_file",
    ],
    "reporting": [
        "save_metrics_tool", "generate_report_tool",
    ],
    "hls": [
        "run_xls_flow", "run_dslx_interpreter", "compile_dslx_to_ir",
        "optimize_xls_ir", "codegen_xls", "benchmark_xls",
        "experimental_compile_cpp_to_ir",
    ],
}

_CATEGORY_BY_TOOL: Dict[str, str] = {
    name: cat for cat, names in TOOL_CATEGORIES.items() for name in names
}

# Mutate/persist or compute-heavy → signed-in user required (same policy the
# MCP server enforces for external clients; imported by mcp_server).
PROTECTED_TOOLS = frozenset(TOOL_CATEGORIES["synthesis"]) | {
    "write_spec", "write_file", "apply_patch_tool", "edit_file_tool",
    "load_yaml_spec_file", "update_manifest",
    "save_metrics_tool", "generate_report_tool",
    "cocotb_tool", "sby_tool",
    *TOOL_CATEGORIES["hls"],
}

# Dispatch-then-poll jobs (the UI renders them as async, never blocks on them).
ASYNC_TOOLS = frozenset({"start_synthesis", "retry_pd"})

# Tools whose execution writes into the workspace → hosted mode must sync the
# workspace back to object storage after the call.
MUTATING_TOOLS = frozenset({
    "write_spec", "write_file", "apply_patch_tool", "edit_file_tool",
    "load_yaml_spec_file", "update_manifest",
    "simulation_tool", "run_isolated_simulation", "cocotb_tool", "sby_tool",
    "start_synthesis", "retry_pd",
    "save_metrics_tool", "generate_report_tool", "schematic_tool",
    *TOOL_CATEGORIES["hls"],
})

# In the registry but not surfaced/invocable from the UI:
#   wait_for_synthesis — a blocking poll loop built for agent turn economy;
#   the UI has live job polling instead.
EXCLUDED_FROM_UI = frozenset({"wait_for_synthesis"})


def category_of(tool_name: str) -> str:
    return _CATEGORY_BY_TOOL.get(tool_name, "other")


# --- Catalog (introspected once per process) ----------------------------------

_catalog_cache: Optional[List[Dict[str, Any]]] = None
_tools_by_name: Optional[Dict[str, Any]] = None


def _load_tools() -> Dict[str, Any]:
    """Lazy-import the agent tool registry (LangChain). Raises ImportError when
    the agent stack isn't installed — callers surface that honestly."""
    global _tools_by_name
    if _tools_by_name is None:
        from src.tools.wrappers import mcp_tools

        _tools_by_name = {t.name: t for t in mcp_tools if t.name not in EXCLUDED_FROM_UI}
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
            entries.append({
                "name": name,
                "description": (t.description or "").strip(),
                "category": category_of(name),
                "argsSchema": schema,
                "requiresSignIn": name in PROTECTED_TOOLS,
                "async": name in ASYNC_TOOLS,
                "mutates": name in MUTATING_TOOLS,
            })
        # Stable order: catalog category order, then registry order within.
        cat_rank = {cat: i for i, cat in enumerate(TOOL_CATEGORIES)}
        entries.sort(key=lambda e: cat_rank.get(e["category"], 99))
        _catalog_cache = entries
    return _catalog_cache


def tool_flags(name: str) -> Dict[str, bool]:
    return {
        "requiresSignIn": name in PROTECTED_TOOLS,
        "mutates": name in MUTATING_TOOLS,
        "async": name in ASYNC_TOOLS,
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
_FILE_ARG_KEYS = ("_file", "_files", "filename", "file_path")


def _looks_like_file_arg(key: str) -> bool:
    return key.endswith(_FILE_ARG_KEYS[0]) or key.endswith(_FILE_ARG_KEYS[1]) or key in _FILE_ARG_KEYS[2:]


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

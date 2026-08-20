"""Policy lives ON the tool, and a tool without policy fails a test.

Adding a tool must touch ONE file (``src/tools/wrappers.py``). Before this,
policy for 40 tools lived in five name-keyed string sets in a DIFFERENT file
(``src/api/tool_catalog.py``), two more in ``src/utils/attempt_logger.py``, and
a per-tool ``if tool == "..."`` chain in the same logger. A tool missing from
those sets **failed open**: ``tool_flags()`` answered ``requiresSignIn=False,
mutates=False`` for any unknown name — an unauthenticated write tool whose
changes never sync to object storage. ``sleep_tool`` had no policy anywhere
precisely because nothing checked.

These tests are the "nothing checked" part. Four guards:

1. **Completeness** — every registered tool declares a full policy, and every
   ``@tool`` in the registry module is registered.
2. **No fail-open** — an unknown name resolves to an ERROR, never to permissive
   defaults.
3. **Authz pin** — the category → ``Action`` mapping the MCP server applies is
   asserted, tool by tool, so a category re-cut cannot silently widen access.
4. **Derived, not duplicated** — the catalog's exported sets ARE the tools'
   declarations; a hand edit to either side fails here.
"""
from __future__ import annotations

import ast
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# 1. Completeness
# =============================================================================

def test_every_registered_tool_declares_a_full_policy():
    """RED for a tool that omits ``@policy`` — the guard that did not exist.

    Verified by adding a policy-less tool to ``ALL_TOOLS``: every test here that
    touches the registry goes red with ``ValueError: tool 'redproof_tool'
    declares no @policy``. They fail that loudly because ``tools_on_surface()``
    refuses to place an unclassified tool on any surface, so the registry module
    itself does not import — an unclassified tool is never served to anyone.
    """
    from src.tools.wrappers import ALL_TOOLS, SURFACE_NAMES, tool_policy

    missing = []
    for t in ALL_TOOLS:
        try:
            p = tool_policy(t)
        except ValueError:
            missing.append(t.name)
            continue
        assert isinstance(p.category, str) and p.category.strip(), t.name
        assert isinstance(p.protected, bool), t.name
        assert isinstance(p.mutates, bool), t.name
        assert isinstance(p.async_job, bool), t.name
        assert isinstance(p.requires_session, bool), t.name
        assert isinstance(p.disabled_when_bound, bool), t.name
        assert p.surfaces and not (p.surfaces - SURFACE_NAMES), t.name
    assert not missing, (
        "tools in the registry that declare no @policy — their sign-in, sync and "
        f"category classification would fail open: {sorted(missing)}"
    )


def test_every_tool_in_the_registry_module_is_registered():
    """A tool defined but left out of ``ALL_TOOLS`` is invisible to policy, to
    the catalog and to the agent. That must be loud, not silent."""
    from langchain_core.tools import BaseTool

    from src.tools import wrappers

    defined = {
        name for name, obj in vars(wrappers).items()
        if isinstance(obj, BaseTool)
    }
    registered = {t.name for t in wrappers.ALL_TOOLS}
    # Module attribute name == tool name for every @tool in this module.
    orphans = defined - registered
    assert not orphans, f"@tool defined but not in ALL_TOOLS: {sorted(orphans)}"


def test_every_category_has_a_presentation_order():
    """``CATEGORY_ORDER`` is the palette's group order. A category missing from
    it would silently sort last — say so here instead."""
    from src.api.tool_catalog import CATEGORY_ORDER, TOOL_CATEGORIES

    missing = set(TOOL_CATEGORIES) - set(CATEGORY_ORDER)
    assert not missing, f"categories with no place in CATEGORY_ORDER: {sorted(missing)}"
    stale = set(CATEGORY_ORDER) - set(TOOL_CATEGORIES)
    assert not stale, f"CATEGORY_ORDER names categories no tool declares: {sorted(stale)}"


def test_only_the_session_tools_opt_out_of_the_session_gate():
    """The MCP server gates EVERY call on ``requires_session`` before dispatch.
    The tools that opt out are exactly the session tools — the ones a stranger
    must be able to call BEFORE any session exists. Anything else opting out
    would be a tool running with no workspace to act on.

    Two independent declarations (the category and the gate field) asserted to
    agree: a session tool that demands a session cannot bootstrap anyone, and a
    design tool that waives one would dispatch into nothing."""
    from src.api.tool_catalog import requires_session
    from src.tools.wrappers import ALL_TOOLS, tool_policy, tools_on_surface

    served_over_mcp = tools_on_surface("mcp") + tools_on_surface("codex")
    sessionless = {t.name for t in served_over_mcp if not requires_session(t.name)}
    session_tools = {t.name for t in ALL_TOOLS if tool_policy(t).category == "session"}
    assert sessionless == session_tools, (
        "the tools that bypass the session gate are no longer the session "
        f"tools: bypassing={sorted(sessionless)} session={sorted(session_tools)}"
    )


def test_the_bound_refusal_set_is_session_management_only():
    """A server bound to ONE session (Codex) refuses the tools that create,
    list, switch or delete sessions — and nothing else. Both readers (the MCP
    server's refusal and the Codex engine's disabled_tools) take this set from
    the tools; this pins what it contains."""
    from src.api.tool_catalog import DISABLED_WHEN_BOUND, category_of, requires_session

    assert set(DISABLED_WHEN_BOUND) == {
        "create_session_tool", "list_sessions_tool",
        "set_active_session", "delete_session_tool",
    }
    for name in DISABLED_WHEN_BOUND:
        assert category_of(name) == "session"
        assert not requires_session(name)


# =============================================================================
# 2. No fail-open
# =============================================================================

def test_unknown_tool_never_resolves_to_permissive_defaults():
    from src.api import tool_catalog as tc

    for fn in (tc.policy_for, tc.tool_flags, tc.category_of, tc.requires_session):
        with pytest.raises(tc.UnknownToolError):
            fn("rm_rf")
    # KeyError subclass: callers that already catch KeyError keep working.
    assert issubclass(tc.UnknownToolError, KeyError)
    assert tc.is_invocable("rm_rf") is False


def test_a_partial_policy_is_a_hard_error():
    """Every required field is required: no silent False."""
    from src.tools.wrappers import ToolPolicy, policy

    with pytest.raises(TypeError):
        policy(category="essential", protected=True)  # missing mutates/async/...
    with pytest.raises(ValueError):
        ToolPolicy(category="essential", protected=False, mutates=False,
                   async_job=False, surfaces=("nowhere",), requires_session=True)
    with pytest.raises(ValueError):
        ToolPolicy(category="essential", protected=False, mutates=False,
                   async_job=False, surfaces=(), requires_session=True)
    with pytest.raises(ValueError):
        ToolPolicy(category="", protected=False, mutates=False,
                   async_job=False, surfaces=("agent",), requires_session=True)
    with pytest.raises(ValueError):
        ToolPolicy(category="essential", protected=False, mutates=False,
                   async_job=False, surfaces=("agent",), requires_session=True,
                   attempt_role="sometimes")
    # The two defaulted fields are the only ones a tool may leave out.
    p = ToolPolicy(category="essential", protected=False, mutates=False,
                   async_job=False, surfaces=("agent",), requires_session=True)
    assert p.disabled_when_bound is False and p.attempt_role is None


def test_unknown_tool_is_not_executable():
    from src.api import tool_catalog as tc

    with pytest.raises(KeyError):
        tc.validate_and_execute("rm_rf", REPO_ROOT, {})


# =============================================================================
# 3. Authz pin — a category re-cut cannot silently widen access
# =============================================================================
# The MCP server picks the capability Action from the tool's CATEGORY, so
# changing categories is an authorization change in disguise. This pins both
# halves: the rule in mcp_server.py, and the tool -> Action map it produces.
#
# Action.SYNTHESIZE and Action.SAVE are both outside ANONYMOUS_ALLOWED today, so
# a tool moving between them is invisible at runtime — which is exactly why it
# is pinned here rather than left to a behavioural test.

_AUTHZ_RULE = (
    'Action.SYNTHESIZE if name in TOOL_CATEGORIES["synthesis"] else Action.SAVE'
)

EXPECTED_TOOL_ACTIONS = {
    # category "synthesis" -> SYNTHESIZE
    "start_synthesis": "synthesize",
    "retry_pd": "synthesize",
    "get_synthesis_status": "synthesize",
    "wait_for_synthesis": "synthesize",
    "get_synthesis_metrics": "synthesize",
    "read_stage_report": "synthesize",
    "get_route_drc_summary": "synthesize",
    "get_cts_summary": "synthesize",
    "get_congestion_summary": "synthesize",
    "compare_pd_runs": "synthesize",
    "search_logs_tool": "synthesize",
    "schematic_tool": "synthesize",
    # everything else protected -> SAVE
    "write_spec": "save",
    "load_yaml_spec_file": "save",
    "write_file": "save",
    "apply_patch_tool": "save",
    "edit_file_tool": "save",
    "update_manifest": "save",
    "cocotb_tool": "save",
    "sby_tool": "save",
    "build_interactive_sim": "save",
    "save_metrics_tool": "save",
    "generate_report_tool": "save",
    "run_python_analysis": "save",
    "run_dslx_interpreter": "save",
    "compile_dslx_to_ir": "save",
    "experimental_compile_cpp_to_ir": "save",
    "optimize_xls_ir": "save",
    "codegen_xls": "save",
    "benchmark_xls": "save",
    "run_xls_flow": "save",
}


def test_the_authz_rule_is_still_keyed_on_the_category():
    """If this fails, the mapping below no longer describes reality — re-read
    mcp_server's capability gate before touching anything else."""
    with open(os.path.join(REPO_ROOT, "mcp_server.py"), encoding="utf-8-sig") as fh:
        source = fh.read()
    assert _AUTHZ_RULE in source, (
        "the MCP capability gate no longer reads "
        f"{_AUTHZ_RULE!r}; the category -> Action pin below is now unverified"
    )


def test_category_to_action_mapping_is_pinned():
    from src.api.tool_catalog import PROTECTED_TOOLS, TOOL_CATEGORIES
    from src.platform_engines.identity import Action

    synthesis = set(TOOL_CATEGORIES["synthesis"])
    actual = {
        name: (Action.SYNTHESIZE if name in synthesis else Action.SAVE).value
        for name in PROTECTED_TOOLS
    }
    assert actual == EXPECTED_TOOL_ACTIONS, (
        "a protected tool's capability Action changed. A category re-cut is an "
        "authorization change in disguise (mcp_server.py's gate): confirm the new "
        "Action is intended, then update this pin deliberately."
    )


def test_unprotected_tools_stay_out_of_the_capability_gate():
    """The anonymous trial covers lint/sim. These four are MUTATING but NOT
    protected on purpose; nothing here may quietly protect or unprotect them."""
    from src.api.tool_catalog import PROTECTED_TOOLS

    assert "linter_tool" not in PROTECTED_TOOLS
    assert "simulation_tool" not in PROTECTED_TOOLS
    assert "run_isolated_simulation" not in PROTECTED_TOOLS
    assert "read_file" not in PROTECTED_TOOLS


# =============================================================================
# 4. Derived, not duplicated
# =============================================================================

def test_catalog_sets_are_exactly_what_the_tools_declare():
    """Hand-edit either side and this fails. The catalog's sets are views."""
    from src.api import tool_catalog as tc
    from src.tools.wrappers import ALL_TOOLS, tool_policy

    declared = {t.name: tool_policy(t) for t in ALL_TOOLS}
    assert set(tc.PROTECTED_TOOLS) == {n for n, p in declared.items() if p.protected}
    assert set(tc.MUTATING_TOOLS) == {n for n, p in declared.items() if p.mutates}
    assert set(tc.ASYNC_TOOLS) == {n for n, p in declared.items() if p.async_job}
    assert set(tc.EXCLUDED_FROM_UI) == {
        n for n, p in declared.items() if "ui" not in p.surfaces
    }
    assert set(tc.DISABLED_WHEN_BOUND) == {
        n for n, p in declared.items() if p.disabled_when_bound
    }
    flat = {}
    for cat, names in tc.TOOL_CATEGORIES.items():
        for n in names:
            assert n not in flat, f"{n} is in two categories"
            flat[n] = cat
    assert flat == {n: p.category for n, p in declared.items()}


def test_the_derived_views_cannot_be_mutated():
    """A view that can be edited is a second source of truth waiting to happen."""
    from src.api import tool_catalog as tc

    with pytest.raises((TypeError, AttributeError)):
        tc.TOOL_CATEGORIES["synthesis"] = ()          # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        tc.PROTECTED_TOOLS.add("read_file")           # type: ignore[attr-defined]
    with pytest.raises((TypeError, AttributeError)):
        tc.MUTATING_TOOLS.add("read_file")            # type: ignore[attr-defined]


def test_the_registries_are_derived_from_surfaces():
    """``mcp_tools`` / ``architect_tools`` are filters over ONE list, in one
    order — not three lists that can disagree."""
    from src.tools.wrappers import ALL_TOOLS, architect_tools, mcp_tools, tool_policy

    assert mcp_tools == [t for t in ALL_TOOLS if "mcp" in tool_policy(t).surfaces]
    assert architect_tools == [t for t in ALL_TOOLS if "agent" in tool_policy(t).surfaces]
    # The two surfaces overlap on the design tools; what MCP has and the agent
    # does not is exactly the session bootstrap, which an in-process agent
    # (already inside a session) has no use for.
    mcp_only = {t.name for t in mcp_tools} - {t.name for t in architect_tools}
    assert mcp_only == {t.name for t in mcp_tools if not tool_policy(t).requires_session}


def test_the_catalog_is_the_ui_surface():
    from src.api.tool_catalog import EXCLUDED_FROM_UI, build_catalog
    from src.tools.wrappers import ALL_TOOLS, tool_policy

    catalogued = {e["name"] for e in build_catalog()}
    assert catalogued == {t.name for t in ALL_TOOLS if "ui" in tool_policy(t).surfaces}
    assert not (catalogued & set(EXCLUDED_FROM_UI))


# =============================================================================
# 5. The attempt log reads the tool's own declaration
# =============================================================================

def test_every_attempt_reader_is_claimed_by_a_tool():
    """The per-tool ``if tool == "..."`` chain is gone; these readers are
    reachable only through a tool's policy. An orphan means dead code."""
    from src.tools.wrappers import ALL_TOOLS, tool_policy
    from src.utils import attempt_logger

    exported = {
        getattr(attempt_logger, n) for n in dir(attempt_logger)
        if n.startswith("attempt_") and callable(getattr(attempt_logger, n))
    }
    claimed = {p.attempt_parser for p in map(tool_policy, ALL_TOOLS) if p.attempt_parser}
    assert exported == claimed, (
        "attempt readers no tool declares (or vice versa): "
        f"{sorted(f.__name__ for f in exported ^ claimed)}"
    )


def test_attempt_summary_tolerates_names_that_are_not_registry_tools():
    """Event rows carry system pseudo-tools (``synthesis_run``) and names the
    registry has since forgotten. Those have no attempt semantics — and must
    not raise. The session tools ARE registry tools now, and take no part in
    attempt tracking either; that is a null policy field, not a null policy."""
    from src.utils.attempt_logger import _tool_policy

    assert _tool_policy("synthesis_run") is None
    assert _tool_policy(_RENAMED_AWAY) is None  # a literal here would be a name the drift guard hunts
    assert _tool_policy("create_session_tool").attempt_role is None
    assert _tool_policy("linter_tool") is not None


def test_the_reports_lint_cell_asks_the_registry_which_tool_lints():
    """``design_report`` used to test an event row for ``tool == "linter_tool"``.
    It asks for the tools that declare the lint parser instead — the same
    declaration the attempt log reads — so a rename or a second lint tool
    reaches the report without anyone remembering it exists."""
    from src.api.tool_catalog import tools_with_attempt_parser
    from src.utils.attempt_logger import attempt_lint

    assert tools_with_attempt_parser(attempt_lint) == {"linter_tool"}
    assert tools_with_attempt_parser(lambda *a: None) == frozenset()


def test_attempt_roles_still_describe_the_flow():
    """The two sets that used to live in attempt_logger, now read off the tools.
    Pinned so a policy typo cannot quietly stop attempt tracking."""
    from src.tools.wrappers import ALL_TOOLS, tool_policy

    roles = {t.name: tool_policy(t).attempt_role for t in ALL_TOOLS}
    changes = {n for n, r in roles.items() if r in ("rtl_change", "synth_change")}
    checkpoints = {n for n, r in roles.items() if r == "checkpoint"}
    assert changes == {
        "write_spec", "load_yaml_spec_file", "write_file", "edit_file_tool",
        "apply_patch_tool", "start_synthesis",
    }
    assert checkpoints == {
        "linter_tool", "simulation_tool", "run_isolated_simulation",
        "get_synthesis_metrics", "generate_report_tool",
    }
    # run_isolated_simulation joined deliberately. It is the PREFERRED sim path
    # and the IDE's Simulate button routes to it, but it declared no attempt
    # policy, so a passing run recorded rtl_sim: "not_run" — the honest-state
    # invariant inverted, since the run happened and the log denied it.
    assert roles["start_synthesis"] == "synth_change"


# =============================================================================
# 6. The event-log names in actions.py are the registry's names
# =============================================================================

def test_ui_action_event_names_are_live_tools():
    """``/api/.../lint`` and friends do a tool's job without going through
    ``/invoke``, and log under that tool's name — positionally, which
    tests/test_tool_name_drift.py cannot see. Resolve those arguments here so a
    rename cannot leave the Activity feed logging a tool that no longer exists.
    """
    from src.tools.wrappers import ALL_TOOLS

    live = {t.name for t in ALL_TOOLS}
    path = os.path.join(REPO_ROOT, "src", "api", "actions.py")
    with open(path, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read())

    # (function name, index of the `tool` parameter) — read from the helpers'
    # own signatures, so moving the parameter cannot silently mis-target this.
    helpers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_ui_log_call", "_ui_log_result"):
            names = [a.arg for a in node.args.args]
            helpers[node.name] = names.index("tool")
    assert set(helpers) == {"_ui_log_call", "_ui_log_result"}, helpers

    found, dead = 0, []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fname not in helpers:
            continue
        idx = helpers[fname]
        arg = node.args[idx] if len(node.args) > idx else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found += 1
            if arg.value not in live:
                dead.append(f"actions.py:{node.lineno} logs as '{arg.value}'")
    assert found >= 6, f"expected the UI action log sites, found {found}"
    assert not dead, "UI actions logging under a tool name nothing answers to: " + str(dead)


# The attempt summary is behaviour that moved, not behaviour that changed. This
# scenario exercises all four readers, a change tool, a tool with no attempt
# role, the ``synthesis_run`` system pseudo-tool and a name the registry does
# not know. The expectation below was produced by the PRE-fold implementation
# (name-keyed sets + an ``if tool == "..."`` chain) and is byte-identical.
_RENAMED_AWAY = "a_name_the_registry_forgot"

_ATTEMPT_SCENARIO = [
    ("tool_call", "write_file", {}, "", "success"),
    ("tool_result", "write_file", {}, "ok", "success"),
    ("tool_call", "linter_tool", {}, "", "success"),
    ("tool_result", "linter_tool", {}, "Syntax OK", "success"),
    ("tool_call", "simulation_tool", {"mode": "rtl"}, "", "success"),
    ("tool_result", "simulation_tool", {"mode": "rtl"},
     '{"status": "test_passed", "mode": "rtl"}', "success"),
    ("tool_call", "read_file", {}, "", "success"),
    ("tool_result", "read_file", {}, "module a;", "success"),
    ("tool_call", "write_file", {}, "", "success"),
    ("tool_result", "write_file", {}, "ok", "success"),
    ("tool_call", "start_synthesis", {}, "", "success"),
    ("tool_result", "start_synthesis", {}, '{"run_id": "synth_0001"}', "success"),
    ("tool_result", "synthesis_run", {}, "done", "success"),
    ("tool_result", _RENAMED_AWAY, {}, "{}", "success"),
    ("tool_call", "get_synthesis_metrics", {}, "", "success"),
    ("tool_result", "get_synthesis_metrics", {},
     '{"status": "ok", "metrics": {"wns_ns": 0.1, "tns_ns": 0}}', "success"),
    ("tool_call", "simulation_tool", {"mode": "post_synth"}, "", "success"),
    ("tool_result", "simulation_tool", {"mode": "post_synth"},
     '{"status": "test_passed", "mode": "post_synth"}', "success"),
    ("tool_call", "generate_report_tool", {}, "", "success"),
    ("tool_result", "generate_report_tool", {}, "report", "success"),
]


def test_the_attempt_summary_survived_the_fold(tmp_path):
    import json

    from src.utils.attempt_logger import _write_summary

    workspace = tmp_path / "ws"
    workspace.mkdir()
    with open(workspace / "attempt_events.jsonl", "w", encoding="utf-8") as fh:
        for i, (etype, name, args, result, status) in enumerate(_ATTEMPT_SCENARIO):
            fh.write(json.dumps({
                "ts": f"2026-01-01T00:00:{i:02d}+00:00",
                "event_type": etype,
                "tool": name,
                "tool_call_id": f"call_{i // 2}",
                "arguments": args,
                "result": result,
                "status": status,
            }) + "\n")

    _write_summary(str(workspace), "sess_x")
    summary = json.loads((workspace / "attempt_log.json").read_text(encoding="utf-8"))

    assert summary["attempt_count"] == 2
    first, second = summary["attempts"]
    assert first["change_type"] == "rtl" and first["changes"] == ["write_file"]
    assert first["rtl_lint"] == "pass" and first["rtl_sim"] == "pass"
    assert first["synth_status"] == "not_run"
    # A checkpoint closed attempt 1, so the next change opened attempt 2.
    assert second["change_type"] == "both"
    assert second["changes"] == ["write_file", "start_synthesis"]
    assert second["synth_status"] == "completed"
    assert second["wns_ns"] == 0.1 and second["tns_ns"] == 0.0
    assert second["post_synth_sim"] == "pass"
    assert summary["final"] == {"success": True, "best_attempt": 2}

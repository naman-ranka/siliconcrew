"""Every tool argument is described, and every closed-set argument is enumerated.

Two properties, both derived — nothing about a tool is typed here twice.

1. **Description presence.** After ``@tool(parse_docstring=True)`` a Google
   ``Args:`` line becomes ``properties[arg].description`` in the JSON Schema
   every surface ships (agent, MCP ``tools/list``, the Command Surface catalog
   via ``tool_catalog._clean_schema``). LangChain fails at import when a
   docstring documents an argument that does NOT exist, but it says nothing
   when an argument is simply left out — that silent half is what this covers.

2. **Enum fidelity.** An argument whose implementation accepts a fixed set of
   values must carry that set as ``enum``, and the set asserted here is read out
   of the IMPLEMENTATION — a returned ``supported_stages`` list, an exported
   constant, or the set literal in the validating ``if`` — never out of the
   docstring that is under test. A docstring can lie about which values work;
   these authorities cannot.

The inventory is a bijection with the schemas: an argument that grows an enum
without an authority fails here just as loudly as an authority that stops
matching. That is deliberate — a hand-typed ``Literal`` is exactly the kind of
second list this repo does not keep.
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
from typing import Any, Dict, List, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("langchain_core")

from src.tools.wrappers import ALL_TOOLS


# =============================================================================
# Schema access
# =============================================================================

def _properties(tool) -> Dict[str, Dict[str, Any]]:
    if tool.args_schema is None:
        return {}
    return tool.args_schema.model_json_schema().get("properties", {})


def _all_schemas() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {t.name: _properties(t) for t in ALL_TOOLS}


# --- the two checkers, as pure functions so they can be proven to bite -------

def undescribed_args(schemas: Dict[str, Dict[str, Dict[str, Any]]]) -> List[str]:
    """``tool.arg`` for every argument with no (or empty) description."""
    out = []
    for tool_name, props in sorted(schemas.items()):
        for arg, prop in props.items():
            if not (prop.get("description") or "").strip():
                out.append(f"{tool_name}.{arg}")
    return out


def enum_mismatches(
    schemas: Dict[str, Dict[str, Dict[str, Any]]],
    authorities: Dict[Tuple[str, str], Set[str]],
) -> List[str]:
    """Every disagreement between a schema enum and the implementation.

    Reported in both directions: an enum the implementation does not back, and
    an implementation-backed argument whose schema forgot the enum.
    """
    out = []
    schema_enums = {
        (tool_name, arg): set(prop["enum"])
        for tool_name, props in schemas.items()
        for arg, prop in props.items()
        if prop.get("enum")
    }
    for key, declared in sorted(schema_enums.items()):
        if key not in authorities:
            out.append(
                f"{key[0]}.{key[1]}: enum {sorted(declared)} has no implementation "
                "authority in this test's inventory — add one, or drop the Literal"
            )
    for key, real in sorted(authorities.items()):
        declared = schema_enums.get(key)
        if declared is None:
            out.append(
                f"{key[0]}.{key[1]}: the implementation accepts exactly "
                f"{sorted(real)} but the schema carries no enum"
            )
        elif declared != real:
            out.append(
                f"{key[0]}.{key[1]}: schema enum {sorted(declared)} != "
                f"implementation {sorted(real)}"
            )
    return out


# =============================================================================
# The authorities — each read out of the implementation
# =============================================================================

def _validated_set_literal(func, variable: str) -> Set[str]:
    """The set in ``if <variable> not in {...}:`` inside ``func``'s own source.

    Some domains are inline set literals in the validating branch rather than a
    module constant. Reading them from the AST keeps this test anchored to the
    code that actually rejects a value, with no copy of the values here.
    """
    tree = ast.parse(inspect.getsource(func).lstrip())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        if not isinstance(node.ops[0], ast.NotIn):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == variable):
            continue
        right = node.comparators[0]
        if isinstance(right, (ast.Set, ast.Tuple, ast.List)):
            values = {e.value for e in right.elts if isinstance(e, ast.Constant)}
            if values:
                return values
    raise AssertionError(
        f"no `if {variable} not in {{...}}` guard found in {func.__qualname__} — "
        "the validator moved; re-anchor this authority"
    )


def _supported_from_rejection(result: Dict[str, Any]) -> Set[str]:
    """The ``supported_stages`` list a tool returns when handed a bad stage.

    The strongest authority available: the implementation itself enumerating
    what it will accept, at the moment it refuses something else.
    """
    assert result.get("status") == "error", result
    stages = result.get("supported_stages")
    assert stages, f"no supported_stages in {result}"
    return set(stages)


def _authorities(tmp_path) -> Dict[Tuple[str, str], Set[str]]:
    from src.tools import run_linter, run_simulation, run_xls, synthesis_manager as sm

    workspace = str(tmp_path)

    # retry_pd: ask the job function itself what it accepts, by giving it a
    # stage it does not.
    retry_stages = _supported_from_rejection(
        sm.retry_pd_job(workspace=workspace, source_run_id="synth_0001",
                        start_stage="not_a_stage")
    )
    retry_max_stages = _supported_from_rejection(
        sm.retry_pd_job(workspace=workspace, source_run_id="synth_0001",
                        start_stage="cts", max_stage="not_a_stage")
    )
    # start_synthesis validates max_stage before reserving quota or touching
    # disk, so this is a pure question with no side effect.
    synth_stages = _supported_from_rejection(
        sm.start_synthesis_job(workspace=workspace, verilog_files=[],
                               top_module="x", max_stage="not_a_stage")
    )
    # read_stage_report's supported list includes three pure aliases
    # (placement/global_route/final); the schema deliberately offers the six
    # canonical names, so the authority is the canonical subset — asserted to
    # BE a subset just below, in test_stage_aliases_are_a_superset.
    report_stages = set(sm._STAGE_REPORT_CANDIDATES) - {"placement", "global_route", "final"}

    return {
        ("linter_tool", "engine"): set(run_linter.ENGINES),
        ("run_simulation", "mode"):
            _validated_set_literal(run_simulation.run_simulation, "mode"),
        ("run_simulation", "sim_profile"):
            _validated_set_literal(run_simulation.run_simulation, "sim_profile"),
        ("start_synthesis", "constraints_mode"):
            _validated_set_literal(sm._constraints_guardrail, "constraints_mode"),
        ("start_synthesis", "max_stage"): synth_stages,
        ("retry_pd", "start_stage"): retry_stages,
        ("retry_pd", "max_stage"): retry_max_stages,
        ("read_stage_report", "stage"): report_stages,
        ("codegen_xls", "generator"): set(run_xls._VALID_GENERATORS),
        ("codegen_xls", "delay_model"): set(run_xls._VALID_DELAY_MODELS),
        ("benchmark_xls", "delay_model"): set(run_xls._VALID_DELAY_MODELS),
        ("run_xls_flow", "generator"): set(run_xls._VALID_GENERATORS),
        ("run_xls_flow", "delay_model"): set(run_xls._VALID_DELAY_MODELS),
    }


# =============================================================================
# Tests
# =============================================================================

def test_every_tool_argument_carries_a_description():
    missing = undescribed_args(_all_schemas())
    assert not missing, (
        "Arguments with no description in the schema every client reads. Add an "
        "`Args:` line for each in src/tools/wrappers.py (or a Field(description=…) "
        "for the two args_schema tools):\n  " + "\n  ".join(missing)
    )


def test_closed_set_arguments_match_the_implementation(tmp_path):
    problems = enum_mismatches(_all_schemas(), _authorities(tmp_path))
    assert not problems, "\n".join(["Enum drift between schema and implementation:"] + problems)


def test_retry_pd_and_constraints_mode_enums_are_the_real_domains(tmp_path):
    """The two the brief names explicitly, asserted against behaviour rather
    than against any list written down for the purpose."""
    from src.tools import synthesis_manager as sm

    schemas = _all_schemas()

    real_start = _supported_from_rejection(
        sm.retry_pd_job(workspace=str(tmp_path), source_run_id="synth_0001",
                        start_stage="floorplanX")
    )
    assert set(schemas["retry_pd"]["start_stage"]["enum"]) == real_start
    # retry_pd's domain is NARROWER than start_synthesis's: no constraints/synth.
    assert set(schemas["start_synthesis"]["max_stage"]["enum"]) > real_start

    real_modes = _validated_set_literal(sm._constraints_guardrail, "constraints_mode")
    assert set(schemas["start_synthesis"]["constraints_mode"]["enum"]) == real_modes
    assert "bypass" in real_modes


def test_stage_aliases_are_a_superset_of_the_offered_stages():
    """read_stage_report also answers to placement/global_route/final. Narrowing
    the enum to the six canonical names is a curation, not a lie — so the
    offered set must stay a strict subset of what the reader accepts."""
    from src.tools import synthesis_manager as sm

    offered = set(_all_schemas()["read_stage_report"]["stage"]["enum"])
    accepted = set(sm._STAGE_REPORT_CANDIDATES)
    assert offered < accepted
    assert accepted - offered == {"placement", "global_route", "final"}


def test_the_checkers_actually_bite():
    """Proof both guards fail on a tool that omits what they require.

    Without this, a checker that silently passed everything would look exactly
    like a clean repo.
    """
    good = {"toy": {"a": {"description": "an a.", "enum": ["x", "y"]}}}
    assert undescribed_args(good) == []
    assert enum_mismatches(good, {("toy", "a"): {"x", "y"}}) == []

    no_desc = {"toy": {"a": {"description": "", "enum": ["x", "y"]}}}
    assert undescribed_args(no_desc) == ["toy.a"]
    assert undescribed_args({"toy": {"a": {"enum": ["x"]}}}) == ["toy.a"]

    # an argument the implementation restricts, shipped without the enum
    no_enum = {"toy": {"a": {"description": "an a."}}}
    problems = enum_mismatches(no_enum, {("toy", "a"): {"x", "y"}})
    assert len(problems) == 1 and "carries no enum" in problems[0]

    # an enum that disagrees with the implementation
    wrong = {"toy": {"a": {"description": "an a.", "enum": ["x", "z"]}}}
    problems = enum_mismatches(wrong, {("toy", "a"): {"x", "y"}})
    assert len(problems) == 1 and "!=" in problems[0]

    # an enum with no authority at all
    orphan = {"toy": {"a": {"description": "an a.", "enum": ["x"]}}}
    problems = enum_mismatches(orphan, {})
    assert len(problems) == 1 and "no implementation authority" in problems[0]


def test_descriptions_do_not_restate_the_server_instructions():
    """SERVER_INSTRUCTIONS says once that a session is required and that tools
    run server-side on workspace-relative paths. Repeating it per tool is the
    duplication this pass removed; keep it removed."""
    banned = ("requires an active session", "select a session first",
              "runs server-side", "run server-side", "on the server, not")
    offenders = []
    for t in ALL_TOOLS:
        low = t.description.lower()
        for phrase in banned:
            if phrase in low:
                offenders.append(f"{t.name}: {phrase!r}")
    assert not offenders, "\n".join(offenders)


def test_no_tool_ships_an_unsubstituted_template():
    """A `{placeholder}` that reaches a client is a description that lies.

    Some descriptions are generated — the manifest role list is built from the
    FileRole Literal so it cannot advertise roles that no longer exist. That
    substitution has to reach the SCHEMA too, not just the description string,
    because parse_docstring lifts argument prose into schema fields and MCP
    clients read the schema.
    """
    import re

    from src.tools.wrappers import ALL_TOOLS

    placeholder = re.compile(r"\{[a-z_]+\}")
    leaks = []
    for t in ALL_TOOLS:
        for m in placeholder.findall(t.description or ""):
            leaks.append(f"{t.name} description: {m}")
        if t.args_schema is None:
            continue
        for arg, spec in t.args_schema.model_json_schema().get("properties", {}).items():
            for m in placeholder.findall(spec.get("description", "") or ""):
                leaks.append(f"{t.name}.{arg} schema: {m}")
    assert not leaks, "unsubstituted templates reaching clients: " + "; ".join(leaks)


def test_the_simulation_tool_records_an_attempt():
    """Simulation must leave evidence in the attempt log.

    There were two sim tools and only one of them declared this, so a passing
    run through the OTHER one recorded as "not_run" — the honest-state invariant
    inverted: the run happened and the log said it did not. One tool now, and it
    is the one the IDE's Simulate button routes to.
    """
    from src.utils.attempt_logger import attempt_simulation
    from src.tools.wrappers import run_simulation

    policy = run_simulation.func.__tool_policy__
    assert policy.attempt_role == "checkpoint"
    assert policy.attempt_parser is attempt_simulation

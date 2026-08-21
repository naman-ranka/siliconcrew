"""X2M-2 disproof + schema drift guard.

X2M-2 hypothesized that the five PD-summary tools (get_synthesis_metrics plus
the four stage readers, since merged into read_stage_report) returned JSON-RPC
-32602 on hosted because their generated MCP inputSchema was something the
SDK/connector validation rejects.

That hypothesis is DISPROVEN here, empirically and durably:
  * every registered MCP tool's generated schema is a well-formed JSON Schema;
  * a canonical call payload validates against every one of them;
  * the run_id-only reader that survives the merge has a schema structurally
    identical (modulo title/description) to a tool that WORKED on hosted in the
    same minute (generate_report_tool) — see
    test_failing_pd_tools_schemas_match_a_working_tool.

So identical schemas produced opposite outcomes → -32602 is not a schema-shape
problem (it is the F9c framework mis-map under post-synth backend degradation;
see report). This test also guards the future: a newly added tool whose schema
is malformed, or which rejects a plain call, trips it before it ships.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("langchain_core")
jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator

from src.tools.wrappers import mcp_tools


def _schema(tool):
    if tool.args_schema is not None:
        return tool.args_schema.model_json_schema()
    return {"type": "object", "properties": {}}


def _dummy_for(prop_schema):
    # An argument with a closed value set is only "well-formed" if the value is
    # IN that set — a schema-shape test must not send 'x' to an enum field and
    # then read the (correct) rejection as a schema defect.
    enum = prop_schema.get("enum")
    if enum:
        return enum[0]
    t = prop_schema.get("type")
    if t == "string":
        return "x"
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "array":
        return []
    if t == "object":
        return {}
    return "x"  # untyped → a string is the safe default


def _canonical_payload(schema):
    """A payload a well-behaved caller would send: every REQUIRED field filled
    with a value of its declared type; optionals omitted."""
    props = schema.get("properties", {})
    required = schema.get("required", [])
    return {name: _dummy_for(props.get(name, {})) for name in required}


@pytest.mark.parametrize("tool", mcp_tools, ids=[t.name for t in mcp_tools])
def test_every_mcp_tool_schema_is_wellformed_and_accepts_a_canonical_call(tool):
    schema = _schema(tool)
    # 1. The schema is itself a valid JSON Schema (what the connector consumes).
    Draft202012Validator.check_schema(schema)
    # 2. A canonical call payload validates — no tool's schema rejects a plain
    #    well-formed call (which is what -32602 "Invalid request parameters"
    #    would mean if it were schema-caused).
    payload = _canonical_payload(schema)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, f"{tool.name}: canonical payload {payload} rejected: {errors[0].message}"


def test_failing_pd_tools_schemas_match_a_working_tool():
    """The load-bearing disproof: the run_id-only PD reader that returned -32602
    has a schema structurally identical (modulo title/description) to
    generate_report_tool, which WORKED on hosted. Identical schema, opposite
    outcome ⇒ the schema is not the cause.

    The other four readers of that report are one tool now, and it takes a
    stage — so it can no longer be compared shape-for-shape. The disproof does
    not depend on it: one identical-schema pair with opposite outcomes is the
    whole argument."""
    byname = {t.name: t for t in mcp_tools}

    def norm(tool):
        import json

        s = json.loads(json.dumps(_schema(tool)))
        s.pop("title", None)
        s.pop("description", None)
        for v in s.get("properties", {}).values():
            if isinstance(v, dict):
                v.pop("title", None)
                # Per-argument prose is the "modulo description" this test's
                # docstring already claims: the readers take the same run_id but
                # word it for their own subject. Shape is what is under test.
                v.pop("description", None)
        return json.dumps(s, sort_keys=True)

    control = norm(byname["generate_report_tool"])  # worked on hosted
    for name in ("get_synthesis_metrics",):
        assert norm(byname[name]) == control, (
            f"{name} schema differs from generate_report_tool — if this ever "
            "becomes true it would be a real schema lead; today they are identical"
        )

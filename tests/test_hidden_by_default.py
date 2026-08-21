"""What "hidden by default" means, written down as a test.

Six rare-flow or environment-dependent tools no longer cost an agent
description bytes for a step it will almost never take. Hidden is a statement
about SURFACES, and about which ones:

  * off ``agent`` — the in-process architect's tool list;
  * off ``mcp``   — what a default MCP connection is advertised and caches;
  * on ``ui``     — a person can still run every one of them from the Command
                    Surface and REST ``/invoke``;
  * on ``codex``  — a server started with ``--codex-tools`` still offers them,
                    which is how our own first-party clients start it (the Codex
                    runtime and the benchmark harness).

So nothing is deleted and nothing is unreachable. Formal verification and cocotb
are differentiators; they are hidden because they are rarely the next step, not
because they are unimportant. Re-enabling them for an agent is connect-time tool
scoping, which is a later phase — deliberately not a runtime toggle, because the
last one leaked one tenant's tool list into another's.
"""
import pytest

from src.tools import wrappers
from src.tools.wrappers import ALL_TOOLS, architect_tools, mcp_tools, tool_policy, tools_on_surface


HIDDEN = {
    "run_xls_flow",
    "build_interactive_sim",
    "schematic_tool",
    "run_python_analysis",
    "cocotb_tool",
    "sby_tool",
}


def _names(tools) -> set:
    return {t.name for t in tools}


def test_the_hidden_set_is_exactly_these_six():
    """Derived from the tools' own declarations, so hiding a seventh (or
    un-hiding one) has to be a deliberate edit here too."""
    hidden = {t.name for t in ALL_TOOLS
              if tool_policy(t).surfaces == frozenset(wrappers.HIDDEN_BY_DEFAULT)}
    assert hidden == HIDDEN


@pytest.mark.parametrize("name", sorted(HIDDEN))
def test_a_hidden_tool_is_off_the_agent_and_mcp_surfaces(name):
    assert name not in _names(architect_tools)
    assert name not in _names(mcp_tools)


@pytest.mark.parametrize("name", sorted(HIDDEN))
def test_a_hidden_tool_is_still_reachable(name):
    """Never deleted: the human surface and the first-party client keep it."""
    assert name in _names(ALL_TOOLS)
    assert name in _names(tools_on_surface("ui"))
    assert name in _names(tools_on_surface("codex"))


@pytest.mark.parametrize("name", sorted(HIDDEN))
def test_a_hidden_tool_keeps_its_full_policy(name):
    """Hiding is not a place to stop declaring things. Category, sign-in gating
    and mutation still have to be answered, because the surfaces it is still on
    read them."""
    policy = tool_policy(next(t for t in ALL_TOOLS if t.name == name))
    assert policy.category
    assert policy.requires_session is True
    assert isinstance(policy.protected, bool)
    assert isinstance(policy.mutates, bool)


# The nineteen tools that DO the design work. The skill tools sit beside them
# and are listed separately below, because they act on knowledge rather than on
# the workspace — and because a reader counting the agent's levers should get
# nineteen, not twenty-one.
FLOW_TOOLS = {
    "write_spec", "read_spec",
    "write_file", "read_file", "edit_file", "list_files_tool",
    "get_manifest", "update_manifest",
    "linter_tool", "run_simulation", "waveform_tool",
    "start_synthesis", "retry_pd", "get_synthesis_status",
    "get_synthesis_metrics", "read_stage_report", "compare_pd_runs",
    "search_logs_tool", "generate_report_tool",
}
SKILL_TOOLS = {"list_skills", "read_skill"}


def test_the_agent_surface_is_the_flow_tools_plus_the_skill_pair():
    """The number this wave exists to reach, and the list it is made of. A tool
    added to the agent's list from now on is a decision someone has to make
    here, out loud. The skill pair was that decision: the store lives outside
    every workspace, so `read_file` cannot reach it."""
    assert _names(architect_tools) == FLOW_TOOLS | SKILL_TOOLS
    assert len(FLOW_TOOLS) == 19
    assert len(architect_tools) == 21


def test_a_default_mcp_connection_gets_the_same_set_plus_the_bootstrap():
    """A stranger's client sees exactly what the agent sees, plus the session
    tools it needs before any session exists — and nothing else."""
    sessionless = {t.name for t in mcp_tools if not tool_policy(t).requires_session}
    assert _names(mcp_tools) - sessionless == FLOW_TOOLS
    assert SKILL_TOOLS <= _names(mcp_tools)   # knowledge needs no session...
    assert SKILL_TOOLS <= sessionless          # ...and must survive the gate
    assert not (_names(mcp_tools) & HIDDEN)


def test_the_command_surface_keeps_every_hidden_tool():
    from src.api.tool_catalog import build_catalog

    assert HIDDEN <= {e["name"] for e in build_catalog()}

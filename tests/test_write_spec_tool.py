"""Authoring a spec and adopting one the user supplied are one tool.

Both built a ``DesignSpec``, wrote ``<module>_spec.yaml`` and regenerated
``constraints.sdc``; the only difference was where the fields came from. So
adopting is now an argument on the authoring tool.

The adopter also had a hole worth naming: it accepted an absolute path and, when
a relative name did not resolve in the workspace, fell back to the REPO ROOT —
and its argument name matched none of the patterns the ``/invoke`` containment
check looks for, so it was unguarded on every surface. Both halves of that are
tested here: the tool confines the path itself (covering agent, MCP and REST by
construction) and the surface rule now recognises a ``_path`` argument too.
"""

import os

import pytest
import yaml

from src.api import tool_catalog
from src.tools import wrappers


PORTS = [
    {"name": "clk", "direction": "input"},
    {"name": "count", "direction": "output", "width": 8},
]

# The spec file format: fields nested under the module name.
SUPPLIED_SPEC = {
    "adder": {
        "description": "an adder the user specified",
        "clock_period": "5.0ns",
        "ports": [
            {"name": "clk", "direction": "input"},
            {"name": "sum", "direction": "output", "width": 16},
        ],
    }
}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: str(workspace))
    return workspace


def _spec(**kwargs) -> str:
    return wrappers.write_spec.invoke(kwargs)


# --- authoring (unchanged) -----------------------------------------------------

def test_authoring_writes_the_spec_and_the_sdc(ws):
    out = _spec(module_name="counter", description="an 8-bit counter",
                ports=PORTS, clock_period_ns=4.0)
    assert "Spec created successfully" in out
    written = yaml.safe_load((ws / "counter_spec.yaml").read_text(encoding="utf-8"))
    assert list(written) == ["counter"]
    assert [p["name"] for p in written["counter"]["ports"]] == ["clk", "count"]
    assert "create_clock" in (ws / "constraints.sdc").read_text(encoding="utf-8")


def test_authoring_still_reports_validation_failures(ws):
    out = _spec(module_name="counter", description="broken",
                ports=[{"direction": "input"}])
    assert "Spec validation failed" in out
    assert not (ws / "counter_spec.yaml").exists()


def test_authoring_without_the_required_fields_says_which_ones(ws):
    out = _spec(module_name="counter")
    assert out.startswith("Error:")
    assert "ports" in out and "yaml_path" in out


# --- adopting (was load_yaml_spec_file) ---------------------------------------

def test_adopting_a_supplied_spec_saves_it_under_its_module_name(ws):
    (ws / "problem_spec.yaml").write_text(yaml.safe_dump(SUPPLIED_SPEC), encoding="utf-8")
    out = _spec(yaml_path="problem_spec.yaml")
    assert "Loaded External Spec: adder" in out
    saved = yaml.safe_load((ws / "adder_spec.yaml").read_text(encoding="utf-8"))
    assert list(saved) == ["adder"]
    assert saved["adder"]["description"] == "an adder the user specified"
    assert "create_clock" in (ws / "constraints.sdc").read_text(encoding="utf-8")


def test_adopting_regenerates_the_sdc_from_the_adopted_period(ws):
    """The adopter REPLACED whatever authoring produced — including the SDC."""
    _spec(module_name="counter", description="an 8-bit counter", ports=PORTS,
          clock_period_ns=40.0)
    first = (ws / "constraints.sdc").read_text(encoding="utf-8")
    assert "40" in first

    (ws / "problem_spec.yaml").write_text(yaml.safe_dump(SUPPLIED_SPEC), encoding="utf-8")
    _spec(yaml_path="problem_spec.yaml")
    second = (ws / "constraints.sdc").read_text(encoding="utf-8")
    assert second != first and "5" in second


def test_a_missing_spec_file_says_how_to_get_one_in(ws):
    out = _spec(yaml_path="nope.yaml")
    assert out.startswith("Error:")
    assert "write_file" in out


def test_both_halves_at_once_is_refused(ws):
    (ws / "problem_spec.yaml").write_text(yaml.safe_dump(SUPPLIED_SPEC), encoding="utf-8")
    out = _spec(module_name="counter", description="x", ports=PORTS,
                yaml_path="problem_spec.yaml")
    assert out.startswith("Error:")
    assert "not both" in out
    assert not (ws / "adder_spec.yaml").exists()
    assert not (ws / "counter_spec.yaml").exists()


# --- the hole the merge closed -------------------------------------------------

def test_an_absolute_path_is_refused(ws, tmp_path):
    outside = tmp_path / "secret.yaml"
    outside.write_text(yaml.safe_dump(SUPPLIED_SPEC), encoding="utf-8")
    out = _spec(yaml_path=str(outside))
    assert out.startswith("Error:")
    assert "Access denied" in out
    assert not (ws / "adder_spec.yaml").exists()


def test_climbing_out_of_the_workspace_is_refused(ws, tmp_path):
    (tmp_path / "secret.yaml").write_text(yaml.safe_dump(SUPPLIED_SPEC), encoding="utf-8")
    out = _spec(yaml_path="../secret.yaml")
    assert out.startswith("Error:")
    assert "Access denied" in out


def test_the_repo_root_is_no_longer_a_fallback(ws):
    """A name that does not resolve in the workspace used to be retried against
    the repo root, which made every file in the checkout readable as YAML."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(repo_root, "requirements.txt"))
    out = _spec(yaml_path="requirements.txt")
    assert out.startswith("Error:")
    assert "not found in the workspace" in out


def test_the_containment_rule_now_recognises_a_path_argument(ws):
    """Defense in depth: the /invoke surface check keys off the argument NAME,
    and a ``_path`` argument used to sail straight through it."""
    with pytest.raises(tool_catalog.ToolArgumentError):
        tool_catalog.enforce_file_containment(str(ws), {"yaml_path": "../escape.yaml"})
    # ...and an ordinary workspace-relative name is still fine.
    tool_catalog.enforce_file_containment(str(ws), {"yaml_path": "problem_spec.yaml"})

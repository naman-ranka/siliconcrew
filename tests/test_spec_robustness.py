"""Spec-tooling robustness against real-world malformed agent payloads (E9/A27).

Two live-verified failure modes drove these tests:

1. Gemini intermittently emits port dicts with literally-quoted keys
   (``{'"name"': "clk"}``) — every ``p.get("name")`` missed, so validation
   said "Port name cannot be empty" once per port with no hint why, and the
   agent looped write_spec until giving up. Fix: normalize port-entry keys in
   both ``create_spec_from_dict`` and ``parse_yaml_spec``, and echo the keys
   actually received in the empty-name validation error.

2. Agents hand-writing flat YAML via write_file made ``parse_yaml_spec``
   raise ``AttributeError: 'str' object has no attribute 'get'`` — surfaced
   by read_spec as a useless error string. Fix: isinstance guards that raise
   honest ValueErrors naming the problem.
"""
import os

import pytest

from src.tools.spec_manager import (
    create_spec_from_dict,
    parse_yaml_spec,
    validate_spec,
)


# ---------------------------------------------------------------------------
# Quoted-key port payloads simply work
# ---------------------------------------------------------------------------

def test_quoted_key_ports_accepted_from_dict():
    """Literally-quoted keys (as Gemini emits them) parse to real ports."""
    data = {
        "module_name": "counter",
        "description": "8-bit counter",
        "ports": [
            {'"name"': "clk", '"direction"': "input"},
            {'"name"': "count", '"direction"': "output", '"width"': 8},
        ],
    }
    spec = create_spec_from_dict(data)
    assert [p.name for p in spec.ports] == ["clk", "count"]
    assert spec.ports[0].direction == "input"
    assert spec.ports[1].width == 8

    result = validate_spec(spec)
    assert result["valid"], result["errors"]


def test_whitespace_padded_keys_accepted_from_dict():
    spec = create_spec_from_dict({
        "module_name": "counter",
        "description": "c",
        "ports": [{" name ": "clk", " direction ": "input"}],
    })
    assert spec.ports[0].name == "clk"
    assert spec.ports[0].direction == "input"


def test_quoted_key_ports_accepted_in_yaml():
    yaml_content = """
counter:
  description: Simple counter
  clock_period: 10ns
  ports:
    - '"name"': clk
      '"direction"': input
    - '"name"': count
      '"direction"': output
      '"width"': 8
"""
    spec = parse_yaml_spec(yaml_content)
    assert [p.name for p in spec.ports] == ["clk", "count"]
    assert spec.ports[1].width == 8


def test_write_spec_accepts_quoted_key_ports_end_to_end(tmp_path, monkeypatch):
    """The full write_spec tool path succeeds on a quoted-key payload."""
    ws = tmp_path / "ws"
    ws.mkdir()
    # No session context in a unit test → get_workspace_path() falls to the env.
    monkeypatch.setenv("RTL_WORKSPACE", str(ws))
    from src.tools.wrappers import write_spec

    out = write_spec.invoke({
        "module_name": "counter",
        "description": "8-bit counter",
        "ports": [
            {'"name"': "clk", '"direction"': "input"},
            {'"name"': "count", '"direction"': "output", '"width"': 8},
        ],
    })
    assert "Spec created successfully" in out
    assert (ws / "counter_spec.yaml").exists()
    # The written spec round-trips with clean (unquoted) keys.
    spec = parse_yaml_spec((ws / "counter_spec.yaml").read_text())
    assert [p.name for p in spec.ports] == ["clk", "count"]


# ---------------------------------------------------------------------------
# Malformed YAML → honest ValueError, never AttributeError
# ---------------------------------------------------------------------------

def test_flat_yaml_raises_honest_error():
    """Hand-written flat YAML (no module wrapper) names the actual problem."""
    flat = """
module_name: counter
description: An 8-bit counter
clock_period: 10ns
"""
    with pytest.raises(ValueError) as exc_info:
        parse_yaml_spec(flat)
    msg = str(exc_info.value)
    assert "expected a mapping under 'module_name'" in msg
    assert "got str" in msg


def test_scalar_top_level_yaml_raises_honest_error():
    with pytest.raises(ValueError) as exc_info:
        parse_yaml_spec("just a string")
    assert "expected a top-level mapping" in str(exc_info.value)
    assert "got str" in str(exc_info.value)


def test_scalar_ports_entry_raises_honest_error():
    yaml_content = """
counter:
  description: c
  clock_period: 10ns
  ports:
    - name: clk
      direction: input
    - count
"""
    with pytest.raises(ValueError) as exc_info:
        parse_yaml_spec(yaml_content)
    msg = str(exc_info.value)
    assert "ports entry 2" in msg
    assert "got str" in msg


def test_non_list_ports_raises_honest_error():
    yaml_content = """
counter:
  description: c
  clock_period: 10ns
  ports: clk
"""
    with pytest.raises(ValueError) as exc_info:
        parse_yaml_spec(yaml_content)
    msg = str(exc_info.value)
    assert "'ports' should be a list" in msg
    assert "got str" in msg


# ---------------------------------------------------------------------------
# Empty-name validation error echoes the keys actually received
# ---------------------------------------------------------------------------

def test_write_spec_empty_name_error_echoes_received_keys(tmp_path, monkeypatch):
    """Misnamed port keys yield a diagnosable error, not a bare 'cannot be empty'."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RTL_WORKSPACE", str(ws))
    from src.tools.wrappers import write_spec

    out = write_spec.invoke({
        "module_name": "counter",
        "description": "c",
        "ports": [
            {"port_name": "clk", "dir": "input"},
            {"name": "count", "direction": "output"},
        ],
    })
    assert "Spec validation failed" in out
    assert "Port name cannot be empty (entry keys: 'port_name', 'dir')" in out
    # The well-formed entry is not blamed.
    assert out.count("Port name cannot be empty") == 1
    # Nothing was written.
    assert not (ws / "counter_spec.yaml").exists()

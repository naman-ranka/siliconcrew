"""A module name is an identifier, not a path.

Every consumer of a spec treats `module_name` as an identifier, and some build a
FILENAME out of it. Adopting an external YAML took the top-level key as the
module name without validating it, so a file keyed `"../../pwned"` produced a
spec whose write target resolved outside the workspace.

Validating at parse time — rather than at each call site — means the property
holds for every consumer by construction: the tool that adopts, the tool that
authors, the report writer, and anything added later.
"""
import os

import pytest

from src.tools.spec_manager import parse_yaml_spec


def _yaml_for(module_name: str) -> str:
    # Single-quoted YAML: no backslash escape processing, so a Windows-style
    # traversal reaches OUR validation instead of dying in the YAML lexer.
    escaped = module_name.replace("'", "''")
    return (
        f"'{escaped}':\n"
        "  description: demo\n"
        "  clock_period: 10ns\n"
        "  ports:\n"
        "    - name: clk\n"
        "      direction: input\n"
        "      width: 1\n"
        "      description: clock\n"
    )


@pytest.mark.parametrize(
    "hostile",
    [
        "../../pwned",           # the reported escape
        "..",
        "a/b",                   # subdirectory
        "/etc/passwd",           # absolute
        "..\\windows",           # backslash traversal
        "9starts_with_digit",    # not an identifier
        "has space",
        "",
    ],
)
def test_a_module_name_that_is_not_an_identifier_is_refused(hostile):
    with pytest.raises(ValueError) as exc:
        parse_yaml_spec(_yaml_for(hostile))
    assert "module name" in str(exc.value).lower()


@pytest.mark.parametrize("legal", ["counter", "fifo_16x8", "_internal", "top$gen", "A9"])
def test_legal_verilog_identifiers_still_parse(legal):
    assert parse_yaml_spec(_yaml_for(legal)).module_name == legal


def test_the_derived_filename_cannot_leave_the_workspace(tmp_path):
    """The concrete failure: the spec filename is built from the module name."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError):
        spec = parse_yaml_spec(_yaml_for("../../pwned"))
        # Unreachable once parsing refuses; kept so the test states the harm.
        target = os.path.abspath(os.path.join(str(workspace), f"{spec.module_name}_spec.yaml"))
        assert target.startswith(os.path.abspath(str(workspace)) + os.sep)

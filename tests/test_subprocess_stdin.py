"""Every tool subprocess gets its own stdin, never the server's.

Under `mcp_server.py --transport stdio` (how the Codex runtime runs the tools),
the server's stdin IS the JSON-RPC pipe. A child that inherits it can block on
it: on Windows, `git rev-parse` for sim provenance hung until the client sent
its next message, ~180 s on the first run_simulation of every Codex session,
long enough for Codex to abandon the call. `timeout=` did not help: it killed
Git for Windows' launcher while the real git kept the output pipes open.

So each call site passes `stdin=` (usually DEVNULL) or feeds `input=`. This
scans the source rather than trusting a list, so a new call site is covered
the day it is written.
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "src" / "tools", ROOT / "src" / "platform_engines", ROOT / "mcp_server.py"]
CALLS = {"run", "Popen", "check_output", "check_call", "call"}


def _files():
    for p in SCANNED:
        yield from ([p] if p.is_file() else sorted(p.rglob("*.py")))


def _kwarg_dicts(tree):
    """Names bound to dict(...) literals that set stdin= (the `**popen_kwargs` pattern)."""
    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", None) == "dict"
                and any(k.arg == "stdin" for k in node.value.keywords)):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _offenders():
    bad = []
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        safe_dicts = _kwarg_dicts(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in CALLS
                    and getattr(node.func.value, "id", None) == "subprocess"):
                continue
            kws = {k.arg for k in node.keywords}
            splats = {getattr(k.value, "id", None) for k in node.keywords if k.arg is None}
            if kws & {"stdin", "input"} or splats & safe_dicts:
                continue
            bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return bad


def test_every_tool_subprocess_sets_its_own_stdin():
    bad = _offenders()
    assert not bad, (
        "subprocess call(s) inherit the server's stdin — pass stdin=subprocess.DEVNULL "
        "(or input=...):\n  " + "\n  ".join(bad)
    )


def test_the_scan_sees_call_sites():
    # Guard the guard: if a refactor moved the tools, an empty scan would pass vacuously.
    count = sum(
        1 for path in _files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in CALLS and getattr(node.func.value, "id", None) == "subprocess"
    )
    assert count >= 15

"""One guard so a tool rename cannot leave dead names scattered behind.

Tool names are strings almost everywhere: catalog policy sets, frontend maps,
``/invoke`` payloads, MCP wire names, the architect prompt, the docs. A rename
that misses one of those fails *silently* — the agent calls a tool that no
longer exists, the Command Surface renders a stale entry, the docs lie. Nothing
in the test suite notices.

This module notices. It derives the live tool set FROM THE REGISTRY
(``src/tools/wrappers.py`` plus the session tools ``mcp_server.py`` declares),
scans the repo for places where a token is a tool name *by construction*, and
fails with a grouped file:line list of every reference that no longer resolves.
There is not a single hardcoded tool name below — rename a tool and the guard
retargets itself.

Scope, and why it is drawn here
-------------------------------
* **String references only.** A bare identifier (``from src.tools.wrappers
  import read_file``) fails LOUDLY at import time, and several tool names are
  also the names of the underlying implementation functions
  (``get_route_drc_summary`` lives in ``synthesis_manager.py`` too), so treating
  identifiers as tool references is both unnecessary and ambiguous. Strings are
  the silent half — they are what this guard covers.
* **Names must contain an underscore.** Every live tool name does. A future
  single-word tool name would be indistinguishable from ordinary prose, so
  dead references to one would be invisible here (documented limitation).
* Recorded history is not a reference: ``tests/fixtures/**`` and ``workspace/**``
  hold captured ``attempt_events.jsonl``/run artifacts, which legitimately
  mention whatever the tools were called when they were recorded.

False positives were the design problem (a guard that cries wolf gets deleted).
Every rule below is either context-exact (the token *must* be a tool name where
it was found) or, for prose, shape-filtered against the registry's own naming
grammar plus the small ``BENIGN`` allowlist at the bottom — 15 entries, each
justified on its own line, and each asserted to still match something.

Known gaps, stated plainly: a tool name passed POSITIONALLY to a helper whose
own name says nothing about tools is not detected here — covering it in general
needs cross-file argument resolution. The one place it mattered
(``_ui_log_call(ws, sid, "linter_tool", ...)`` in ``src/api/actions.py``) is now
resolved exactly, by signature, in
``tests/test_tool_policy.py::test_ui_action_event_names_are_live_tools``. A
line-context rule ("any tool-shaped string on a line mentioning tools") was
measured instead: +423 references covered, but +22 suppressions, so it was
rejected as the kind of noise that gets a test deleted.
"""
from __future__ import annotations

import ast
import os
import re
import warnings
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF_REL = os.path.join("tests", os.path.basename(__file__))

SCAN_SUFFIXES = (".py", ".ts", ".tsx", ".md")
SKIP_DIRS = {
    ".git", "node_modules", ".next", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", "dist", "build", "out", "coverage", "htmlcov",
    "test-results", "playwright-report", ".ruff_cache", ".turbo", "site-packages",
}
# Captured history / generated artifacts — mentions there are records, not references.
# ``cvdp-pipeline/research`` is the same thing in prose: dated post-hoc audits
# that quote per-tool CALL COUNTS from runs that already happened. Rewriting the
# tool names in a measurement would falsify the measurement, and nothing
# executes from those files.
SKIP_PREFIXES = (
    os.path.join("tests", "fixtures"),
    "workspace",
    os.path.join("bench-orchestrator", "runs"),
    os.path.join("bench-orchestrator", "final_runs"),
    os.path.join("cvdp-pipeline", "research"),
)

# A tool-name-shaped token: lowercase snake_case with at least one underscore.
_SNAKE = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
_SNAKE_RE = re.compile(_SNAKE)

# --- rule 1: contexts where a quoted token IS a tool name --------------------
# No shape filtering needed: the surrounding syntax already says "tool name".
_STRONG_CONTEXTS: Tuple[Tuple[str, re.Pattern], ...] = (
    # MCP wire names: mcp__silicon_crew__<tool>
    ("mcp-wire", re.compile(r"mcp__[A-Za-z0-9_]*?[Cc]rew__(" + _SNAKE + r")")),
    # tool == "x" / tool: "x" / tool_name="x" / toolName === "x"
    ("tool-key", re.compile(r"""\btool(?:_name|Name|name)?\s*(?:===|!==|==|=|:)\s*["'`](""" + _SNAKE + r""")["'`]""")),
    # {"tool": "x"} / {'tool_name': 'x'}  (invoke payloads, event records)
    ("tool-field", re.compile(r"""["']tool(?:_name)?["']\s*:\s*["'](""" + _SNAKE + r""")["']""")),
    # any *tool* function called with a literal name: call_tool("x"), toolKind('x'),
    # artifactKeyForToolCall("x"), prettifyToolName("x"). The function name is
    # captured too so a LIVE TOOL called with a data argument
    # (create_session_tool("counter_design")) can be dropped — that argument is
    # a session name, not a tool name.
    ("tool-call", re.compile(r"""\b(\w*[Tt]ool\w*)\(\s*["'`](""" + _SNAKE + r""")["'`]""")),
    # MCP Tool(name="x") declarations
    ("tool-decl", re.compile(r"""\b\w*[Tt]ool\w*\(\s*name\s*=\s*["'](""" + _SNAKE + r""")["']""")),
)

# --- rule 2: collections whose declared name says they hold tool names -------
# CHANGE_TOOLS = {...} / const RUNS_REFRESH_TOOLS = new Set([...]) / TOOL_LABELS = {...}
_TOOLISH_NAME = re.compile(r"tool", re.IGNORECASE)
_TS_TOOL_DECL = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w*[Tt][Oo][Oo][Ll]\w*)\s*(?::[^=]*)?=\s*"
    r"(?:new\s+Set\(|new\s+Map\(|\[|\{|\()"
)
_TS_KEY = re.compile(r"""^\s*["']?(""" + _SNAKE + r""")["']?\s*:""")
_TS_STR = re.compile(r"""["'](""" + _SNAKE + r""")["']""")
# Catalog-entry objects inside a tool collection: { name: "waveform_tool", ... }
_TS_NAME_FIELD = re.compile(r"""["']?name["']?\s*:\s*["'`](""" + _SNAKE + r""")["'`]""")

# --- rule 3: prose (prompts, docs, embedded prompt strings) ------------------
_BACKTICKED = re.compile(r"`(" + _SNAKE + r")`")
_BARE_WORD = re.compile(r"(?<![`\w/.\-])(" + _SNAKE + r")(?![\w/.\-])")


# =============================================================================
# The live tool set — derived, never typed
# =============================================================================

def _mcp_server_declared_tools() -> Set[str]:
    """Tools declared directly in ``mcp_server.py`` as ``Tool(name="...")``.

    There are none any more — the six session tools that used to live there are
    registry tools now (``test_the_server_hand_declares_no_tools`` pins that).
    Kept because the server declaring a tool by hand is exactly what would make
    it invisible to the registry, and this is the only reader that would see it
    at all."""
    path = os.path.join(REPO_ROOT, "mcp_server.py")
    tree = _parse(_read(path))
    names: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = getattr(func, "id", None) or getattr(func, "attr", None) or ""
        if not fname.endswith("Tool"):
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                names.add(kw.value.value)
    return names


def live_tool_names() -> Set[str]:
    """Every name a caller may legitimately reference today.

    The whole registry, not a union of surfaces: a tool served on ONE surface
    (the Codex-only prompt tool) is just as live as one served on all of them,
    and the surfaces are themselves derived from the same list."""
    from src.agents.subagents import subagent_tool_names
    from src.tools.wrappers import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    names |= _mcp_server_declared_tools()
    # The delegation tool is native-agent-only and cannot be a registry entry —
    # it closes over the turn's resolved key and pinned model, so it has no
    # identity to advertise ahead of time (src/agents/subagents.py). It is still
    # a tool name people write down, so it is still live here. Derived, like
    # everything else in this function.
    names |= set(subagent_tool_names())
    return names


def _naming_grammar(live: Set[str]) -> Tuple[Set[str], Set[str]]:
    """The registry's own naming grammar: leading verbs and trailing nouns."""
    return ({n.split("_")[0] for n in live}, {n.split("_")[-1] for n in live})


def _tool_shaped(token: str, firsts: Set[str], lasts: Set[str]) -> bool:
    """Prose filter: only tokens built like a registry name are considered.
    Drops the overwhelming majority of snake_case prose (signal names, JSON
    fields, module ids) without ever hiding a name the registry itself could
    have produced."""
    parts = token.split("_")
    return parts[0] in firsts or parts[-1] in lasts or "tool" in parts


# =============================================================================
# The scanner
# =============================================================================

Hit = Tuple[str, str, int, str]  # (tool name, relpath, lineno, rule)


def _parse(text: str):
    """ast.parse, without letting a scanned file's own SyntaxWarning
    (e.g. an invalid escape in some unrelated module) pollute this run."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(text)


def _read(path: str) -> str:
    # utf-8-sig: src/agents/architect.py carries a BOM; without this its
    # embedded prompt silently fails to parse and 40 tool mentions go unchecked.
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def iter_repo_files(root: str = REPO_ROOT) -> Iterable[Tuple[str, str]]:
    """(relpath, text) for every file in scanning scope."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if not name.endswith(SCAN_SUFFIXES):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if rel == SELF_REL or rel.startswith(SKIP_PREFIXES):
                continue
            yield rel, _read(path)


def _scan_python_collections(rel: str, tree: ast.Module) -> List[Hit]:
    """Python assignments whose NAME says they hold tool names."""
    hits: List[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and _TOOLISH_NAME.search(t.id) for t in targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and value.args:  # frozenset({...}), set([...])
            value = value.args[0]
        elements: List[ast.expr] = []
        if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            elements = list(value.elts)
        elif isinstance(value, ast.Dict):
            elements = [k for k in value.keys if k is not None]  # keys only: values are payloads
        for el in elements:
            if isinstance(el, ast.Constant) and isinstance(el.value, str) and _SNAKE_RE.fullmatch(el.value):
                hits.append((el.value, rel, el.lineno, "tool-collection"))
    return hits


def _bracket_delta(line: str) -> int:
    return (line.count("{") + line.count("[") + line.count("(")
            - line.count("}") - line.count("]") - line.count(")"))


def _scan_ts_collections(rel: str, lines: List[str]) -> List[Hit]:
    """TS/TSX ``const *TOOL* = new Set([...]) / = { ... }`` blocks.

    Only the collection's OWN level counts (depth 1): a mocked catalog entry
    nests an ``argsSchema`` whose property names (``vcd_file``, ``start_time``)
    are arguments, not tools. Nested ``name:`` fields are the exception — that
    is exactly where a catalog fixture names its tool."""
    hits: List[Hit] = []
    depth = base = 0
    active = False
    for idx, line in enumerate(lines):
        if not active:
            if not _TS_TOOL_DECL.match(line):
                continue
            active = True
            body = line.split("=", 1)[1]
            # `new Set([` opens two brackets; that pair IS the collection's own
            # level, so whatever the declaration opens becomes the baseline.
            depth = base = max(_bracket_delta(line), 0)
            own_level = True
            closing = 0
        else:
            body = line
            own_level = depth <= base
            closing = _bracket_delta(line)
        if own_level:
            key = _TS_KEY.match(body)
            if key:
                hits.append((key.group(1), rel, idx + 1, "tool-collection"))
            else:  # set / array elements
                for m in _TS_STR.finditer(body):
                    hits.append((m.group(1), rel, idx + 1, "tool-collection"))
        for m in _TS_NAME_FIELD.finditer(body):
            hits.append((m.group(1), rel, idx + 1, "tool-collection"))
        depth += closing
        if depth <= 0:
            active = False
    return hits


def _scan_python_prompt_strings(rel: str, tree: ast.Module, firsts: Set[str], lasts: Set[str]) -> List[Hit]:
    """Backticked names inside embedded PROMPT text (the architect system
    prompt, MCP prompt payloads). Docstrings are excluded on purpose: this repo
    documents functions with backticks, and those are identifier references,
    not tool references (43 false positives if included, 0 with them out)."""
    hits: List[Hit] = []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            blob = node.value
        elif isinstance(node, ast.JoinedStr):
            blob = "".join(v.value for v in node.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
        else:
            continue
        # "prompt-like": long, multi-line, and mentioning several backticked names.
        if len(blob) < 400 or "\n" not in blob:
            continue
        tokens = _BACKTICKED.findall(blob)
        if len(tokens) < 2:
            continue
        for token in tokens:
            if _tool_shaped(token, firsts, lasts):
                hits.append((token, rel, node.lineno, "embedded-prompt"))
    return hits


def scan_text(rel: str, text: str, live: Set[str]) -> List[Hit]:
    """Every tool-name reference in one file. Pure — the self-test feeds it
    synthetic content to prove the detector actually detects."""
    firsts, lasts = _naming_grammar(live)
    hits: List[Hit] = []
    lines = text.splitlines()

    for lineno, line in enumerate(lines, 1):
        # Cheap prefilter: every strong context needs "tool"/"Tool" (→ "ool")
        # or an MCP wire prefix on the line. Skips ~95% of lines.
        if "ool" not in line and "rew__" not in line:
            continue
        for rule, pattern in _STRONG_CONTEXTS:
            for m in pattern.finditer(line):
                if rule == "tool-call":
                    # create_session_tool("counter_design") — a live tool called
                    # with a DATA argument; the argument is not a tool name.
                    if m.group(1) in live:
                        continue
                    hits.append((m.group(2), rel, lineno, rule))
                    continue
                hits.append((m.group(1), rel, lineno, rule))

    if rel.endswith(".py"):
        try:
            tree = _parse(text)
        except SyntaxError:  # a deliberately broken fixture module, not a reference
            tree = None
        if tree is not None:
            hits += _scan_python_collections(rel, tree)
            hits += _scan_python_prompt_strings(rel, tree, firsts, lasts)
    elif rel.endswith((".ts", ".tsx")):
        hits += _scan_ts_collections(rel, lines)

    in_prompts = rel.startswith("prompts" + os.sep)
    if rel.endswith(".md"):
        # Docs/prompts: backticked names, shape-filtered. Prompts additionally
        # get bare mentions — an unbackticked name there is still an
        # instruction to the agent to call it.
        for lineno, line in enumerate(lines, 1):
            for m in _BACKTICKED.finditer(line):
                if _tool_shaped(m.group(1), firsts, lasts):
                    hits.append((m.group(1), rel, lineno, "prose"))
            if in_prompts:
                for m in _BARE_WORD.finditer(line):
                    if _tool_shaped(m.group(1), firsts, lasts):
                        hits.append((m.group(1), rel, lineno, "prompt-text"))
    return hits


_SCAN_CACHE: Dict[int, List[Hit]] = {}


def scan_repo(live: Set[str] | None = None) -> List[Hit]:
    """Every tool-name reference in the repo. Cached: the scan is pure and the
    tests below share it, so a push pays for one pass."""
    live = live_tool_names() if live is None else live
    key = hash(frozenset(live))
    if key not in _SCAN_CACHE:
        hits: List[Hit] = []
        for rel, text in iter_repo_files():
            hits += scan_text(rel, text, live)
        _SCAN_CACHE[key] = hits
    return _SCAN_CACHE[key]


# =============================================================================
# Allowlist: benign matches, one justification per line
# =============================================================================
# Tokens the rules above catch that are NOT tool names. Small by design — if
# this list grows past a couple dozen the matching is too loose, not the repo.
BENIGN: Dict[str, str] = {
    "run_id": "tool ARGUMENT/field name, all over prompts and docs",
    "route_stage_status": "a FIELD of get_route_drc_summary's result, not a tool",
    "run_docker_command": "src/platform_engines helper function, cited in deploy/RUNBOOK.md",
    "get_synthesis": "deliberately fake name in frontend/test/activityFilters.test.ts (prefix fallback)",
    "get_synthesis_report": "deliberately fake name in a frontend test — asserts an UNREGISTERED tool falls to 'other'. The get_synthesis_* prefix heuristic it once guarded is gone; synthesis membership is now totality-tested against the backend category.",
    "rm_rf": "deliberately unknown tool in the /invoke 404 test (test_workbench_v2_api.py)",
    "synthesis_run": "SYSTEM pseudo-tool on run-completion events (attempt_logger), never a registry tool",
    "configure_tool_filter": "docs/TOOL_DESIGN_DECISIONS.md records it as REMOVED — deliberate history",
}

# Dead references that ALREADY exist on this branch. Not fixed here on purpose
# (this item builds the detector; the rename wave fixes the references), but
# recorded so the guard can still run green and catch NEW drift. Each entry is
# asserted to still exist — fix it and the ledger tells you to delete the line.
# Dead names this scanner still DETECTS somewhere. Every entry is asserted to
# still be found, so a fixed reference forces its removal from this ledger — the
# list cannot rot into a permanent excuse.
#
# The four entries this started with are down to one. Fixed in P0:
#   search_logs      -> search_logs_tool  (prompts/architect/pareto_sweep_prompt_v{1,2}.md)
#                       This was a live bug: the Pareto prompt told the agent to
#                       call a tool that does not exist.
#   ppa_tool         -> get_synthesis_metrics   (docs/MCP_SETUP.md)
#   get_synthesis_job-> get_synthesis_status    (tests/test_mcp.py expected-tools list)
#
# `synthesis_tool` survives because older docs use it as an illustrative example
# inside code blocks and transcripts (docs/TOOL_AUTO_DISCOVERY.md,
# MCP_SESSION_GUIDE.md, TOOL_DESIGN_DECISIONS.md, MCP_VSCODE_SETUP.md). Rewriting
# those belongs to the docs sweep, not here.
#
# HONEST LIMIT: `ppa_tool` also still appears in several of those same docs, but
# in shapes no rule matches, so the scanner no longer sees it and the ledger
# cannot carry it. Prose inside doc code blocks is a known blind spot — see the
# module docstring. Do not read an empty ledger as "no dead names anywhere".
KNOWN_DEAD: Dict[str, str] = {
    "synthesis_tool": "older docs use it as an example (start_synthesis is the real tool) — docs sweep",
}


def _group(hits: Iterable[Hit]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for name, rel, lineno, rule in hits:
        grouped[name].append(f"{rel}:{lineno} ({rule})")
    return grouped


def _also_mentioned(names: Set[str], detected: Set[Tuple[str, str, int]]) -> Dict[str, List[str]]:
    """Plain whole-word mentions of a dead name that no rule flagged (prose,
    imports, positional args). Only ever computed on failure — it turns a
    detection into the COMPLETE fix list."""
    extra: Dict[str, List[str]] = defaultdict(list)
    patterns = {n: re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])") for n in names}
    for rel, text in iter_repo_files():
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in patterns.items():
                if name in line and pattern.search(line) and (name, rel, lineno) not in detected:
                    extra[name].append(f"{rel}:{lineno}")
    return extra


def _report(grouped: Dict[str, List[str]], live: Set[str],
            extra: Dict[str, List[str]] | None = None) -> str:
    extra = extra or {}
    lines = [
        "",
        f"Dead tool-name references: {len(grouped)} name(s) that no live tool answers to.",
        "Fix every line below, or add the name to KNOWN_DEAD/BENIGN in "
        f"{SELF_REL} with a reason.",
        "",
    ]
    for name in sorted(grouped):
        places = sorted(set(grouped[name]))
        lines.append(f"  {name}  ({len(places)} reference(s))")
        lines += [f"      {p}" for p in places]
        others = sorted(set(extra.get(name, [])))
        if others:
            lines.append(f"    ...plus {len(others)} plain mention(s) to sweep:")
            lines += [f"      {p}" for p in others]
        lines.append("")
    lines.append(f"Live tools ({len(live)}): {', '.join(sorted(live))}")
    return "\n".join(lines)


# =============================================================================
# Tests
# =============================================================================

def test_every_tool_name_reference_resolves_to_a_live_tool():
    """The safety net: rename a tool and every stale mention of the old name
    turns into a file:line fix list instead of silent rot."""
    live = live_tool_names()
    dead = [h for h in scan_repo(live)
            if h[0] not in live and h[0] not in BENIGN and h[0] not in KNOWN_DEAD]
    grouped = _group(dead)
    extra = _also_mentioned({h[0] for h in dead}, {(h[0], h[1], h[2]) for h in dead}) if dead else {}
    assert not grouped, _report(grouped, live, extra)


def test_the_server_hand_declares_no_tools():
    """One registry, no exceptions. ``mcp_server.py`` used to declare six tools
    with hand-written JSON schemas — advertised to every client, invisible to
    the catalog, to @policy and to the schema tests. Every tool it serves now
    comes from the registry; a new ``Tool(name="...")`` there would be a second
    source of truth, so it fails here."""
    assert _mcp_server_declared_tools() == set()


def test_suppression_lists_are_not_stale():
    """BENIGN and KNOWN_DEAD are debt lists, not dumping grounds: once a match
    stops occurring its entry must go, so neither list can quietly grow into a
    place where a dead name hides."""
    seen = {name for name, _, _, _ in scan_repo()}
    stale_dead = sorted(set(KNOWN_DEAD) - seen)
    stale_benign = sorted(set(BENIGN) - seen)
    assert not stale_dead, (
        "KNOWN_DEAD entries no longer found in the repo — delete them from "
        f"{SELF_REL}: {stale_dead}"
    )
    assert not stale_benign, (
        "BENIGN suppressions that no longer match anything — delete them from "
        f"{SELF_REL}: {stale_benign}"
    )


def test_detector_flags_a_renamed_tool():
    """Proof the guard bites. A tool renamed in the registry leaves references
    behind in exactly these shapes; each must be reported."""
    live = live_tool_names()
    victim = sorted(live)[0]
    stale = victim + "_old"  # a name the registry no longer knows

    samples = {
        "some/mod.py": f'if tool == "{stale}":\n',
        "frontend/lib/x.ts": f'const RUNS_REFRESH_TOOLS = new Set(["{stale}"]);\n',
        "docs/guide.md": f"Call `{stale}` to do the thing.\n",
        "prompts/architect/p.md": f"- {stale} -> use it first\n",
        "mcp/client.py": f'name = "mcp__silicon_crew__{stale}"\n',
    }
    for rel, text in samples.items():
        found = {h[0] for h in scan_text(rel, text, live)}
        assert stale in found, f"detector missed a stale reference in {rel}: {text!r}"
        assert stale not in live


def test_catalog_policy_sets_reference_live_tools_only():
    """The catalog's policy views must name live tools only.

    They are now DERIVED from the tools' own ``@policy`` declarations
    (src/tools/wrappers.py), so this can no longer fail by someone forgetting to
    rename a string here — but it stays as the cheap end-to-end check that the
    derivation still produces real names."""
    from src.api import tool_catalog

    live = live_tool_names()
    policy: Set[str] = set(tool_catalog.PROTECTED_TOOLS) | set(tool_catalog.ASYNC_TOOLS) \
        | set(tool_catalog.MUTATING_TOOLS) | set(tool_catalog.EXCLUDED_FROM_UI)
    for names in tool_catalog.TOOL_CATEGORIES.values():
        policy |= set(names)
    assert not policy - live, f"tool_catalog policy names no live tool answers to: {sorted(policy - live)}"

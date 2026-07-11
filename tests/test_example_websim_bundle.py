"""Drift gate for shipped interactive-sim example bundles.

A checked-in ``<top>.websim.json`` is a COMPILED artifact of checked-in RTL.
If someone edits the example's Verilog without regenerating the netlist, the
shipped dashboard silently plays the OLD design — the exact honest-state
failure the platform forbids. This gate recomputes the provenance hashes so
that divergence fails CI instead of shipping.

Also enforces the fork-safety rules for these bundles: dashboards declare
their netlist by bare relative name, and websim sources are workspace-relative
(no absolute paths, no traversal) so a forked/templated copy still works.
"""
import glob
import hashlib
import json
import os
from html.parser import HTMLParser

import pytest

from src.tools.build_interactive_sim import ARTIFACT_FORMAT

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")

WEBSIM_ARTIFACTS = sorted(
    glob.glob(os.path.join(EXAMPLES, "*", "workspace", "*.websim.json"))
)
DASHBOARDS = sorted(
    glob.glob(os.path.join(EXAMPLES, "*", "workspace", "*.dashboard.html"))
)

class _SimMetaParser(HTMLParser):
    """Real HTML parsing (attribute order/quoting agnostic) so this gate can't
    diverge from the runtime's DOMParser on valid HTML."""

    def __init__(self):
        super().__init__()
        self.sim_ref = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.sim_ref is not None:
            return
        d = dict(attrs)
        if (d.get("name") or "").lower() == "siliconcrew-sim":
            self.sim_ref = d.get("content")


def parse_sim_meta(html):
    p = _SimMetaParser()
    p.feed(html)
    return p.sim_ref


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_meta_parser_is_quoting_and_order_agnostic():
    """The runtime uses DOMParser; this gate must accept the same valid HTML
    (single quotes, reversed attribute order) — no false drift failures."""
    assert parse_sim_meta("<meta name='siliconcrew-sim' content='a.websim.json'>") == "a.websim.json"
    assert parse_sim_meta('<meta content="b.websim.json" name="siliconcrew-sim">') == "b.websim.json"
    assert parse_sim_meta('<META NAME="siliconcrew-sim" CONTENT="c.websim.json">') == "c.websim.json"
    assert parse_sim_meta("<html><body>no meta</body></html>") is None


def test_at_least_one_runnable_example_ships():
    assert WEBSIM_ARTIFACTS, "expected a shipped websim example (traffic_light)"
    assert DASHBOARDS, "expected a shipped dashboard example (traffic_light)"


@pytest.mark.parametrize("artifact", WEBSIM_ARTIFACTS)
def test_websim_artifact_fresh_against_sources(artifact):
    with open(artifact) as f:
        payload = json.load(f)
    assert payload["format"] == ARTIFACT_FORMAT, artifact
    assert payload["sources"], f"{artifact} has no provenance sources"

    workspace = os.path.dirname(artifact)
    for rel, recorded in payload["sources"].items():
        assert not os.path.isabs(rel) and ".." not in rel.split("/"), (
            f"{artifact}: source {rel!r} is not workspace-relative (fork-unsafe)"
        )
        src = os.path.join(workspace, rel)
        assert os.path.isfile(src), f"{artifact}: source {rel} missing from bundle"
        assert _sha256(src) == recorded, (
            f"DRIFT: {rel} changed after {os.path.basename(artifact)} was built — "
            f"re-run build_interactive_sim for this example"
        )

    # netlist must actually contain the declared top
    assert payload["top"] in payload["yosys_netlist"]["modules"], artifact
    assert payload["ports"], artifact


@pytest.mark.parametrize("dashboard", DASHBOARDS)
def test_dashboard_declares_an_existing_netlist_by_relative_name(dashboard):
    with open(dashboard) as f:
        html = f.read()
    ref = parse_sim_meta(html)
    assert ref, f"{dashboard} has no siliconcrew-sim meta tag (would render as mockup)"
    assert "/" not in ref and not os.path.isabs(ref), (
        f"{dashboard}: netlist ref {ref!r} must be a bare sibling name (fork-safe)"
    )
    assert os.path.isfile(os.path.join(os.path.dirname(dashboard), ref)), (
        f"{dashboard}: declared netlist {ref} not shipped in the bundle"
    )
    # the dashboard drives the sim only through the bridge
    assert "simBridge" in html, f"{dashboard} never touches window.simBridge"

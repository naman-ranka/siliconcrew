"""The post-synthesis *sim contract* recorded by synthesis and read by sim.

A whole class of post-synth-sim bugs (stdcell path, run-id resolution,
netlist-vs-RTL, absolute-path leaks) shared one root cause: the simulation tool
re-discovered state by heuristic — guessing workspace paths, resolving runs from
an ambiguous ``cwd``, walking directories and scoring filenames to *find* the
netlist — instead of reading the authoritative record synthesis already
produced. Every heuristic was a latent bug.

Synthesis is the authority on what a post-synth simulation needs: which gate
netlist it produced, the platform, the top module, and the stdcell model set.
It records these — as **workspace-relative** paths — into ``run_meta.json`` under
the ``sim_contract`` key at finalize time (the one moment the netlist is known
for certain, right after ORFS wrote it). Simulation **reads** this contract
instead of re-discovering: no directory walking, no filename scoring, no
cwd-based run resolution, no path guessing.

Workspace-relative paths keep the record portable: a returning session resolves
on any instance and the contract never leaks an absolute host path (invariant #5,
run dir is the database). Older runs without a contract still resolve through a
legacy fallback (``netlist_path``) so nothing that worked before breaks.

The one resolver here serves both callers of the single simulation wrapper: the
human in the IDE (one-click "simulate my latest synth") and the LLM agent (which
cannot see the file tree and needs minimal, unambiguous, structured results).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from src.tools.synthesis_manager import get_run_dir

SIM_CONTRACT_VERSION = 1
SIM_CONTRACT_KEY = "sim_contract"
RUN_META_FILENAME = "run_meta.json"


def _to_rel(workspace: str, path: Optional[str]) -> Optional[str]:
    """Workspace-relative POSIX form of ``path`` (portable; no absolute leak).

    If ``path`` already sits outside the workspace we keep it as given — the
    caller decides whether that is acceptable — but paths under the workspace
    (the common case) become relative so the record survives a move to another
    instance / self-host root.
    """
    if not path:
        return None
    if not os.path.isabs(path):
        return path.replace("\\", "/")
    try:
        rel = os.path.relpath(path, workspace)
    except ValueError:
        # Different drive on Windows — cannot make relative; keep absolute.
        return path.replace("\\", "/")
    if rel.startswith(".."):
        return path.replace("\\", "/")
    return rel.replace("\\", "/")


def build_sim_contract(
    workspace: str,
    *,
    netlist_abs: Optional[str],
    platform: Optional[str],
    top: Optional[str],
    stdcell_manifest_version: Optional[str] = None,
    netlist_origin: str = "synthesis",
) -> Dict[str, Any]:
    """The sim contract synthesis stamps into ``run_meta.json``.

    ``netlist_abs`` is the gate-level netlist synthesis just produced (absolute,
    as returned by the ORFS finalization). It is stored **workspace-relative** so
    the record is portable. Everything post-synth simulation needs to compile is
    named here; sim never has to look for it again.
    """
    return {
        "schema_version": SIM_CONTRACT_VERSION,
        "mode": "post_synth",
        "platform": platform,
        "top": top,
        # Workspace-relative POSIX path to the gate netlist (None if synthesis
        # produced none — an honest, resolvable-as-not-found state).
        "netlist": _to_rel(workspace, netlist_abs),
        "netlist_origin": netlist_origin,
        # The stdcell model *set* required to elaborate the netlist is keyed by
        # platform; the manifest version pins exactly which models were baked.
        "stdcell_platform": platform,
        "stdcell_manifest_version": stdcell_manifest_version,
    }


@dataclass
class PostSynthResolution:
    """The resolved post-synth simulation inputs, plus an honest echo of *how*
    they were resolved so both the IDE card and the agent can see what ran."""

    netlist_abs: str
    platform: str
    resolved_run_id: Optional[str] = None
    resolved_netlist: Optional[str] = None  # workspace-relative echo
    stdcell_source: Optional[str] = None
    top: Optional[str] = None
    # How resolution happened: "explicit" (caller passed a netlist),
    # "contract" (read the sim_contract), or "legacy_netlist_path" (older run
    # without a contract — fallback that keeps prior runs working).
    source: str = "contract"
    contract: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionError:
    """A typed, semantic resolution failure — never a leaked traceback.

    ``code`` names the cause the IDE renders and the agent branches on;
    ``recovery`` (when present) points at a native platform operation both can
    invoke, instead of a shell command the platform cannot run.
    """

    code: str
    message: str
    recovery: Optional[Dict[str, Any]] = None


def _read_run_meta(run_dir: str) -> Dict[str, Any]:
    path = os.path.join(run_dir, RUN_META_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _abs_netlist(workspace: str, netlist: Optional[str]) -> Optional[str]:
    if not netlist:
        return None
    return netlist if os.path.isabs(netlist) else os.path.join(workspace, netlist)


def resolve_post_synth(
    workspace: str,
    run_id: Optional[str] = None,
    netlist_file: Optional[str] = None,
    platform: Optional[str] = None,
) -> Tuple[Optional[PostSynthResolution], Optional[ResolutionError]]:
    """Resolve the netlist + platform for a post-synth sim from the run record.

    Precedence (authoritative first, heuristics never):
      1. An explicit ``netlist_file`` + ``platform`` the caller passed wins
         (invariant #1: the manifest suggests, free entry is still allowed).
      2. The synthesis run's ``sim_contract`` (workspace-relative netlist +
         platform + stdcell set) — the authoritative record.
      3. Legacy ``netlist_path`` on the run_meta (older runs, pre-contract) so
         previously-working runs keep working.

    Returns ``(resolution, None)`` on success or ``(None, error)`` with a typed
    semantic cause. All paths are resolved against ``workspace`` — never a
    (possibly isolated) exec cwd.
    """
    # An explicit netlist the caller passed is always honored for the netlist
    # (invariant #1: free entry stays allowed). We only touch the run record for
    # the fields the caller did not pin — the netlist and/or the platform.
    explicit_netlist_abs = _abs_netlist(workspace, netlist_file) if netlist_file else None
    if explicit_netlist_abs and not os.path.exists(explicit_netlist_abs):
        return None, ResolutionError(
            code="netlist_not_found",
            message=(
                "Post-synth mode was given an explicit netlist that does not "
                f"exist: {netlist_file}"
            ),
        )

    resolved_run_id: Optional[str] = run_id
    source = "explicit"
    top = None
    contract: Dict[str, Any] = {}
    netlist_abs = explicit_netlist_abs

    need_record = (netlist_abs is None) or (not platform)
    if need_record:
        # Resolve the run record against the WORKSPACE — never a (possibly
        # isolated) exec cwd. This is what #50 fixed at the sim_manager layer;
        # the contract centralizes it here for every caller of the one wrapper.
        run_dir = get_run_dir(workspace, run_id)
        if run_dir is None:
            if run_id:
                return None, ResolutionError(
                    code="run_not_found",
                    message=(
                        f"Unknown synthesis run_id '{run_id}'. Run start_synthesis, "
                        "or pass an existing run_id (omit it to use the latest)."
                    ),
                )
            return None, ResolutionError(
                code="run_not_found",
                message=(
                    "No synthesis run found to simulate. Run synthesis first, then "
                    "simulate in post_synth mode."
                ),
            )

        resolved_run_id = os.path.basename(run_dir)
        meta = _read_run_meta(run_dir)
        contract = meta.get(SIM_CONTRACT_KEY) or {}

        if contract:
            source = "explicit" if explicit_netlist_abs else "contract"
            if netlist_abs is None:
                netlist_abs = _abs_netlist(workspace, contract.get("netlist"))
            platform = platform or contract.get("platform")
            top = contract.get("top")
        else:
            # Legacy fallback: the pre-contract absolute netlist_path. Kept so
            # runs produced before the sim contract shipped still resolve.
            source = "explicit" if explicit_netlist_abs else "legacy_netlist_path"
            if netlist_abs is None:
                netlist_abs = _abs_netlist(workspace, meta.get("netlist_path"))
            platform = platform or meta.get("platform")
            top = meta.get("top_module")

    if not netlist_abs or not os.path.exists(netlist_abs):
        return None, ResolutionError(
            code="netlist_not_found",
            message=(
                f"Synthesis run '{resolved_run_id}' recorded no usable gate-level "
                "netlist to simulate. Re-run synthesis to the finish stage (it "
                "writes the netlist the sim contract points at)."
            ),
        )

    if not platform:
        return None, ResolutionError(
            code="platform_unknown",
            message=(
                f"Synthesis run '{resolved_run_id}' has no platform recorded; "
                "post-synth simulation cannot pick the stdcell model set."
            ),
        )

    return (
        PostSynthResolution(
            netlist_abs=netlist_abs,
            platform=platform,
            resolved_run_id=resolved_run_id,
            resolved_netlist=_to_rel(workspace, netlist_abs),
            stdcell_source=platform,
            top=top,
            source=source,
            contract=contract,
        ),
        None,
    )


def stdcell_recovery_action(platform: Optional[str]) -> Dict[str, Any]:
    """A native, invokable recovery for a missing/incomplete stdcell cache.

    Both surfaces can act on this without a shell: the IDE renders a button and
    POSTs the bootstrap action; the agent calls the ``bootstrap_stdcells`` tool.
    This replaces the old ``python scripts/bootstrap_stdcells.py ...`` hint —
    a command the platform can't run for the user.
    """
    pf = platform or "<platform>"
    return {
        # Names the single registered tool both surfaces invoke (invariant #2,
        # one registry): the agent calls it in the agent loop; the IDE invokes
        # it from the Command Surface. No shell command, no REST drift.
        "action": "bootstrap_stdcells_tool",
        "params": {"platform": platform} if platform else {},
        "label": f"Download {pf} standard-cell simulation models",
    }

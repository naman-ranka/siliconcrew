"""Session templates as BUNDLES (Wave 11, Level 1).

A *template* is a repo-owned bundle on disk — ``examples/<id>/`` holding a small
``template.json`` and a ``workspace/`` snapshot (RTL/spec/tb, sim/synth runs,
``attempt_events.jsonl``, rendered ``conversations/*.md``, manifest). It is NOT a
session and has no owner; the only thing you can do with it is FORK it into a
new user-owned session. Because there is never a template-session to mutate,
immutability needs zero enforcement.

Forking (``fork_from_template``) copies the bundle workspace into a fresh
session and rewrites exactly the fields that would otherwise leak the source's
identity or absolute paths into state a tool consumes:

* ``manifest.json.sessionId`` — carries the SOURCE session id and ``read_manifest``
  won't overwrite a non-empty one, so the fork clears it (reconcile re-seeds the
  fork's id). [A3]
* ``run_meta.json.netlist_path`` — absolute and consumed at read time
  (``run_simulation`` does ``os.path.exists`` on it), so the fork re-derives it
  against the copied run dir. [A2]

Historical evidence (``attempt_events.jsonl``, ``completion.event`` markers,
``docker_*`` log tails) is copied VERBATIM — it is the trajectory the showcase
exists to display, and the copied terminal status + completion markers keep old
runs from re-announcing.

Level 1 is self-host ONLY: in cloud mode the copytree target is invisible to
tools (they read object-storage scratch), so fork HARD-GATES to non-cloud with a
clear message. The hosted gallery is a later wave. [A5]
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional

from src.utils.bundles import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_FILES,
    copytree_guarded,
    redact_host_paths,
    scan_for_secrets,
)
from src.utils.transcript import read_thread_messages, render_transcript, slugify

TEMPLATE_MANIFEST = "template.json"
WORKSPACE_SUBDIR = "workspace"
PROVENANCE_FILE = ".source_template.json"
CONVERSATIONS_SUBDIR = "conversations"


class TemplateNotFound(Exception):
    """Requested template id has no bundle under the examples dir → 404."""


def default_examples_dir() -> str:
    """``<repo-root>/examples`` — resolved from this file's location."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo_root, "examples")


def _examples_dir(examples_dir: Optional[str]) -> str:
    return os.path.abspath(examples_dir) if examples_dir else default_examples_dir()


def _is_cloud_workspace() -> bool:
    """True when the active workspace engine is object-storage-backed (hosted).

    Reads the core settings engine (not a cloud dependency). Any failure is
    treated as self-host so a mis-set environment never blocks local forks.
    """
    try:
        from src.platform_engines.settings import get_settings

        return get_settings().workspace_engine == "cloud"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Listing / preview
# ---------------------------------------------------------------------------


def _load_template_json(bundle_dir: str) -> Optional[dict]:
    path = os.path.join(bundle_dir, TEMPLATE_MANIFEST)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _count_workspace(bundle_dir: str) -> tuple[int, int]:
    """(file_count, run_count) for the card — cheap directory stats."""
    ws = os.path.join(bundle_dir, WORKSPACE_SUBDIR)
    file_count = 0
    for _root, _dirs, files in os.walk(ws):
        file_count += len(files)
    run_count = 0
    for runs_name in ("synth_runs", "sim_runs"):
        runs_root = os.path.join(ws, runs_name)
        if os.path.isdir(runs_root):
            run_count += sum(
                1 for e in os.scandir(runs_root) if e.is_dir()
            )
    return file_count, run_count


def _template_summary(template_id: str, data: dict, bundle_dir: str) -> dict:
    file_count, run_count = _count_workspace(bundle_dir)
    return {
        "id": data.get("id") or template_id,
        "name": data.get("name") or template_id,
        "description": data.get("description") or "",
        "highlights": list(data.get("highlights") or []),
        "top_module": data.get("top_module"),
        "platform": data.get("platform"),
        "source_note": data.get("source_note"),
        "file_count": file_count,
        "run_count": run_count,
    }


def list_templates(examples_dir: Optional[str] = None) -> List[dict]:
    """All valid bundles under the examples dir, sorted by name.

    A directory is a template iff it has a readable ``template.json`` AND a
    ``workspace/`` snapshot. Malformed entries are skipped (never a 500).
    """
    root = _examples_dir(examples_dir)
    if not os.path.isdir(root):
        return []
    out: List[dict] = []
    for entry in os.scandir(root):
        if not entry.is_dir():
            continue
        data = _load_template_json(entry.path)
        if data is None:
            continue
        if not os.path.isdir(os.path.join(entry.path, WORKSPACE_SUBDIR)):
            continue
        out.append(_template_summary(entry.name, data, entry.path))
    out.sort(key=lambda t: (t["name"] or "").lower())
    return out


# Internal bookkeeping files that are real on disk but not design content — kept
# out of the preview file list (A13).
_PREVIEW_HIDDEN = {".sc_binaries.json", PROVENANCE_FILE}


def _shallow_file_preview(ws: str, limit: int = 200) -> List[str]:
    """Workspace-relative file paths for the preview (design files first)."""
    paths: List[str] = []
    for root, dirs, files in os.walk(ws):
        # Skip noisy/heavy internals in the shallow preview.
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for name in files:
            if name in _PREVIEW_HIDDEN:
                continue
            rel = os.path.relpath(os.path.join(root, name), ws).replace(os.sep, "/")
            paths.append(rel)
            if len(paths) >= limit:
                paths.sort()
                return paths
    paths.sort()
    return paths


def get_template(template_id: str, examples_dir: Optional[str] = None) -> dict:
    """Full preview for one bundle: manifest + a shallow file list + conversations.

    Raises :class:`TemplateNotFound` for an unknown/invalid id.
    """
    root = _examples_dir(examples_dir)
    bundle_dir = _safe_bundle_dir(root, template_id)
    data = _load_template_json(bundle_dir)
    ws = os.path.join(bundle_dir, WORKSPACE_SUBDIR)
    if data is None or not os.path.isdir(ws):
        raise TemplateNotFound(template_id)

    summary = _template_summary(template_id, data, bundle_dir)
    files = _shallow_file_preview(ws)
    conv_dir = os.path.join(ws, CONVERSATIONS_SUBDIR)
    conversations: List[str] = []
    if os.path.isdir(conv_dir):
        conversations = sorted(
            f for f in os.listdir(conv_dir) if f.endswith(".md")
        )
    summary["files"] = files
    summary["conversations"] = conversations
    return summary


def _safe_bundle_dir(examples_root: str, template_id: str) -> str:
    """Resolve ``examples_root/<template_id>`` with traversal protection.

    Template ids are single path segments (the REST route enforces this too);
    reject anything that escapes the examples root.
    """
    candidate = os.path.abspath(os.path.join(examples_root, template_id))
    root = os.path.abspath(examples_root)
    if os.path.commonpath([candidate, root]) != root or candidate == root:
        raise TemplateNotFound(template_id)
    return candidate


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def _clear_manifest_session_id(ws: str) -> None:
    """Blank ``manifest.json.sessionId`` so the fork re-seeds its own (A3)."""
    path = os.path.join(ws, "manifest.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    if data.get("sessionId"):
        data["sessionId"] = ""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _iter_run_metas(ws: str):
    """Yield (run_dir, run_meta.json path) for every run under the workspace."""
    for root, _dirs, files in os.walk(ws):
        if "run_meta.json" in files:
            yield root, os.path.join(root, "run_meta.json")


SC_BINARIES_FILE = ".sc_binaries.json"


def _split_binaries_paths(ws: str) -> List[str]:
    """Workspace-relative paths listed in ``.sc_binaries.json`` (empty if none).

    These are the heavy PnR outputs the split moved to GCS; on a self-host clone
    that never fetched them the paths are present in the manifest but absent on
    disk. Fork uses this to keep ``netlist_path`` honest (A15).
    """
    path = os.path.join(ws, SC_BINARIES_FILE)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return [
        e["path"]
        for e in data.get("files", [])
        if isinstance(e, dict) and isinstance(e.get("path"), str)
    ]


def _run_has_split_out_netlist(ws: str, run_dir: str, binaries_paths: List[str]) -> bool:
    """True when a synthesized gate netlist for THIS run is split-out + absent.

    A15: a real bundle keeps ``synth_runs/*/inputs/*.v`` (pre-synthesis RTL) in
    git, and ``_find_netlist`` scans BOTH ``orfs_results`` and ``inputs`` — so a
    binary-less fork would otherwise re-derive ``netlist_path`` to the RTL input,
    claiming a "netlist" that is actually pre-synthesis source (dishonest for
    gate-level sim). When the run's ``.sc_binaries.json`` lists an
    ``orfs_results/**/*.v`` that isn't on disk, the gate netlist was split out
    (not merely never produced), so the fork forces ``netlist_path=None``.
    """
    run_rel = os.path.relpath(run_dir, ws).replace(os.sep, "/")
    prefix = "" if run_rel == "." else run_rel + "/"
    for rel in binaries_paths:
        if prefix and not rel.startswith(prefix):
            continue
        parts = rel.split("/")
        if "orfs_results" in parts[:-1] and parts[-1].lower().endswith(".v"):
            if not os.path.exists(os.path.join(ws, rel.replace("/", os.sep))):
                return True
    return False


def _rewrite_run_meta_netlists(ws: str) -> None:
    """Re-derive ``netlist_path`` in each copied run_meta against the fork's dir.

    ``netlist_path`` is absolute and consumed at read time (post-synth sim does
    ``os.path.exists`` on it), so a copied source path would 404 in the fork.
    The netlist lives inside its own run dir, which was copied intact, so
    ``_find_netlist`` re-derives the fork-local absolute path exactly as the
    original synthesis did (A2). A run with no netlist (failed synth) resolves to
    None, same as it was. A15: a run whose gate netlist was split out to GCS and
    not fetched resolves to None rather than the ``inputs/`` RTL source.
    """
    from src.tools.synthesis_manager import _find_netlist

    binaries_paths = _split_binaries_paths(ws)

    for run_dir, meta_path in _iter_run_metas(ws):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict) or "netlist_path" not in meta:
            continue
        top = meta.get("top_module")
        if binaries_paths and _run_has_split_out_netlist(ws, run_dir, binaries_paths):
            new_netlist = None  # gate netlist split out, not fetched — honest None
        else:
            new_netlist = _find_netlist(run_dir, top) if top else None
        if new_netlist != meta.get("netlist_path"):
            meta["netlist_path"] = new_netlist
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except OSError:
                pass


def _write_provenance(ws: str, template_id: str, name: str) -> dict:
    """Stamp ``.source_template.json`` — read by the workbench provenance chip.

    ``forked_at`` is an AWARE UTC ISO timestamp (never a naive datetime — a naive
    value read back as local time is the timezone sharp edge this repo has paid
    for before). Returns the exact dict written so the caller can persist a
    byte-identical copy to the metadata store (the hosted durable path).
    """
    provenance = {
        "id": template_id,
        "name": name,
        "forked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(os.path.join(ws, PROVENANCE_FILE), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
    return provenance


def read_provenance(ws: str) -> Optional[dict]:
    """Return the fork's ``{id, name, forked_at}`` provenance, or None."""
    path = os.path.join(ws, PROVENANCE_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _allocate_fork_session(session_manager, base_tag: str, user_id) -> str:
    """create_session with a unique tag (A1: create FIRST, into an empty dir).

    Forking the same template twice must not collide, so on FileExistsError we
    retry with a numeric suffix. create_session seeds the fork's own "Chat 1".
    """
    tag = base_tag
    for attempt in range(1, 50):
        try:
            return session_manager.create_session(tag=tag, user_id=user_id)
        except FileExistsError:
            attempt += 1
            tag = f"{base_tag}-{attempt}"
    # Extremely unlikely; fall back to a uuid-suffixed tag.
    import uuid

    return session_manager.create_session(tag=f"{base_tag}-{uuid.uuid4().hex[:8]}", user_id=user_id)


def _rollback_fork(session_manager, provider, session_id: str, user_id) -> None:
    """Undo a failed fork: cloud workspace staging first, then the session row.

    On cloud, ``delete_session`` removes the (empty local) dir + metadata +
    seeded Chat 1 but NOT the object-storage staging — so drop the staged
    scratch + the committed manifest via the provider so no adoptable half-fork
    survives (D7). Best-effort throughout — never mask the original error. Only
    orphaned content-addressed blobs may remain (unreferenced, harmless; GC is
    deferred with run retention).
    """
    if provider is not None:
        delete_ws = getattr(provider, "delete_workspace", None)
        if callable(delete_ws):
            try:
                delete_ws(session_id)
            except Exception:
                pass
    try:
        session_manager.delete_session(session_id, user_id=user_id)
    except Exception:
        pass


def fork_from_template(
    session_manager,
    template_id: str,
    *,
    user_id=None,
    examples_dir: Optional[str] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> str:
    """Fork a bundle into a new user-owned session. Returns the new session id.

    Sequence (A1): ``create_session`` FIRST (empty dir + metadata + seeded Chat
    1), THEN materialize the bundle workspace into it, THEN rewrite the
    identity/path leaks and stamp provenance. The two engine-dependent pieces:

    * **destination** — self-host copies into ``get_workspace_path`` (a real
      local dir); a cloud workspace materializes into the provider's empty
      scratch (``workspace_for``), the path the tools actually read (D5).
    * **materialization** — routed through the :class:`TemplateSource` engine:
      local = today's ``copytree_guarded`` of the bundle ``workspace/`` (behavior
      -identical); gcs = pull the source + binaries archives, guarded post-extract.
      An explicit ``examples_dir`` (self-host / tests) pins a local source.

    On cloud, ``provider.sync`` runs LAST (D5/D7): the manifest is written last
    within sync, so it is the atomic initial commit — any earlier failure leaves
    no adoptable workspace. On ANY failure after the session is created,
    :func:`_rollback_fork` undoes the dir + metadata + seeded chat and, on cloud,
    the staged workspace (A6/D7) so a half-fork never survives.
    """
    # Lazy import: template_source imports this module, so a top-level import
    # would be circular. Local source honors an explicit examples_dir (tests /
    # self-host callers); otherwise the process-wide configured engine.
    from src.platform_engines.template_source import (
        LocalTemplateSource,
        get_template_source,
    )

    source = (
        LocalTemplateSource(examples_dir)
        if examples_dir is not None
        else get_template_source()
    )

    info = source.get(template_id)  # raises TemplateNotFound for an unknown id
    name = info.get("name") or template_id
    template_ref = info.get("id") or template_id
    base_tag = slugify(name, fallback=template_id) or template_id

    cloud = _is_cloud_workspace()
    provider = None
    if cloud:
        from src.platform_engines.workspace_provider import get_workspace_provider

        provider = get_workspace_provider()

    new_session_id = _allocate_fork_session(session_manager, base_tag, user_id)
    try:
        if cloud:
            dst_ws = provider.workspace_for(new_session_id)  # empty scratch (D5)
        else:
            dst_ws = session_manager.get_workspace_path(new_session_id)
        source.materialize(
            template_id, dst_ws, max_bytes=max_bytes, max_files=max_files
        )
        _clear_manifest_session_id(dst_ws)
        _rewrite_run_meta_netlists(dst_ws)
        provenance = _write_provenance(dst_ws, template_ref, name)
        # Durable copy for the "forked from" chip on hosted list endpoints (D8).
        try:
            session_manager.set_source_template(
                new_session_id, json.dumps(provenance), user_id=user_id
            )
        except Exception:
            pass  # the workspace file remains authoritative; store copy is a cache
        if cloud:
            provider.sync(new_session_id)  # atomic initial commit — manifest LAST
    except BaseException:
        _rollback_fork(session_manager, provider, new_session_id, user_id)
        raise
    return new_session_id


# ---------------------------------------------------------------------------
# Export (bundle authoring; the future publish primitive)
# ---------------------------------------------------------------------------


# Compiled build products that are machine-specific (embed the toolchain's
# absolute install paths), useless in a template, and pure weight — dropped from
# an EXPORTED bundle. The waveform (.vcd), logs, and run_meta stay.
_BUILD_ARTIFACT_EXTS = (".out", ".vvp")


def _sanitize_exported_workspace(ws: str, redact_paths: Optional[List[str]] = None) -> None:
    """Strip the author's identity from a workspace about to be committed.

    * Clear ``manifest.json.sessionId`` (source session id).
    * Null every ``run_meta.json.netlist_path`` — it is an ABSOLUTE path into the
      author's machine; the fork re-derives it against the copied run dir.
    * Redact the author's absolute paths (source workspace, home dir) from EVERY
      generated text artifact — run_meta command/log-tail strings AND the actor
      event logs (``attempt_events.jsonl`` / ``attempt_log.json``), whose tool
      arguments/results can echo absolute paths. The fork leaves these verbatim
      as historical evidence in a user's PRIVATE workspace (A2), but a bundle
      bound for a PUBLIC repo must not carry ``C:\\Users\\<name>\\…`` — the
      command SHAPE is the evidence, not the absolute prefix. (The rendered chat
      transcripts are redacted at render time in ``export_session_bundle``.)
    * Drop compiled build artifacts (``*.out``/``*.vvp``) under run dirs.
    * Drop a stale ``.source_template.json`` if this session was itself a fork.
    """
    _clear_manifest_session_id(ws)

    redactions = list(redact_paths or [])

    for _run_dir, meta_path in _iter_run_metas(ws):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        # Redact absolute host paths in the raw JSON text (covers command/tail
        # strings in every separator form: native, JSON-escaped ``\\``, and ``/``).
        raw = redact_host_paths(raw, redactions)
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(meta, dict) and meta.get("netlist_path"):
            meta["netlist_path"] = None
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except OSError:
            pass

    # Actor event logs are copied verbatim (they ARE the trajectory), but their
    # tool arguments/results can carry absolute host paths — redact those too.
    if redactions:
        for log_name in ("attempt_events.jsonl", "attempt_log.json"):
            log_path = os.path.join(ws, log_name)
            if not os.path.isfile(log_path):
                continue
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            redacted = redact_host_paths(text, redactions)
            if redacted != text:
                try:
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write(redacted)
                except OSError:
                    pass

    for runs_name in ("synth_runs", "sim_runs"):
        runs_root = os.path.join(ws, runs_name)
        if not os.path.isdir(runs_root):
            continue
        for root, _dirs, files in os.walk(runs_root):
            for name in files:
                if name.lower().endswith(_BUILD_ARTIFACT_EXTS):
                    try:
                        os.remove(os.path.join(root, name))
                    except OSError:
                        pass

    stale = os.path.join(ws, PROVENANCE_FILE)
    if os.path.isfile(stale):
        try:
            os.remove(stale)
        except OSError:
            pass


def _manifest_top_module(ws: str) -> Optional[str]:
    path = os.path.join(ws, "manifest.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("synthTop") or data.get("simTop")
    except (OSError, json.JSONDecodeError):
        pass
    return None


# The one final GDS a showcase layout viewer renders; everything else under a
# run's ``base/`` with these shapes is a regenerable per-stage checkpoint.
_FINAL_GDS = "6_final.gds"


def _prune_pnr_intermediates(ws: str) -> int:
    """Drop regenerable per-stage PnR checkpoints from a full-flow GDS bundle.

    A completed sky130 run leaves ~35 MB of intermediate OpenDB ``*.odb`` and a
    merged ``6_1_merged.gds`` under ``synth_runs/*/orfs_results/.../base/`` — NO
    viewer reads them (the layout viewer renders ``6_final.gds``; reports read
    ``orfs_reports/*.rpt``; the runs pane reads ``run_meta.json``). Removing them
    shrinks a public GDS bundle from tens of MB to a few, keeping the final GDS,
    netlist, DEF/SDC/SPEF, reports, and logs — the honest tapeout result. Opt-in
    (default off); the run really produced these, this is curation not fabrication.
    Returns the count removed.
    """
    removed = 0
    runs_root = os.path.join(ws, "synth_runs")
    if not os.path.isdir(runs_root):
        return 0
    for dirpath, _dirs, files in os.walk(runs_root):
        for name in files:
            low = name.lower()
            drop = low.endswith(".odb") or (low.endswith(".gds") and low != _FINAL_GDS)
            if drop:
                try:
                    os.remove(os.path.join(dirpath, name))
                    removed += 1
                except OSError:
                    pass
    return removed


@dataclass
class ExportResult:
    template_dir: str
    conversations: List[str]
    secret_warnings: List[str]
    files: int
    bytes: int
    pruned: int = 0


def export_session_bundle(
    session_manager,
    session_id: str,
    out_dir: str,
    *,
    db_path: str,
    user_id=None,
    name: Optional[str] = None,
    description: str = "",
    highlights: Optional[List[str]] = None,
    platform: Optional[str] = None,
    source_note: Optional[str] = None,
    prune_pnr_intermediates: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> ExportResult:
    """Author a bundle from a live session (``examples/<id>/`` layout).

    Copies the session workspace (guarded), renders each chat thread to
    ``conversations/chat-N-<slug>.md`` via the lightweight checkpoint reader,
    sanitizes the author's identity out, and writes a ``template.json`` scaffold
    (the curator fills description/highlights). Secret-looking files are
    surfaced as warnings — never silently shipped, never silently dropped.

    ``prune_pnr_intermediates`` (opt-in) drops the regenerable per-stage PnR
    ``*.odb``/intermediate ``*.gds`` checkpoints so a full-flow GDS bundle is a
    few MB instead of tens — keeping the final GDS, netlist, reports, and logs.

    A hot path this is not: it is an offline authoring utility (also the seed for
    a future publish flow). Self-host only — see ``read_thread_messages``.
    """
    src_ws = session_manager.get_workspace_path(session_id)
    if not os.path.isdir(src_ws):
        raise FileNotFoundError(f"Session workspace not found: {session_id}")

    out_dir = os.path.abspath(out_dir)
    template_id = os.path.basename(out_dir.rstrip(os.sep))
    display_name = name or template_id
    workspace_out = os.path.join(out_dir, WORKSPACE_SUBDIR)

    stats = copytree_guarded(
        src_ws, workspace_out, max_bytes=max_bytes, max_files=max_files, dirs_exist_ok=True
    )
    secret_warnings = scan_for_secrets(workspace_out)
    # The author's absolute paths to scrub from every generated artifact
    # (run_meta, event logs, and — below — the rendered transcripts).
    redactions = [os.path.abspath(src_ws), os.path.expanduser("~")]
    _sanitize_exported_workspace(workspace_out, redact_paths=redactions)
    pruned = _prune_pnr_intermediates(workspace_out) if prune_pnr_intermediates else 0

    # Render each thread's transcript into the exported workspace. list_threads
    # is read-only; a session with no separate threads still has its "Chat 1"
    # (thread_id == session_id) checkpoint.
    import asyncio

    threads = session_manager.list_threads(session_id, user_id=user_id) or []
    if not threads:
        threads = [{"id": session_id, "title": "Chat 1"}]
    conv_dir = os.path.join(workspace_out, CONVERSATIONS_SUBDIR)
    conversations: List[str] = []
    for i, t in enumerate(threads, 1):
        title = t.get("title") or f"Chat {i}"
        try:
            messages = asyncio.run(read_thread_messages(db_path, t["id"]))
        except Exception:
            messages = []
        # Only ship a transcript for a thread that actually holds a conversation.
        # A bundle authored via direct tool calls (no chat) honestly carries no
        # conversations dir rather than a "no conversation recorded" placeholder.
        if not messages:
            continue
        os.makedirs(conv_dir, exist_ok=True)
        md = render_transcript(
            messages, title=title, template_name=display_name, redact_paths=redactions
        )
        fname = f"chat-{i}-{slugify(title, fallback=f'chat-{i}')}.md"
        with open(os.path.join(conv_dir, fname), "w", encoding="utf-8") as f:
            f.write(md)
        conversations.append(fname)

    template = {
        "id": template_id,
        "name": display_name,
        "description": description,
        "highlights": list(highlights or []),
        "top_module": _manifest_top_module(workspace_out),
        "platform": platform,
        "source_note": source_note,
    }
    with open(os.path.join(out_dir, TEMPLATE_MANIFEST), "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)

    return ExportResult(
        template_dir=out_dir,
        conversations=conversations,
        secret_warnings=secret_warnings,
        files=stats.files,
        bytes=stats.bytes,
        pruned=pruned,
    )

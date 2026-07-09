#!/usr/bin/env python3
"""Publish the example bundles to the official templates bucket (operator tool).

The hosted gallery reads ``official/index.json`` + per-bundle archives from a
public GCS bucket (see ``src/platform_engines/template_source.py``). This script
builds and uploads them so an operator can publish/update examples WITHOUT a
backend redeploy. It is offline/admin-only — NOT a service path — so it MAY
import ``google.cloud`` (lazily, inside :func:`main`).

For each bundle it uploads two tar archives and one index:

  * ``bundles/<id>/source``   — the ``workspace/`` SUBTREE (source files only, as
    the split left them: RTL/spec/tb/manifest/run_meta/trajectory + the
    ``.sc_binaries.json`` manifest). No ``template.json`` inside (that is index-
    only). [A9]
  * ``bundles/<id>/binaries`` — exactly the files listed in
    ``workspace/.sc_binaries.json`` at their workspace-relative paths. [D9]
  * ``official/index.json``   — written LAST (atomic publish): the whole gallery,
    with each entry's ``template.json`` fields verbatim + ``file_count``/
    ``run_count``/``files``/``conversations`` computed from the FULL (source +
    binaries) bundle so the hosted cards match the self-host ones. [D4]

Source comes from a git ref (``--ref``, default HEAD) checked out via a detached
worktree (A11); the split-out binaries come from that same ref if still present,
else from ``--binaries-from`` (a pre-split checkout). Auth is ADC /
GOOGLE_APPLICATION_CREDENTIALS, or a service-account file via ``--key``.
``--dry-run`` prints the plan and uploads nothing. Output is deterministic.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

# Repo root on sys.path so ``python scripts/publish_templates.py`` imports src.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.platform_engines.template_source import (  # noqa: E402
    INDEX_KEY,
    OFFICIAL_PREFIX,
    _BINARIES_KEY,
    _SOURCE_KEY,
)
from src.platform_engines.workspace_provider import _tar_dir_to_bytes  # noqa: E402
from src.utils import templates as templates_mod  # noqa: E402

SC_BINARIES_NAME = ".sc_binaries.json"
INDEX_VERSION = 1


# ---------------------------------------------------------------------------
# Bundle staging + index construction (pure; store-injected for tests)
# ---------------------------------------------------------------------------


def discover_bundles(examples_root: str) -> List[str]:
    """Bundle ids under ``examples_root`` (template.json + workspace/), sorted."""
    out: List[str] = []
    if not os.path.isdir(examples_root):
        return out
    for entry in sorted(os.scandir(examples_root), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        if not os.path.isfile(os.path.join(entry.path, templates_mod.TEMPLATE_MANIFEST)):
            continue
        if not os.path.isdir(os.path.join(entry.path, templates_mod.WORKSPACE_SUBDIR)):
            continue
        out.append(entry.name)
    return out


def _read_binaries_list(ws: str) -> List[str]:
    """Workspace-relative paths from ``.sc_binaries.json`` (empty if none)."""
    path = os.path.join(ws, SC_BINARIES_NAME)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [e["path"] for e in data.get("files", [])]


def _archive_stats(local_dir: str) -> Tuple[int, str]:
    """(bytes, sha256) of the tar.gz for ``local_dir`` — advisory only (A4).

    Uses the same tarrer the object store uses; gzip embeds an mtime so the exact
    bytes are not reproducible, hence the index treats these as advisory.
    """
    data = _tar_dir_to_bytes(local_dir)
    return len(data), hashlib.sha256(data).hexdigest()


def _build_binaries_dir(binaries_ws: str, rels: List[str], out_dir: str) -> List[str]:
    """Copy each listed binary into ``out_dir`` at its rel path. Returns missing."""
    missing: List[str] = []
    for rel in rels:
        src = os.path.join(binaries_ws, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            missing.append(rel)
            continue
        dst = os.path.join(out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return missing


def _build_merged_bundle(source_ws: str, binaries_dir: str, template_json_src: str, merged_root: str, template_id: str) -> None:
    """Reconstruct the FULL bundle (source + binaries) so the existing
    ``templates.get_template`` computes the index preview fields identically to
    the self-host gallery (parity by construction)."""
    merged_ws = os.path.join(merged_root, template_id, templates_mod.WORKSPACE_SUBDIR)
    shutil.copytree(source_ws, merged_ws)
    if os.path.isdir(binaries_dir):
        shutil.copytree(binaries_dir, merged_ws, dirs_exist_ok=True)
    shutil.copy2(template_json_src, os.path.join(merged_root, template_id, templates_mod.TEMPLATE_MANIFEST))


def build_index_entry(
    examples_root: str,
    binaries_ws_root: str,
    template_id: str,
    scratch: str,
) -> Tuple[dict, str, str]:
    """Build the index entry + return (entry, source_ws_dir, binaries_dir).

    Raises ``FileNotFoundError`` if any listed binary is absent under
    ``binaries_ws_root`` (an incomplete publish must fail loudly, not silently
    ship a bundle a hosted fork can't complete — A6).
    """
    bundle_dir = os.path.join(examples_root, template_id)
    source_ws = os.path.join(bundle_dir, templates_mod.WORKSPACE_SUBDIR)
    template_json = os.path.join(bundle_dir, templates_mod.TEMPLATE_MANIFEST)
    rels = _read_binaries_list(source_ws)

    binaries_ws = os.path.join(binaries_ws_root, template_id, templates_mod.WORKSPACE_SUBDIR)
    binaries_dir = os.path.join(scratch, f"bin_{template_id}")
    os.makedirs(binaries_dir, exist_ok=True)
    missing = _build_binaries_dir(binaries_ws, rels, binaries_dir)
    if missing:
        raise FileNotFoundError(
            f"bundle '{template_id}': {len(missing)} listed binary file(s) not found under "
            f"{binaries_ws} (use --binaries-from a pre-split checkout): {missing[:3]}..."
        )

    # Preview fields from the FULL bundle (reuse the tested local logic).
    merged_root = os.path.join(scratch, f"merged_{template_id}")
    _build_merged_bundle(source_ws, binaries_dir, template_json, merged_root, template_id)
    preview = templates_mod.get_template(template_id, merged_root)

    src_bytes, src_sha = _archive_stats(source_ws)
    bin_bytes, bin_sha = _archive_stats(binaries_dir)
    entry = {
        # template.json fields verbatim + computed preview (D4).
        "id": preview["id"],
        "name": preview["name"],
        "description": preview["description"],
        "highlights": preview["highlights"],
        "top_module": preview["top_module"],
        "platform": preview["platform"],
        "source_note": preview["source_note"],
        "file_count": preview["file_count"],
        "run_count": preview["run_count"],
        "files": preview["files"],
        "conversations": preview["conversations"],
        "tier": "official",
        "source": {"key": _SOURCE_KEY.format(id=template_id), "bytes": src_bytes, "sha256": src_sha},
        "binaries": {"key": _BINARIES_KEY.format(id=template_id), "bytes": bin_bytes, "sha256": bin_sha},
    }
    return entry, source_ws, binaries_dir


def publish(
    store,
    examples_root: str,
    binaries_ws_root: str,
    ids: List[str],
    *,
    dry_run: bool = False,
    log=print,
) -> dict:
    """Build every bundle, upload archives, then write ``index.json`` LAST.

    Returns the index dict. In ``dry_run`` nothing is uploaded (the index is
    returned for inspection). The store is injected so tests drive an in-memory
    fake with no live GCS / google-cloud import.
    """
    scratch = tempfile.mkdtemp(prefix="sc-publish-")
    try:
        entries: List[dict] = []
        for tid in ids:
            entry, source_ws, binaries_dir = build_index_entry(
                examples_root, binaries_ws_root, tid, scratch
            )
            src_key = _SOURCE_KEY.format(id=tid)
            bin_key = _BINARIES_KEY.format(id=tid)
            log(
                f"[{tid}] source={entry['source']['bytes']}B "
                f"binaries={entry['binaries']['bytes']}B files={entry['file_count']} "
                f"runs={entry['run_count']} -> {OFFICIAL_PREFIX}/{src_key}.tar.gz, "
                f"{OFFICIAL_PREFIX}/{bin_key}.tar.gz"
            )
            if not dry_run:
                store.put_tree(src_key, source_ws)
                store.put_tree(bin_key, binaries_dir)
            entries.append(entry)

        # Deterministic, name-sorted (matches the local list_templates ordering).
        entries.sort(key=lambda e: ((e.get("name") or "").lower(), e["id"]))
        index = {
            "version": INDEX_VERSION,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "templates": entries,
        }
        log(f"index: {len(entries)} template(s) -> {OFFICIAL_PREFIX}/{INDEX_KEY}"
            + (" (dry-run, not written)" if dry_run else " (written LAST)"))
        if not dry_run:
            index_path = os.path.join(scratch, "index.json")
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2, sort_keys=True)
            store.put_file(INDEX_KEY, index_path)  # atomic publish point
        return index
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI — git worktree checkout of --ref + GCS client (google.cloud lazy here)
# ---------------------------------------------------------------------------


def _git_worktree_add(ref: str) -> str:
    tmp = tempfile.mkdtemp(prefix="sc-publish-ref-")
    subprocess.run(["git", "worktree", "add", "--detach", tmp, ref], check=True)
    return tmp


def _git_worktree_remove(path: str) -> None:
    try:
        subprocess.run(["git", "worktree", "remove", "--force", path], check=False)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Publish example bundles to the templates bucket.")
    ap.add_argument("--bucket", required=True, help="Target GCS bucket (e.g. <project>-siliconcrew-templates).")
    ap.add_argument("--ref", default="HEAD", help="Git ref for the bundle SOURCE (default HEAD).")
    ap.add_argument("--binaries-from", default=None,
                    help="Repo root of a checkout that still has the split-out binaries "
                         "(default: the --ref worktree itself).")
    ap.add_argument("--only", nargs="*", default=None, help="Publish only these bundle ids.")
    ap.add_argument("--key", default=None, help="Service-account JSON key file (else ADC / GOOGLE_APPLICATION_CREDENTIALS).")
    ap.add_argument("--dry-run", action="store_true", help="Print the plan; upload nothing.")
    args = ap.parse_args(argv)

    worktree = _git_worktree_add(args.ref)
    try:
        examples_root = os.path.join(worktree, "examples")
        binaries_ws_root = (
            os.path.join(args.binaries_from, "examples") if args.binaries_from else examples_root
        )
        ids = args.only or discover_bundles(examples_root)
        if not ids:
            print("No bundles found to publish.", file=sys.stderr)
            return 1

        store = None
        if not args.dry_run:
            from google.cloud import storage  # lazy: operator-only path
            from src.platform_engines.workspace_provider import GcsObjectStore

            if args.key:
                client = storage.Client.from_service_account_json(args.key)
            else:
                client = storage.Client()  # ADC / GOOGLE_APPLICATION_CREDENTIALS
            store = GcsObjectStore(bucket=args.bucket, prefix=OFFICIAL_PREFIX, client=client)

        publish(store, examples_root, binaries_ws_root, ids, dry_run=args.dry_run)
        return 0
    finally:
        _git_worktree_remove(worktree)


if __name__ == "__main__":
    raise SystemExit(main())

"""Bundle plumbing shared by template fork (read → new session) and bundle
export (session → curated example).

The one net-new primitive here is a *guarded* recursive copy: fork and export
both duplicate a whole workspace tree, and an unbounded ``shutil.copytree`` on a
workspace that happens to carry a multi-GB GDS (or a symlink loop) would fill
the disk or hang. ``copytree_guarded`` counts bytes + files as it walks and
aborts — cleaning up the partial destination — the moment either ceiling is
crossed, so a bad source can never half-fill the disk and leave a partial
workspace behind (Wave 11 A6).

Kept dependency-free (stdlib only) so self-host never pulls a cloud package to
fork an example — the engine-selection invariant applies to bundles too.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


# Level-1 bundles are LIGHT by contract (small designs; heavy GDS is a later
# hosted level). These ceilings are generous for real RTL + sim/synth runs yet
# still refuse a runaway copy. Callers may override for export authoring.
DEFAULT_MAX_BYTES = 512 * 1024 * 1024   # 512 MiB
DEFAULT_MAX_FILES = 20_000


class BundleTooLarge(Exception):
    """A guarded copy crossed its byte or file-count ceiling and was aborted."""


@dataclass(frozen=True)
class CopyStats:
    files: int
    bytes: int


def copytree_guarded(
    src: str,
    dst: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
    dirs_exist_ok: bool = True,
) -> CopyStats:
    """Copy ``src`` → ``dst`` recursively, aborting past a byte/file ceiling.

    Symlinks are copied as links (never followed) so a symlink loop cannot be
    walked into an infinite copy, and a link pointing outside the tree is not
    silently materialized. On ANY failure — a crossed ceiling or an OS error —
    the (partial) destination this call created is removed before re-raising, so
    the caller never has to reason about a half-written workspace.

    Returns the (files, bytes) actually copied on success.
    """
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        raise FileNotFoundError(f"Source is not a directory: {src}")

    # Track whether we created dst so cleanup only removes what THIS call made
    # (never a caller's pre-existing directory when dirs_exist_ok=True).
    created_dst = not os.path.exists(dst)
    n_files = 0
    n_bytes = 0
    try:
        os.makedirs(dst, exist_ok=dirs_exist_ok)
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            target_root = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(target_root, exist_ok=True)
            for name in files:
                s_path = os.path.join(root, name)
                d_path = os.path.join(target_root, name)
                if os.path.islink(s_path):
                    linkto = os.readlink(s_path)
                    if os.path.lexists(d_path):
                        os.remove(d_path)
                    os.symlink(linkto, d_path)
                    n_files += 1
                    continue
                try:
                    size = os.path.getsize(s_path)
                except OSError:
                    size = 0
                n_files += 1
                n_bytes += size
                if n_files > max_files:
                    raise BundleTooLarge(
                        f"copy exceeded file-count ceiling ({max_files}) under {src}"
                    )
                if n_bytes > max_bytes:
                    raise BundleTooLarge(
                        f"copy exceeded size ceiling ({max_bytes} bytes) under {src}"
                    )
                # copy2 preserves mtimes — deliberate: run-dir liveness/adoption
                # logic elsewhere reasons about mtimes, and a fork must present
                # the same timestamps the original run wrote (Wave 11 relies on
                # copied completion markers + terminal status, not fresh mtimes).
                shutil.copy2(s_path, d_path)
        return CopyStats(files=n_files, bytes=n_bytes)
    except BaseException:
        # Undo a partial copy so a failed fork/export leaves no debris.
        if created_dst and os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        raise


# Filenames / substrings that most often hold real secrets. Export SCRUB-WARNS
# (never silently ships, never silently drops) so a curator sees the risk before
# committing a bundle to a public repo. Enforcement (block/strip) is a later
# hosted level — here we only surface.
_SECRET_NAME_HINTS = (
    ".env",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credentials",
    "secrets",
    ".npmrc",
    ".pypirc",
    "service-account",
    "gcp-key",
    ".p12",
    ".pfx",
)


def scan_for_secrets(root: str) -> list[str]:
    """Return workspace-relative paths whose NAME looks secret-bearing.

    Name-based only (fast, no content parse) — a warning list for the curator,
    not a guarantee. Case-insensitive substring match on the basename.
    """
    hits: list[str] = []
    root = os.path.abspath(root)
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            low = name.lower()
            if any(h in low for h in _SECRET_NAME_HINTS):
                hits.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return sorted(hits)

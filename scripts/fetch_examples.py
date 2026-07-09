#!/usr/bin/env python
"""Fetch the heavy example binaries split out by ``split_bundle_binaries.py``.

    python -m scripts.fetch_examples                 # all published bundles
    python -m scripts.fetch_examples --bundle simon128
    make fetch-bundles

For every ``examples/<id>`` that carries a ``workspace/.sc_binaries.json``
manifest, this downloads ``official/bundles/<id>/binaries.tar.gz`` from the
public templates bucket, extracts it into ``workspace/`` (path-traversal
guarded), and verifies EVERY listed file against its recorded sha256. The
per-file verify — not the archive hash — is what makes this correct and
idempotent: a bundle whose listed files are all present and matching is skipped
without a download.

Honest states: a bundle whose archive is not published yet (HTTP 404 / missing)
is reported and skipped; the run still exits 0 unless ``--strict``. A corrupt
download (extracted file fails its sha256) is always a hard error — that is
integrity, not "not published".

STDLIB ONLY — no ``google-cloud-*``, no auth, no new dependency. Self-host must
never need a cloud SDK to obtain public template binaries (sacred constraint).
The bucket is public-read; the URL scheme is plain HTTPS over ``urllib``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

WORKSPACE_SUBDIR = "workspace"
SC_BINARIES_NAME = ".sc_binaries.json"

# The official public templates bucket. NOTE: the terraform bucket name is
# provisioned in Item 2 (`<project>-siliconcrew-templates`, public objectViewer);
# until then this constant is the single source of truth for the published URL.
# Override with --base-url or $SILICONCREW_TEMPLATES_BASE_URL.
DEFAULT_BASE_URL = "https://storage.googleapis.com/siliconcrew-siliconcrew-templates"
BASE_URL_ENV = "SILICONCREW_TEMPLATES_BASE_URL"

_DOWNLOAD_TIMEOUT_SEC = 120


class NotPublished(Exception):
    """The bundle's binaries archive is not published (404 / missing object)."""


class VerifyError(Exception):
    """An extracted file failed its recorded sha256 — a corrupt download."""


def binaries_url(base_url: str, template_id: str) -> str:
    """Public URL of a bundle's binaries archive (see A3: ``.tar.gz`` naming)."""
    return f"{base_url.rstrip('/')}/official/bundles/{template_id}/binaries.tar.gz"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(ws: str) -> Optional[dict]:
    import json

    path = os.path.join(ws, SC_BINARIES_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None


def _missing_or_mismatched(ws: str, files: List[dict]) -> List[str]:
    """Listed paths that are absent or whose sha256 differs on disk."""
    bad: List[str] = []
    for entry in files:
        abs_path = os.path.join(ws, entry["path"].replace("/", os.sep))
        if not os.path.isfile(abs_path):
            bad.append(entry["path"])
            continue
        if _sha256(abs_path) != entry.get("sha256"):
            bad.append(entry["path"])
    return bad


def _download(url: str) -> bytes:
    """Fetch ``url`` fully. Raise :class:`NotPublished` on 404 / missing object."""
    try:
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SEC) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotPublished(url) from e
        raise
    except urllib.error.URLError as e:
        # file:// for a missing path surfaces FileNotFoundError inside URLError.
        if isinstance(e.reason, FileNotFoundError):
            raise NotPublished(url) from e
        raise


def _safe_extract(tar: tarfile.TarFile, dest: str) -> None:
    """Extract guarding against path traversal (CVE-2007-4559 class)."""
    dest_real = os.path.realpath(dest)
    members = tar.getmembers()
    for m in members:
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == dest_real or target.startswith(dest_real + os.sep)):
            raise ValueError(f"Refusing path-traversal tar member: {m.name}")
    tar.extractall(dest, members=members)


def fetch_bundle(bundle_dir: str, base_url: str) -> str:
    """Fetch + verify one bundle's binaries. Returns a status string.

    ``"no-manifest"`` (nothing to fetch), ``"up-to-date"`` (idempotent skip),
    ``"fetched"`` (downloaded + verified), or raises :class:`NotPublished` /
    :class:`VerifyError`.
    """
    template_id = os.path.basename(bundle_dir.rstrip(os.sep))
    ws = os.path.join(bundle_dir, WORKSPACE_SUBDIR)
    manifest = load_manifest(ws)
    if not manifest:
        return "no-manifest"
    files = manifest.get("files") or []
    if not files:
        return "up-to-date"
    if not _missing_or_mismatched(ws, files):
        return "up-to-date"

    data = _download(binaries_url(base_url, template_id))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        _safe_extract(tar, ws)

    bad = _missing_or_mismatched(ws, files)
    if bad:
        raise VerifyError(
            f"{template_id}: {len(bad)} file(s) failed sha256 verify after extract: "
            + ", ".join(bad[:5])
            + (" …" if len(bad) > 5 else "")
        )
    return "fetched"


def _iter_bundles(examples_dir: str, only: Optional[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for entry in sorted(os.scandir(examples_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        if only and entry.name != only:
            continue
        out.append((entry.name, entry.path))
    return out


def _default_examples_dir() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "examples")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch example binaries from the public templates bucket (stdlib only)."
    )
    parser.add_argument("--examples-dir", default=_default_examples_dir(), help="Bundles root (default: ./examples).")
    parser.add_argument("--bundle", default=None, help="Only this bundle id (default: all).")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL),
        help=f"Templates base URL (default: ${BASE_URL_ENV} or the official bucket).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any bundle's archive is not published yet.",
    )
    args = parser.parse_args(argv)

    examples_dir = os.path.abspath(args.examples_dir)
    if not os.path.isdir(examples_dir):
        print(f"error: examples dir not found: {examples_dir}", file=sys.stderr)
        return 2

    fetched = up_to_date = not_published = 0
    corrupt = 0
    for name, bundle_dir in _iter_bundles(examples_dir, args.bundle):
        try:
            status = fetch_bundle(bundle_dir, args.base_url)
        except NotPublished:
            not_published += 1
            print(f"{name}: not published yet (skipped)")
            continue
        except VerifyError as e:
            corrupt += 1
            print(f"error: {e}", file=sys.stderr)
            continue
        if status == "no-manifest":
            continue
        if status == "up-to-date":
            up_to_date += 1
            print(f"{name}: up to date")
        else:
            fetched += 1
            print(f"{name}: fetched + verified")

    print(
        f"\nDone: {fetched} fetched, {up_to_date} up to date, "
        f"{not_published} not published, {corrupt} corrupt."
    )
    if corrupt:
        return 1
    if not_published and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

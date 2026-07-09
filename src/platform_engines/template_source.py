"""Template source engine — local ``examples/`` dir vs a GCS bucket index.

The template gallery has the same self-host/hosted split as everything else
(the sacred engine-selection idiom, ``get_workspace_provider``): self-host reads
the repo-owned bundles under ``examples/`` and never needs a cloud dependency; a
hosted deployment reads a small ``index.json`` object from a public GCS bucket
and fetches per-bundle archives on fork. One factory chooses which, ONCE, from
settings — call sites depend only on the :class:`TemplateSource` protocol.

Why a dynamic GCS index at all: baking bundles into the backend image forces a
commit → image rebuild → redeploy to publish or update an example. Reading the
gallery from a bucket lets an operator publish by uploading (see
``scripts/publish_templates.py``) with no redeploy. The index is ONE small
object listing every template plus the preview metadata the cards need
(``file_count``/``run_count``/``files``/``conversations`` — a hosted instance has
no local workspace to walk, so those are computed at publish time and persisted).

Honest offline (invariant 4): a store outage must never masquerade as an empty
gallery. :class:`GcsTemplateSource` keeps the last good index in an in-process
TTL cache and, when a fresh read fails, serves that cache until it expires — then
raises :class:`TemplateStoreUnavailable`, which the REST layer maps to a 503
"unable to connect", NEVER an empty 200. A brand-new instance with no cache and a
dead store raises immediately.

All ``google-cloud-*`` imports stay lazy inside :class:`GcsObjectStore` (this
module imports only the local provider module), so self-host runs with the cloud
SDK absent.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from typing import List, Optional, Protocol

from src.platform_engines.workspace_provider import GcsObjectStore
from src.utils import templates as templates_mod
from src.utils.bundles import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_FILES,
    BundleTooLarge,
    copytree_guarded,
)
from src.utils.templates import TemplateNotFound

logger = logging.getLogger(__name__)

# Suffix-less, store-relative keys (A3): ``GcsObjectStore`` appends ``.tar.gz``
# and prepends the ``official`` prefix, so ``bundles/<id>/source`` addresses
# ``official/bundles/<id>/source.tar.gz`` in the bucket. The index is a raw
# object (put_file / get_file), not a tar blob.
INDEX_KEY = "index.json"
_SOURCE_KEY = "bundles/{id}/source"
_BINARIES_KEY = "bundles/{id}/binaries"

# The bucket prefix that isolates the (admin-write) official gallery from a
# future ``community/`` space — see the intent doc §6.
OFFICIAL_PREFIX = "official"

# Last-good staleness window: within this many seconds of the last SUCCESSFUL
# index read, a failed fresh read serves the cached copy; past it, we 503 (A14 —
# the staleness contract is intended, not accidental).
_DEFAULT_TTL_SECONDS = 60.0


class TemplateStoreUnavailable(Exception):
    """The template store cannot be read right now → surfaced as a 503.

    Distinct from :class:`TemplateNotFound` (a valid store that has no such id →
    404). NEVER swallowed into an empty list: an unreachable gallery must read as
    "unable to connect", not "no templates" (invariant 4).
    """


class TemplateSource(Protocol):
    """Read the gallery + materialize a bundle into a session workspace."""

    def list(self) -> List[dict]: ...
    def get(self, template_id: str) -> dict: ...
    def materialize(
        self,
        template_id: str,
        dst_dir: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None: ...


class LocalTemplateSource:
    """Self-host source — the repo-owned bundles under ``examples/``.

    A thin delegation to the existing ``templates`` module so behavior is
    byte-identical to today: ``list``/``get`` are its listing/preview, and
    ``materialize`` is the same ``copytree_guarded`` copy of the bundle's
    ``workspace/`` subtree that ``fork_from_template`` has always done. Stateless
    and cloud-free.
    """

    def __init__(self, examples_dir: Optional[str] = None):
        # Resolved lazily on every call (not captured here) so a test that
        # monkeypatches ``default_examples_dir`` after construction still wins.
        self._examples_dir = examples_dir

    def list(self) -> List[dict]:
        return templates_mod.list_templates(self._examples_dir)

    def get(self, template_id: str) -> dict:
        return templates_mod.get_template(template_id, self._examples_dir)

    def materialize(
        self,
        template_id: str,
        dst_dir: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        root = templates_mod._examples_dir(self._examples_dir)
        bundle_dir = templates_mod._safe_bundle_dir(root, template_id)  # raises TemplateNotFound
        src_ws = os.path.join(bundle_dir, templates_mod.WORKSPACE_SUBDIR)
        if not os.path.isdir(src_ws):
            raise TemplateNotFound(template_id)
        copytree_guarded(
            src_ws, dst_dir, max_bytes=max_bytes, max_files=max_files, dirs_exist_ok=True
        )


class GcsTemplateSource:
    """Hosted source — a GCS bucket holding ``official/index.json`` + archives.

    ``list``/``get`` read the single index object (via the store's raw
    ``get_file``) and serve it through a last-good TTL cache: on a fresh-read
    failure the cache is served until it expires, then :class:`TemplateStoreUnavailable`
    is raised (never an empty list). ``materialize`` pulls the two per-bundle tar
    archives (source + binaries) into the destination, then enforces the fork's
    byte/file ceilings post-extract (``get_tree`` has no size guard of its own,
    unlike ``copytree_guarded``). A gcs source PROMISES binaries (the index lists
    them), so a missing binaries archive is all-or-nothing failure (A6), while a
    missing source archive is a plain :class:`TemplateNotFound`.

    The store's ``google-cloud-storage`` import is lazy; constructing this source
    imports nothing cloud-side.
    """

    def __init__(self, bucket: str, ttl_seconds: float = _DEFAULT_TTL_SECONDS, store=None):
        self._store = store if store is not None else GcsObjectStore(
            bucket=bucket, prefix=OFFICIAL_PREFIX
        )
        self._ttl = ttl_seconds
        self._cache: Optional[dict] = None       # last good parsed index
        self._cache_time: float = 0.0            # monotonic time of that read

    # -- index reading --------------------------------------------------------

    def _fetch_index(self) -> Optional[dict]:
        """Read + parse ``index.json``, or None on any absence/parse failure.

        Uses a unique temp path so concurrent gallery reads never collide on one
        scratch file. Returns None (rather than raising) so the caller applies
        the uniform last-good/stale policy for every failure shape.
        """
        tmp = os.path.join(
            tempfile.gettempdir(), f".sc_templates_index.{uuid.uuid4().hex}.json"
        )
        try:
            if not self._store.get_file(INDEX_KEY, tmp):
                return None
            with open(tmp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
                return None
            return data
        except Exception:
            return None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _load_index(self) -> dict:
        """Fresh index, or the last-good cache within TTL, or a 503.

        Every call attempts a fresh read (so a publish shows up immediately). A
        failed read falls back to the cached copy only while it is younger than
        the TTL; with no (or an expired) cache it raises — an unreachable gallery
        is honest, never fake-empty.
        """
        now = time.monotonic()
        data = self._fetch_index()
        if data is not None:
            self._cache = data
            self._cache_time = now
            return data
        if self._cache is not None and (now - self._cache_time) < self._ttl:
            return self._cache
        raise TemplateStoreUnavailable("template index is unreachable")

    def list(self) -> List[dict]:
        return list(self._load_index().get("templates", []))

    def get(self, template_id: str) -> dict:
        for entry in self._load_index().get("templates", []):
            if entry.get("id") == template_id:
                return entry
        raise TemplateNotFound(template_id)

    # -- materialization ------------------------------------------------------

    def materialize(
        self,
        template_id: str,
        dst_dir: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        source_key = _SOURCE_KEY.format(id=template_id)
        binaries_key = _BINARIES_KEY.format(id=template_id)

        # get_tree silently yields an empty dir for an absent blob, so presence
        # must be checked explicitly BEFORE extracting (exists() checks the
        # ``.tar.gz`` spelling of a suffix-less key).
        if not self._store.exists(source_key):
            raise TemplateNotFound(template_id)
        if not self._store.exists(binaries_key):
            # A6: a gcs source promised binaries (the index lists them) — a
            # missing archive is an incomplete publish, not honest degradation.
            raise TemplateStoreUnavailable(
                f"binaries archive missing for template '{template_id}'"
            )

        os.makedirs(dst_dir, exist_ok=True)
        self._store.get_tree(source_key, dst_dir)
        self._store.get_tree(binaries_key, dst_dir)
        _enforce_ceiling(dst_dir, max_bytes=max_bytes, max_files=max_files)


def _enforce_ceiling(root: str, *, max_bytes: int, max_files: int) -> None:
    """Net-new post-extract guard (A9): ``get_tree`` has no ceiling of its own.

    Mirrors ``copytree_guarded`` semantics — abort past the byte or file count
    limit — so a runaway archive can never fill the fork's disk. The caller rolls
    back the destination on the raised :class:`BundleTooLarge`.
    """
    n_files = 0
    n_bytes = 0
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                n_files += 1
                continue
            try:
                n_bytes += os.path.getsize(full)
            except OSError:
                pass
            n_files += 1
            if n_files > max_files:
                raise BundleTooLarge(
                    f"materialized bundle exceeded file-count ceiling ({max_files})"
                )
            if n_bytes > max_bytes:
                raise BundleTooLarge(
                    f"materialized bundle exceeded size ceiling ({max_bytes} bytes)"
                )


# ---------------------------------------------------------------------------
# Factory — chosen once by settings (mirrors get_workspace_provider).
# ---------------------------------------------------------------------------

_SOURCE = None
_LOGGED_EMPTY_BUCKET = False


def get_template_source():
    """Return the process-wide template source selected by platform settings.

    ``templates_engine == "gcs"`` builds a :class:`GcsTemplateSource` against
    ``templates_bucket``; anything else is the self-host :class:`LocalTemplateSource`.
    An engine of ``gcs`` with no bucket configured raises
    :class:`TemplateStoreUnavailable` at first use (surfaced as an honest 503,
    logged loudly once) — the same "fail at the engine builder, not silently"
    posture as the postgres guard. Not cached in that error case, so a later
    correct config still builds cleanly.
    """
    global _SOURCE, _LOGGED_EMPTY_BUCKET
    if _SOURCE is not None:
        return _SOURCE

    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if settings.templates_engine == "gcs":
        if not settings.templates_bucket:
            if not _LOGGED_EMPTY_BUCKET:
                logger.error(
                    "TEMPLATES_ENGINE=gcs but TEMPLATES_BUCKET is empty — the "
                    "template gallery cannot be served (503) until the bucket is set."
                )
                _LOGGED_EMPTY_BUCKET = True
            raise TemplateStoreUnavailable("TEMPLATES_BUCKET is not configured")
        _SOURCE = GcsTemplateSource(settings.templates_bucket)
    else:
        _SOURCE = LocalTemplateSource()
    return _SOURCE


def set_template_source(source) -> None:
    """Override the process-wide template source (tests / explicit wiring).

    Pass ``None`` to reset so the next :func:`get_template_source` rebuilds from
    current settings (test hygiene — mirrors ``set_workspace_provider``).
    """
    global _SOURCE
    _SOURCE = source

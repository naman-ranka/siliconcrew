"""Where a user's OWN skills live — the second layer's storage, and only that.

The layering rules (a user skill replaces a built-in of the same name; a name
in a small list is off; never auto-merge) are ONE piece of code in
``src.utils.skills``. This module exists so that code never learns which
deployment it is running in: it asks for a local directory holding
``<name>/SKILL.md`` files plus a small ``skills.json``, and gets one. Self-host
that directory IS the user's folder; hosted it is a scratch copy of the owner's
object-storage tree, staged on entry and pushed back on a clean write. The
merge therefore reads the same bytes from the same kind of path in both modes —
"identical logic, different storage" is a property of the seam, not a promise
in a comment.

Tenancy. The owner is a parameter, never an ambient default: every call names
the owner whose layer it wants, and the hosted key is derived from that owner id
alone (``skills/<sha256(owner)>``). There is no listing across owners and no
route that accepts an owner from a caller — the only owner any request can name
is the one its identity resolved to. Nothing is cached in this process, on
purpose: a module-level cache keyed by a bare id is exactly the cross-workspace
collision CLAUDE.md warns about, and here it would be a cross-TENANT one — user
A's skills are INSTRUCTIONS that would run with user B's tool credentials. The
cost of that choice is one small object read per composed prompt in hosted, and
that is the right trade.

Self-host must never need a cloud dependency: the ``google-cloud-storage``
import lives inside ``GcsObjectStore`` (workspace_provider), which this module
only touches on the hosted branch.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Iterator, Optional, Protocol

#: Per-owner state that is not a skill file: which names are off, and which
#: built-in each replacement was forked from. One small JSON beside the skill
#: directories, so the whole layer is a folder a self-host user can read, edit,
#: copy or delete with a file manager.
CONFIG_FILENAME = "skills.json"


def owner_key(owner: Optional[str]) -> str:
    """The storage segment for ``owner`` — a hash, never the id itself.

    Hashing keeps tenant ids out of bucket paths and makes traversal
    impossible by construction (the segment is always 32 hex characters). It
    costs an operator the ability to eyeball whose tree is whose; tenancy wins
    that trade.
    """
    return hashlib.sha256((owner or "").encode("utf-8")).hexdigest()[:32]


def read_config(root: Optional[Path]) -> dict:
    """``{"disabled": [...], "forked": {name: sha}}`` — never raises.

    A corrupt or hand-mangled config must not take the agent down: an
    unreadable file reads as "nothing disabled, nothing forked", which is the
    same state as a fresh install. The one thing it may not do is silently
    disable something.
    """
    if root is None:
        return {"disabled": [], "forked": {}}
    path = Path(root) / CONFIG_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"disabled": [], "forked": {}}
    if not isinstance(data, dict):
        return {"disabled": [], "forked": {}}
    disabled = data.get("disabled")
    forked = data.get("forked")
    return {
        "disabled": [n for n in disabled if isinstance(n, str)] if isinstance(disabled, list) else [],
        "forked": {k: v for k, v in forked.items() if isinstance(k, str) and isinstance(v, str)}
        if isinstance(forked, dict) else {},
    }


def write_config(root: Path, config: dict) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILENAME).write_text(
        json.dumps(
            {
                "disabled": sorted(set(config.get("disabled") or [])),
                "forked": dict(config.get("forked") or {}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class UserSkillStore(Protocol):
    """Hand out a local directory for one owner's layer, read or write.

    ``open`` yields ``None`` when the owner has no layer at all — the common
    case, and the one that must cost nothing. ``edit`` always yields a real
    directory and persists it when the block exits cleanly.
    """

    def open(self, owner: Optional[str]) -> ContextManager[Optional[Path]]:  # pragma: no cover - protocol
        ...

    def edit(self, owner: Optional[str]) -> ContextManager[Path]:  # pragma: no cover - protocol
        ...


class LocalUserSkillStore:
    """Self-host: a folder on disk, and that folder is the storage.

    ``open`` and ``edit`` yield the same path — there is nothing to stage and
    nothing to push, so a user editing ``SKILL.md`` in their own editor and a
    user editing it on the Skills page are doing the same thing to the same
    bytes.
    """

    def __init__(self, base: Path):
        self._base = Path(base)

    def root_for(self, owner: Optional[str]) -> Path:
        # One local user means one folder: no owner segment to walk past. A
        # local install running WITH tenancy (dev, tests) still separates
        # owners, so the hosted-shaped case is exercised by the same code.
        return self._base if owner is None else self._base / owner_key(owner)

    @contextmanager
    def open(self, owner: Optional[str]) -> Iterator[Optional[Path]]:
        root = self.root_for(owner)
        yield root if root.is_dir() else None

    @contextmanager
    def edit(self, owner: Optional[str]) -> Iterator[Path]:
        root = self.root_for(owner)
        root.mkdir(parents=True, exist_ok=True)
        yield root


class ObjectUserSkillStore:
    """Hosted: the owner's layer is one small tree in object storage.

    Staged into a private temp directory per call and deleted after. That is
    deliberately the least clever thing that works: no scratch reuse, no
    generation cache, no lock — a request reads its own copy and nobody else's,
    and two instances serving the same owner cannot hand each other a half
    written tree. Writes are last-writer-wins at tree granularity, which is
    honest for a single person editing their own skills and is stated here
    rather than discovered later.
    """

    def __init__(self, store, key_prefix: str = "skills"):
        self._store = store
        self._prefix = key_prefix.strip("/")

    def key_for(self, owner: str) -> str:
        return f"{self._prefix}/{owner_key(owner)}"

    @contextmanager
    def open(self, owner: Optional[str]) -> Iterator[Optional[Path]]:
        # No owner in a hosted deployment means no identity resolved this
        # request. There is no shared tree to fall back to — built-ins only.
        if owner is None:
            yield None
            return
        tmp = Path(tempfile.mkdtemp(prefix="sc-skills-"))
        try:
            self._store.get_tree(self.key_for(owner), str(tmp))
            yield tmp if any(tmp.iterdir()) else None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @contextmanager
    def edit(self, owner: Optional[str]) -> Iterator[Path]:
        if owner is None:
            raise PermissionError("A user skill needs an owner; this request has none.")
        tmp = Path(tempfile.mkdtemp(prefix="sc-skills-"))
        try:
            self._store.get_tree(self.key_for(owner), str(tmp))
            yield tmp
            # Push only on a clean exit: a failed edit leaves the stored tree
            # exactly as it was, so a rejected SKILL.md cannot half-land.
            self._store.put_tree(self.key_for(owner), str(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


_STORE = None


def default_local_base() -> Path:
    """``<data dir>/skills`` — beside state.db, outside the repo checkout.

    The data dir is what a self-host docker deploy already mounts as a volume,
    so a user's skills survive a container replacement for the same reason
    their sessions do.
    """
    explicit = os.environ.get("SILICONCREW_USER_SKILLS_DIR")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("RTL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".siliconcrew")
    return Path(data_dir) / "skills"


def get_user_skill_store():
    """The process-wide store, chosen ONCE from platform settings.

    The selector belongs in ``src/platform_engines/settings.py`` beside
    ``workspace_engine`` and ``templates_engine`` as a ``user_skills_engine``
    field; it is read here from ``hosted`` + one env override only because that
    file is owned by another change in flight. The shape is the same either
    way: config chooses an engine once, call sites see one interface.
    """
    global _STORE
    if _STORE is not None:
        return _STORE

    from src.platform_engines.settings import get_settings

    settings = get_settings()
    # The engine decision lives in settings with every other engine decision,
    # not here. Reading the env var directly put a sixth selection outside the
    # one place that owns them, which is how two of them drift apart.
    engine = settings.user_skills_engine

    if engine == "object":
        from src.platform_engines.workspace_provider import GcsObjectStore

        _STORE = ObjectUserSkillStore(
            GcsObjectStore(bucket=settings.workspace_bucket, prefix="user-skills")
        )
    else:
        _STORE = LocalUserSkillStore(default_local_base())
    return _STORE


def set_user_skill_store(store) -> None:
    """Override the process-wide store (tests / explicit wiring)."""
    global _STORE
    _STORE = store

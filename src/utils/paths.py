"""Path-containment guard shared by every workspace file handler.

One correct implementation of "does this resolved path stay inside this base
directory?" so the read endpoints, the write path, and uploads all enforce the
same tenant boundary.

A bare ``os.path.realpath(target).startswith(os.path.realpath(base))`` is subtly
wrong: it accepts a *sibling* whose name shares a prefix. With base
``/scratch/abc`` it would accept ``/scratch/abc-evil/secret`` — a cross-tenant
escape. The fix is to require an exact match or a real path separator boundary.
"""
from __future__ import annotations

import os


def is_within(base: str, target: str) -> bool:
    """True iff ``target`` resolves to ``base`` itself or a path strictly inside.

    Both paths are resolved with ``realpath`` (following symlinks and collapsing
    ``..``) before comparison, so traversal and symlink escapes are caught.
    """
    real_base = os.path.realpath(base)
    real_target = os.path.realpath(target)
    return real_target == real_base or real_target.startswith(real_base + os.sep)

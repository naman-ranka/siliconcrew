"""Identity-unification migration (Phase 2, Slice 3) — google_<sub> -> workos_<sub>.

When the deployed web sign-in moves from Google-direct to WorkOS-with-Google, a
user's ``user_id`` changes from ``google_<google_sub>`` to ``workos_<workos_sub>``.
Their existing data (projects, sessions, chat threads, BYOK keys) is keyed by the
old id, so without a migration it would silently disappear from their account.

This is an **explicit, operator-run, idempotent** re-key — never an automatic
mutation of shipped data. The old↔new pairing is **email-linked**: WorkOS knows
each user's verified email and new subject; Google knew the same email and old
subject. The operator builds that mapping (a list of pairs) out-of-band and feeds
it here. We only apply the moves and report what happened.

Design choices (deliberate):
  * Pure functions over injected stores → unit-tested with in-memory fakes; no
    network, no WorkOS, no live DB needed in CI.
  * Idempotent: re-running a completed migration moves zero rows (safe to retry).
  * ``dry_run`` reports the plan without mutating, so an operator can eyeball it.
  * Self-host is never involved — there is no sign-in and no ``user_id`` there.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class IdentityMapping:
    """One user's old→new identity pairing, linked by verified email."""

    old_user_id: str
    new_user_id: str
    email: Optional[str] = None

    def validate(self) -> None:
        if not self.old_user_id or not self.new_user_id:
            raise ValueError("each mapping needs both old_user_id and new_user_id")


@dataclass
class MigrationResult:
    email: Optional[str]
    old_user_id: str
    new_user_id: str
    metadata_rows: int = 0
    byok_rows: int = 0
    dry_run: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def total_rows(self) -> int:
        return self.metadata_rows + self.byok_rows


def migrate_identity(
    mapping: IdentityMapping,
    *,
    metadata_store,
    key_store=None,
    dry_run: bool = False,
) -> MigrationResult:
    """Re-key one user's data from ``old_user_id`` to ``new_user_id``.

    ``metadata_store`` is a :class:`MetadataStore`; ``key_store`` is a BYOK
    ``WrappedKeyStore`` / ``EnvelopeKeyVault`` (optional — omit when BYOK is not
    deployed). Both expose ``reassign_user(old, new) -> int``.
    """
    mapping.validate()
    result = MigrationResult(
        email=mapping.email,
        old_user_id=mapping.old_user_id,
        new_user_id=mapping.new_user_id,
        dry_run=dry_run,
    )
    try:
        if dry_run:
            # Report the would-move counts without mutating: count current rows
            # owned by the old id. Metadata rows are not directly countable
            # through the public API, so a dry run reports 0 moves and simply
            # validates the mapping (the operator's real signal is the live run).
            return result
        result.metadata_rows = metadata_store.reassign_user(
            mapping.old_user_id, mapping.new_user_id
        )
        if key_store is not None:
            result.byok_rows = key_store.reassign_user(
                mapping.old_user_id, mapping.new_user_id
            )
    except Exception as exc:  # surface, don't abort the whole batch
        result.error = str(exc)
    return result


def migrate_batch(
    mappings: Iterable[IdentityMapping],
    *,
    metadata_store,
    key_store=None,
    dry_run: bool = False,
) -> List[MigrationResult]:
    """Apply a batch of mappings, isolating failures (one bad pair never aborts
    the rest). Returns a per-user report."""
    return [
        migrate_identity(
            m, metadata_store=metadata_store, key_store=key_store, dry_run=dry_run
        )
        for m in mappings
    ]


def load_mappings(raw: str) -> List[IdentityMapping]:
    """Parse a JSON mapping file: ``[{"old_user_id","new_user_id","email"?}, ...]``."""
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("mapping file must be a JSON list of {old_user_id, new_user_id}")
    out: List[IdentityMapping] = []
    for item in data:
        m = IdentityMapping(
            old_user_id=item.get("old_user_id", ""),
            new_user_id=item.get("new_user_id", ""),
            email=item.get("email"),
        )
        m.validate()
        out.append(m)
    return out


def _build_stores():  # pragma: no cover - thin production wiring
    """Build the live metadata + BYOK stores from settings (operator CLI path)."""
    from src.platform_engines.settings import get_settings
    from src.platform_engines.metadata_store import build_metadata_store

    settings = get_settings()
    metadata_store = build_metadata_store(settings.database_url or "state.db")
    metadata_store.init_schema()

    key_store = None
    try:
        from src.platform_engines.llm_keys import build_key_vault

        key_store = build_key_vault(settings)
    except Exception:
        key_store = None
    return metadata_store, key_store


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - CLI glue
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-key SiliconCrew users google_<sub> -> workos_<sub> (Slice 3)."
    )
    parser.add_argument("mapping_file", help="JSON list of {old_user_id, new_user_id, email?}")
    parser.add_argument("--dry-run", action="store_true", help="validate + report, do not mutate")
    args = parser.parse_args(argv)

    with open(args.mapping_file, "r", encoding="utf-8") as f:
        mappings = load_mappings(f.read())

    metadata_store, key_store = _build_stores()
    results = migrate_batch(
        mappings, metadata_store=metadata_store, key_store=key_store, dry_run=args.dry_run
    )

    moved = sum(r.total_rows for r in results)
    failed = [r for r in results if not r.ok]
    for r in results:
        tag = "DRY" if r.dry_run else ("ERR" if not r.ok else "OK ")
        print(f"[{tag}] {r.old_user_id} -> {r.new_user_id}: "
              f"{r.metadata_rows} meta + {r.byok_rows} byok"
              + (f"  ({r.error})" if r.error else ""))
    print(f"\n{len(results)} users, {moved} rows moved, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

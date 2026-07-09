#!/usr/bin/env python
"""Author a template bundle from a live self-host session.

    python -m scripts.export_bundle <session_id> examples/<name> \
        --name "Sync FIFO" --description "..." --highlight "..." --highlight "..."

Copies the session workspace into ``examples/<name>/workspace/`` (guarded),
renders each chat thread to ``conversations/chat-N-<slug>.md`` from the local
LangGraph checkpoints (no LLM), sanitizes the author's identity out, and writes
a ``template.json`` scaffold. Secret-looking files are printed as WARNINGS — you
decide whether to keep them before committing the bundle.

Self-host only: transcripts read the local ``state.db`` checkpointer (hosted
checkpoints live in Cloud SQL). See src/utils/templates.py.
"""

import argparse
import os
import sys

from src.utils.session_manager import SessionManager
from src.utils.templates import export_session_bundle


def _default_db_path() -> str:
    data_dir = os.environ.get("RTL_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), ".siliconcrew"
    )
    return os.path.join(data_dir, "state.db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export a session as a template bundle.")
    parser.add_argument("session_id", help="Source session id (self-host).")
    parser.add_argument("out_dir", help="Bundle output dir, e.g. examples/sync_fifo")
    parser.add_argument("--name", default=None, help="Display name (defaults to the dir name).")
    parser.add_argument("--description", default="", help="One-line description for the card.")
    parser.add_argument(
        "--highlight",
        action="append",
        default=[],
        dest="highlights",
        help="A metric/outcome bullet (repeatable).",
    )
    parser.add_argument("--platform", default=None, help="ORFS platform (e.g. sky130hd).")
    parser.add_argument("--source-note", default=None, help="Provenance note for the card.")
    parser.add_argument(
        "--prune-pnr",
        action="store_true",
        help="Drop regenerable per-stage PnR checkpoints (*.odb, intermediate "
        "*.gds); keeps 6_final.gds + netlist + reports. Use for full-flow GDS bundles.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=os.environ.get("RTL_WORKSPACE")
        or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace"),
        help="Workspace root (defaults to ./workspace or $RTL_WORKSPACE).",
    )
    parser.add_argument("--db-path", default=_default_db_path(), help="state.db path for checkpoints.")
    args = parser.parse_args(argv)

    sm = SessionManager(base_dir=args.workspace_dir, db_path=args.db_path)
    result = export_session_bundle(
        sm,
        args.session_id,
        args.out_dir,
        db_path=args.db_path,
        name=args.name,
        description=args.description,
        highlights=args.highlights,
        platform=args.platform,
        source_note=args.source_note,
        prune_pnr_intermediates=args.prune_pnr,
    )

    print(f"Bundle written to: {result.template_dir}")
    print(f"  files copied:   {result.files}  ({result.bytes} bytes)")
    if result.pruned:
        print(f"  pruned:         {result.pruned} PnR intermediate file(s)")
    print(f"  conversations:  {', '.join(result.conversations) or '(none)'}")
    if result.secret_warnings:
        print("  SECRET WARNINGS (review before committing):", file=sys.stderr)
        for w in result.secret_warnings:
            print(f"    ! {w}", file=sys.stderr)
    print("Next: fill in template.json (description + highlights), then commit the bundle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

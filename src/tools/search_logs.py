import glob
import os
from typing import List, Optional

from src.tools.synthesis_manager import get_run_dir


def _collect_search_dirs(workspace_dir: str, run_id: Optional[str]) -> List[str]:
    if run_id:
        run_dir = get_run_dir(workspace_dir, run_id)
        if not run_dir:
            return []
        return [
            os.path.join(run_dir, "orfs_reports"),
            os.path.join(run_dir, "orfs_logs"),
            os.path.join(run_dir, "orfs_results"),
        ]

    # Backward-compatible default roots
    return [
        os.path.join(workspace_dir, "orfs_reports"),
        os.path.join(workspace_dir, "orfs_logs"),
        os.path.join(workspace_dir, "orfs_results"),
        os.path.join(workspace_dir, "synth_runs"),
    ]


def search_logs(query: str, workspace_dir: Optional[str] = None, run_id: Optional[str] = None) -> str:
    """
    Search for a keyword in synthesis logs and reports.

    Args:
        query: String query to search.
        workspace_dir: Session workspace path.
        run_id: Optional synthesis run id for deterministic search scope.
    """
    if workspace_dir is None:
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workspace"))

    search_dirs = _collect_search_dirs(workspace_dir, run_id)
    if not search_dirs:
        return f"Run '{run_id}' not found."

    files = []
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
        for ext in ["*.log", "*.rpt", "*.txt", "*.v", "*.json", "*.mk"]:
            files.extend(glob.glob(os.path.join(directory, "**", ext), recursive=True))

    if not files:
        return "No log files found to search."

    query_lower = query.lower()
    results = []

    for fpath in files:
        try:
            with open(fpath, "r", errors="ignore") as f:
                for line_no, line in enumerate(f, start=1):
                    if query_lower in line.lower():
                        rel_path = os.path.relpath(fpath, workspace_dir)
                        results.append(f"File: {rel_path} | Line {line_no}: {line.strip()}")
        except Exception:
            continue

    if not results:
        return f"No matches found for '{query}'."

    return "\n".join(results[:50])

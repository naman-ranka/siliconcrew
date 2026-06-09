from __future__ import annotations

from pathlib import Path
import subprocess


def repo_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    for p in (start, *start.parents):
        if (p / ".git").exists():
            return p.resolve()
    return start


def orchestrator_root(repo: Path | None = None) -> Path:
    return (repo or repo_root()) / "bench-orchestrator"


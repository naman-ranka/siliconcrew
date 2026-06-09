from __future__ import annotations

from pathlib import Path


def ensure_project(repo_root: Path, project_name: str | None, enabled: bool) -> str | None:
    if not enabled or not project_name:
        return None
    try:
        from src.utils.session_manager import SessionManager
    except Exception:
        return _slug(project_name)

    workspace_root = Path(__import__("os").environ.get("RTL_WORKSPACE") or repo_root / "workspace_new")
    db_path = Path.home() / ".siliconcrew" / "state.db"
    if not db_path.exists():
        db_path = repo_root / "state.db"
    manager = SessionManager(base_dir=str(workspace_root), db_path=str(db_path))
    slug = manager._slugify(project_name)
    if manager.get_project(slug):
        return slug
    try:
        return manager.create_project(project_name)["id"]
    except ValueError:
        return slug


def project_id_for_name(project_name: str | None, enabled: bool) -> str | None:
    if not enabled or not project_name:
        return None
    return _slug(project_name)


def _slug(value: str) -> str:
    safe = "".join(c for c in value if c.isalnum() or c in ("-", "_"))
    return safe.strip("-_") or "project"

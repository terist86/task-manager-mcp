"""Project-level CRUD operations and metadata management.

Handles project directory creation, ``project.json`` metadata I/O,
and project discovery.  Does **not** touch individual task files —
that is the job of :class:`~.task_manager.TaskManager`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import ProjectMetadata


_METADATA_FILENAME = "project.json"


class ProjectManager:
    """Manages project directories and their ``project.json`` metadata.

    Typical usage::

        pm = ProjectManager("projects")
        pm.create_project("my-app", path="/home/me/my-app", language="python")
        meta = pm.get_project("my-app")
    """

    def __init__(self, projects_dir: str = "projects") -> None:
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        path: str = "",
        language: str = "",
        build_system: str = "",
        description: str = "",
    ) -> ProjectMetadata:
        """Create ``projects/<name>/`` with ``project.json`` and an empty ``tasks/`` subdirectory.

        Returns the newly written :class:`ProjectMetadata`.
        Raises :class:`FileExistsError` if the project already exists.
        """
        proj_dir = self._get_project_dir(name)
        if proj_dir.exists():
            raise FileExistsError(f"Project '{name}' already exists at {proj_dir}")

        proj_dir.mkdir(parents=True)
        tasks_dir = proj_dir / "tasks"
        tasks_dir.mkdir()

        meta = ProjectMetadata(
            name=name,
            path=path,
            language=language,
            build_system=build_system,
            description=description,
        )
        self._write_metadata(meta)
        return meta

    def get_project(self, name: str) -> Optional[ProjectMetadata]:
        """Read ``project.json`` for *name*, or ``None`` if it doesn't exist."""
        if not self.project_exists(name):
            return None
        data = self._read_metadata(name)
        return ProjectMetadata.from_dict(data) if data else None

    def list_projects(self) -> List[ProjectMetadata]:
        """Discover all projects by scanning subdirectories for ``project.json``."""
        results: List[ProjectMetadata] = []
        if not self.projects_dir.is_dir():
            return results
        for sub in sorted(self.projects_dir.iterdir()):
            if sub.is_dir():
                mp = sub / _METADATA_FILENAME
                if mp.is_file():
                    try:
                        data = json.loads(mp.read_text(encoding="utf-8"))
                        results.append(ProjectMetadata.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        return results

    def update_project(self, name: str, **kwargs: Any) -> ProjectMetadata:
        """Update writable metadata fields on *name*.

        Accepted keyword arguments correspond to :class:`ProjectMetadata` fields
        (except ``name`` and ``created_at``).
        """
        meta = self.get_project(name)
        if meta is None:
            raise FileNotFoundError(f"Project '{name}' not found")

        # Whitelist settable fields
        settable = {"path", "language", "build_system", "description"}
        for key, value in kwargs.items():
            if key in settable:
                setattr(meta, key, value)
        meta.touch()
        self._write_metadata(meta)
        return meta

    def delete_project(self, name: str) -> bool:
        """Remove the entire ``projects/<name>/`` directory recursively.

        Returns ``True`` if deletion happened, ``False`` if the project didn't exist.
        """
        proj_dir = self._get_project_dir(name)
        if not proj_dir.is_dir():
            return False
        _rmtree(proj_dir)
        return True

    def project_exists(self, name: str) -> bool:
        """Check that ``projects/<name>/project.json`` exists."""
        return self._get_metadata_path(name).is_file()

    def get_tasks_dir(self, name: str) -> Path:
        """Return ``projects/<name>/tasks/`` (creates if missing)."""
        d = self._get_project_dir(name) / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_project_dir(self, name: str) -> Path:
        return self.projects_dir / name

    def _get_metadata_path(self, name: str) -> Path:
        return self._get_project_dir(name) / _METADATA_FILENAME

    def _read_metadata(self, name: str) -> Dict[str, Any]:
        mp = self._get_metadata_path(name)
        if not mp.is_file():
            return {}
        return json.loads(mp.read_text(encoding="utf-8"))

    def _write_metadata(self, meta: ProjectMetadata) -> None:
        mp = self._get_metadata_path(meta.name)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _rmtree(path: Path) -> None:
    """Safely remove a directory tree."""
    if not path.is_dir():
        return
    for child in sorted(path.iterdir()):
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    path.rmdir()

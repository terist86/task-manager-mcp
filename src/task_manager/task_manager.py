"""Per-project task CRUD operations.

Operates on individual ``T-XXX.md`` files within a single project's
``projects/<name>/tasks/`` directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from .schema import TaskData, Subtask
from .task_file import TaskFile


class TaskManager:
    """CRUD operations for tasks belonging to a single project.

    Typical usage::

        tm = TaskManager("my-app", projects_dir="projects")
        task = tm.create_task("Add login page", description="...", priority="P0")
        all_tasks = tm.list_tasks()
        next_up = tm.get_next_task()
    """

    def __init__(self, project_name: str, projects_dir: str = "projects") -> None:
        self.project_name = project_name
        base = Path(projects_dir)
        self.tasks_dir = base / project_name / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str = "",
        category: str = "",
        priority: str = "P2",
        subtasks: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        complexity: str = "",
        estimated_hours: int = 0,
    ) -> TaskData:
        """Create a new ``T-XXX.md`` file with an auto-assigned ID."""
        task_id = TaskFile.get_next_id(self.tasks_dir)
        task = TaskData(
            id=task_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            dependencies=dependencies or [],
            subtasks=[Subtask(title=s) for s in (subtasks or [])],
            complexity=complexity,
            estimated_hours=estimated_hours,
        )
        tf = TaskFile(self._task_path(task_id))
        tf.write(task)
        return task

    def get_task(self, task_id: str) -> Optional[TaskData]:
        """Read a single ``T-XXX.md`` file."""
        p = self._task_path(task_id)
        if not p.is_file():
            return None
        return TaskFile(p).read()

    def list_tasks(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[TaskData]:
        """List all tasks, optionally filtered by *status* or *category*."""
        results: List[TaskData] = []
        for p in sorted(self._all_task_files()):
            try:
                task = TaskFile(p).read()
            except Exception:
                continue
            if status is not None and task.status != status:
                continue
            if category is not None and task.category != category:
                continue
            results.append(task)
        return results

    def update_task(self, task_id: str, **updates: Any) -> Optional[TaskData]:
        """Update fields on *task_id*.  Reads, patches, writes back.

        Accepted keyword arguments are field names of :class:`TaskData`.
        """
        task = self.get_task(task_id)
        if task is None:
            return None

        for key, value in updates.items():
            if hasattr(task, key) and key not in ("id", "created_at"):
                setattr(task, key, value)

        TaskFile(self._task_path(task_id)).write(task)
        return task

    def update_subtask(
        self, task_id: str, subtask_title: str, status: str
    ) -> Optional[TaskData]:
        """Toggle a single subtask's status (``"todo"`` | ``"done"``)."""
        task = self.get_task(task_id)
        if task is None:
            return None
        found = False
        for st in task.subtasks:
            if st.title == subtask_title:
                st.status = status
                found = True
                break
        if not found:
            return None
        TaskFile(self._task_path(task_id)).write(task)
        return task

    def update_task_status(
        self, task_id: str, new_status: str
    ) -> Optional[TaskData]:
        """Shorthand to update only the ``status`` field."""
        return self.update_task(task_id, status=new_status)

    def delete_task(self, task_id: str) -> bool:
        """Remove a ``T-XXX.md`` file."""
        p = self._task_path(task_id)
        if p.is_file():
            p.unlink()
            return True
        return False

    def get_next_task(self) -> Optional[TaskData]:
        """Return the first task that is not ``Done``."""
        status_order = {"ToDo": 0, "Analyze": 1, "Implementation": 2, "In Review": 3, "Done": 4}
        active: List[TaskData] = []
        for task in self.list_tasks():
            if task.status != "Done":
                active.append(task)
        if not active:
            return None
        active.sort(key=lambda t: status_order.get(t.status, 99))
        return active[0]

    def get_dependent_tasks(self, task_id: str) -> List[TaskData]:
        """Return tasks that list *task_id* in their dependencies."""
        return [t for t in self.list_tasks() if task_id in t.dependencies]

    def get_task_count(self) -> int:
        """Return the number of ``T-*.md`` files in the project."""
        return len(self._all_task_files())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.md"

    def _all_task_files(self) -> List[Path]:
        if not self.tasks_dir.is_dir():
            return []
        return sorted(self.tasks_dir.glob("T-*.md"))

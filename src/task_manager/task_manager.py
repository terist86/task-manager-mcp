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
        """Shorthand to update only the ``status`` field.

        If *new_status* is ``"Done"`` and the task has a parent,
        automatically propagates the status check upward.
        """
        result = self.update_task(task_id, status=new_status)
        if result and new_status == "Done" and result.parent_task_id:
            self._propagate_to_parent(result.parent_task_id)
        return result

    # ------------------------------------------------------------------
    # Task expansion into separate files
    # ------------------------------------------------------------------

    def expand_to_files(
        self,
        parent_id: str,
        titles: List[str],
        mode: str = "parallel",
        descriptions: Optional[List[str]] = None,
    ) -> List[TaskData]:
        """Split *parent_id* into N child task files with auto-assigned IDs.

        Args:
            parent_id: The task to split (e.g. ``"T-001"``).
            titles: Titles for each child task.
            mode: ``"parallel"`` (all children depend on parent only)
                  or ``"chain"`` (sequential: T-003 → T-004 → T-005).
            descriptions: Optional descriptions for each child (same length as *titles*).

        Returns:
            List of created child :class:`TaskData`.

        Raises:
            ValueError: If parent task not found or mode is invalid.
        """
        parent = self.get_task(parent_id)
        if parent is None:
            raise ValueError(f"Parent task '{parent_id}' not found in '{self.project_name}'")
        if mode not in ("parallel", "chain"):
            raise ValueError(f"Invalid mode '{mode}'. Use 'parallel' or 'chain'.")
        if not titles:
            raise ValueError("At least one child title is required.")

        children: List[TaskData] = []
        child_ids: List[str] = []

        for idx, title in enumerate(titles):
            desc = descriptions[idx] if descriptions and idx < len(descriptions) else ""
            child = self.create_task(
                title=title,
                description=desc,
                priority=parent.priority,
                category=parent.category,
            )
            child.parent_task_id = parent_id

            if mode == "parallel":
                child.dependencies = [parent_id]
            elif mode == "chain":
                if idx == 0:
                    child.dependencies = [parent_id]
                else:
                    child.dependencies = [child_ids[-1]]

            self.update_task(child.id, parent_task_id=child.parent_task_id, dependencies=child.dependencies)
            children.append(child)
            child_ids.append(child.id)

        # Update parent with child references (extend, not replace)
        parent.child_task_ids.extend(child_ids)
        self.update_task(parent_id, child_task_ids=parent.child_task_ids)

        return children

    def _propagate_to_parent(self, parent_id: str) -> None:
        """Check if all children of *parent_id* are Done; if so, promote parent.

        Recurses upward through the hierarchy.
        """
        parent = self.get_task(parent_id)
        if parent is None or not parent.child_task_ids:
            return

        all_done = True
        for child_id in parent.child_task_ids:
            child = self.get_task(child_id)
            if child is None or child.status != "Done":
                all_done = False
                break

        if all_done and parent.status != "Done":
            self.update_task(parent_id, status="Done")
            if parent.parent_task_id:
                self._propagate_to_parent(parent.parent_task_id)

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

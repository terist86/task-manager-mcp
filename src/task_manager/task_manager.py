"""Per-project task CRUD operations.

Operates on individual ``T-XXX.md`` files within a single project's
``projects/<name>/tasks/`` directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from .schema import TaskData, Subtask, LogEntry
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

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "ToDo":          {"Analyze", "In Progress"},
        "In Progress":   {"Analyze", "Implementation", "In Review", "Done"},
        "Analyze":       {"Implementation"},
        "Implementation": {"In Review"},
        "In Review":     {"Done"},
        "Done":          set(),
        "Canceled":      set(),
    }

    def update_task_status(
        self, task_id: str, new_status: str, note: str = ""
    ) -> Optional[TaskData]:
        """Update task status with transition logging.

        Logs the old→new transition with timestamp and optional *note*.
        ``Canceled`` is a terminal status that allows a parent to become
        ``Done`` even though the child is not.

        If *new_status* is ``"Done"`` or ``"Canceled"`` and the task has
        a parent, automatically propagates the status check upward.
        """
        task = self.get_task(task_id)
        if task is None:
            return None

        old_status = task.status

        # No-op: same status
        if old_status == new_status:
            return task

        # Determine validation result
        allowed = self.VALID_TRANSITIONS.get(old_status, set())
        if new_status in allowed:
            result = "✅ PASS"
        elif new_status == "Canceled":
            result = "✅ PASS (canceled)"
        elif old_status == "In Review" and new_status == "Analyze":
            result = "✅ PASS (rejected)"
        else:
            result = "⚠️ UNKNOWN"

        # Append log entry
        from datetime import datetime, timezone
        task.log_entries.append(LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_status=old_status,
            to_status=new_status,
            note=note,
            validation_result=result,
        ))

        # Update status
        task.status = new_status
        TaskFile(self._task_path(task_id)).write(task)

        # Sync parent status based on all children
        if task.parent_task_id:
            self._sync_parent_status(task.parent_task_id)

        return task

    # ------------------------------------------------------------------
    # Parent status automation
    # ------------------------------------------------------------------

    def _sync_parent_status(self, parent_id: str) -> None:
        """Derive parent status from its children.

        Rules:
        - All children ToDo → parent = ToDo
        - Any child active (not Done/Canceled) → parent = In Progress
        - All children Done → parent = Done
        - All children Canceled → parent = Canceled
        - Mixed Done + Canceled, none active → parent = Done
        """
        parent = self.get_task(parent_id)
        if parent is None or not parent.child_task_ids:
            return

        statuses = set()
        for child_id in parent.child_task_ids:
            child = self.get_task(child_id)
            if child is None:
                continue
            statuses.add(child.status)

        # Determine target status
        if not statuses:
            return  # no children found
        if statuses == {"ToDo"}:
            target = "ToDo"
        elif statuses == {"Done"}:
            target = "Done"
        elif statuses == {"Canceled"}:
            target = "Canceled"
        elif statuses - {"Done", "Canceled"}:  # any active children
            target = "In Progress"
        else:  # mix of Done + Canceled only
            target = "Done"

        if parent.status != target:
            self.update_task_status(parent_id, target, note="Parent status synced from children")

        # Sync child statuses to parent Subtask checkboxes
        subtask_updated = False
        for child_id in parent.child_task_ids:
            child = self.get_task(child_id)
            if child is None:
                continue
            for st in parent.subtasks:
                if st.title.startswith(f"{child_id}:"):
                    mapped = "done" if child.status in ("Done", "Canceled") else "todo"
                    if st.status != mapped:
                        st.status = mapped
                        subtask_updated = True
                    break
        if subtask_updated:
            self.update_task(parent_id, subtasks=parent.subtasks)

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
            ValueError: If parent task not found, mode is invalid, or parent is Done/Canceled.
        """
        parent = self.get_task(parent_id)
        if parent is None:
            raise ValueError(f"Parent task '{parent_id}' not found in '{self.project_name}'")
        if parent.status in ("Done", "Canceled"):
            raise ValueError(f"Cannot expand '{parent_id}' — task is {parent.status}")
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
        # Add Subtask entries referencing child tasks
        for child in children:
            parent.subtasks.append(Subtask(
                title=f"{child.id}: {child.title}",
                status="todo"  # all children start at ToDo
            ))
        self.update_task(parent_id, child_task_ids=parent.child_task_ids, subtasks=parent.subtasks)

        # Sync parent status (children just created → all ToDo → parent stays ToDo)
        self._sync_parent_status(parent_id)

        return children

    def delete_task(self, task_id: str) -> bool:
        """Remove a ``T-XXX.md`` file."""
        p = self._task_path(task_id)
        if p.is_file():
            p.unlink()
            return True
        return False

    def get_next_task(self) -> Optional[TaskData]:
        """Return the first task that is not ``Done`` or ``Canceled``."""
        status_order = {"ToDo": 0, "In Progress": 1, "Analyze": 2, "Implementation": 3, "In Review": 4, "Done": 5, "Canceled": 6}
        active: List[TaskData] = []
        for task in self.list_tasks():
            if task.status not in ("Done", "Canceled"):
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

"""Migration tool: converts old ``tasks/*.md`` flat files to the new
``projects/<name>/`` directory-based structure.

Usage:
    tool = MigrationTool(old_tasks_dir="tasks", new_projects_dir="projects")
    result = tool.migrate()
    print(result)  # {"migrated": [...], "skipped": [...], "errors": [...]}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import TaskData, Subtask
from .task_file import TaskFile
from .project_manager import ProjectManager


class MigrationTool:
    """One-shot converter from the old flat-file format to the new directory tree."""

    def __init__(
        self,
        old_tasks_dir: str = "tasks",
        new_projects_dir: str = "projects",
    ) -> None:
        self.old_dir = Path(old_tasks_dir)
        self.new_dir = Path(new_projects_dir)
        self.pm = ProjectManager(str(new_projects_dir))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def migrate(self, delete_old: bool = False) -> Dict[str, Any]:
        """Run a full migration of every ``*.md`` file in *old_tasks_dir*.

        Returns a summary dict::

            {
                "migrated": ["project-a", "project-b"],
                "skipped": [],
                "errors": {"broken-project": "error message"},
                "task_count": 12,
            }
        """
        summary: Dict[str, Any] = {
            "migrated": [],
            "skipped": [],
            "errors": {},
            "task_count": 0,
        }

        if not self.old_dir.is_dir():
            summary["errors"]["<global>"] = f"Old tasks directory '{self.old_dir}' not found"
            return summary

        for md_file in sorted(self.old_dir.glob("*.md")):
            project_name = md_file.stem
            try:
                tasks = self._parse_old_format(md_file)
                if not tasks:
                    summary["skipped"].append(project_name)
                    continue

                # Create / update project
                if not self.pm.project_exists(project_name):
                    self.pm.create_project(
                        project_name,
                        description=f"Migrated from {md_file}",
                    )

                tasks_dir = self.pm.get_tasks_dir(project_name)
                for task_data in tasks:
                    task_id = TaskFile.get_next_id(tasks_dir)
                    task_data.id = task_id
                    tf = TaskFile(tasks_dir / f"{task_id}.md")
                    tf.write(task_data)
                    summary["task_count"] += 1

                summary["migrated"].append(project_name)

                if delete_old:
                    md_file.unlink()

            except Exception as exc:
                summary["errors"][project_name] = str(exc)

        return summary

    def migrate_project(self, project_name: str, delete_old: bool = False) -> bool:
        """Migrate a single project's old file."""
        md_file = self.old_dir / f"{project_name}.md"
        if not md_file.is_file():
            return False

        tasks = self._parse_old_format(md_file)
        if not tasks:
            return False

        if not self.pm.project_exists(project_name):
            self.pm.create_project(project_name, description=f"Migrated from {md_file}")

        tasks_dir = self.pm.get_tasks_dir(project_name)
        for task_data in tasks:
            task_id = TaskFile.get_next_id(tasks_dir)
            task_data.id = task_id
            tf = TaskFile(tasks_dir / f"{task_id}.md")
            tf.write(task_data)

        if delete_old:
            md_file.unlink()

        return True

    def verify_migration(self) -> Dict[str, Any]:
        """Compare old and new data to verify migration completeness."""
        report: Dict[str, Any] = {"match": [], "mismatch": {}, "missing": []}

        if not self.old_dir.is_dir():
            report["<error>"] = "Old tasks directory missing"
        return report

    # ------------------------------------------------------------------
    # .md → .json migration
    # ------------------------------------------------------------------

    def migrate_md_to_json(self, project_name: str) -> dict:
        """Convert all T-XXX.md files in a project to T-XXX.json."""
        tasks_dir = self.pm.get_tasks_dir(project_name)
        converted = 0
        skipped = 0

        for md_file in sorted(tasks_dir.glob("T-*.md")):
            json_file = md_file.with_suffix(".json")
            if json_file.exists():
                skipped += 1
                continue
            try:
                task = self._parse_task_template_md(md_file)
                if task:
                    from .task_file import TaskFile
                    TaskFile(json_file).write(task)
                    converted += 1
            except Exception:
                skipped += 1

        return {"converted": converted, "skipped": skipped}

    def _parse_task_template_md(self, filepath: Path) -> Optional[TaskData]:
        """Parse a T-XXX.md file in Task File Template format into TaskData."""
        import re
        content = filepath.read_text(encoding="utf-8")
        task = TaskData()

        # Parse title: # T-001: Title
        m = re.match(r"^#\s+(T-\d+):\s*(.+)", content.split("\n")[0] if content else "")
        if m:
            task.id = m.group(1)
            task.title = m.group(2).strip()

        # Parse metadata (colon is INSIDE bold: **Key:** value)
        for m in re.finditer(r"^-\s+\*\*(.+?)\*\*\s*(.+)", content, re.MULTILINE):
            key = m.group(1).strip().rstrip(":").strip().lower()
            val = m.group(2).strip()
            if key == "priority": task.priority = val
            elif key == "category": task.category = val
            elif key == "dependencies": task.dependencies = [d.strip() for d in val.split(",") if d.strip()]
            elif key == "parent task": task.parent_task_id = val
            elif key == "child tasks": task.child_task_ids = [d.strip() for d in val.split(",") if d.strip()]
            elif key == "complexity": task.complexity = val
            elif key == "estimated hours": task.estimated_hours = int(val.split()[0]) if val else 0

        # Parse status
        m = re.search(r"^##\s+Status:\s*(.+)", content, re.MULTILINE)
        if m:
            task.status = m.group(1).strip()

        # Parse description
        m = re.search(r"^##\s+Description\n(.+?)(?=\n##|\Z)", content, re.MULTILINE | re.DOTALL)
        if m:
            task.description = m.group(1).strip()

        return task

        for md_file in sorted(self.old_dir.glob("*.md")):
            project_name = md_file.stem
            old_tasks = self._parse_old_format(md_file)

            if not self.pm.project_exists(project_name):
                report["missing"].append(project_name)
                continue

            # Count tasks in new format
            tasks_dir = self.pm.get_tasks_dir(project_name)
            new_count = len(list(tasks_dir.glob("T-*.md"))) if tasks_dir.is_dir() else 0

            if new_count == len(old_tasks):
                report["match"].append(project_name)
            else:
                report["mismatch"][project_name] = f"old={len(old_tasks)} new={new_count}"

        return report

    # ------------------------------------------------------------------
    # Parsing helpers (old format)
    # ------------------------------------------------------------------

    _RE_OLD_TASK = re.compile(r"^##\s+Task\s+\d*:\s*(.+)$")
    _RE_OLD_SUBTASK = re.compile(r"^-\s+\[(.)\]\s+(.+)$")

    def _parse_old_format(self, filepath: Path) -> List[TaskData]:
        """Parse an old-style ``tasks/<name>.md`` file into :class:`TaskData` objects.

        The old format uses::

            ## Task N: [category] Title (priority)
            description text...
            ### Subtasks:
            - [x] subtask title
        """
        content = filepath.read_text(encoding="utf-8")
        tasks: List[TaskData] = []
        current: Optional[TaskData] = None
        description_lines: List[str] = []
        in_subtasks = False

        for raw in content.split("\n"):
            line = raw.strip()

            # New task header
            m = self._RE_OLD_TASK.match(line)
            if m:
                if current is not None:
                    current.description = "\n".join(description_lines).strip()
                    tasks.append(current)
                current = TaskData(title=m.group(1).strip())
                # Try to extract category [TAG] and priority (PX)
                title_text = m.group(1)
                cat_m = re.match(r"^\[([A-Z]+)\]\s+(.*?)\s*\(P(\d)\)$", title_text)
                if cat_m:
                    current.category = f"[{cat_m.group(1)}]"
                    current.title = cat_m.group(2).strip()
                    current.priority = f"P{cat_m.group(3)}"
                description_lines = []
                in_subtasks = False
                continue

            # Subtask section start
            if re.match(r"^###\s+Subtasks", line):
                in_subtasks = True
                continue

            # Subtask checkbox
            m = self._RE_OLD_SUBTASK.match(line)
            if m and in_subtasks and current is not None:
                checked = m.group(1) in ("x", "X")
                current.subtasks.append(Subtask(
                    title=m.group(2).strip(),
                    status="done" if checked else "todo",
                ))
                continue

            # Separator or empty — stop description
            if line.startswith("---"):
                in_subtasks = False
                continue

            # Description line
            if current is not None and not in_subtasks and line and not line.startswith("#"):
                description_lines.append(line)

        # Flush last task
        if current is not None:
            current.description = "\n".join(description_lines).strip()
            tasks.append(current)

        return tasks

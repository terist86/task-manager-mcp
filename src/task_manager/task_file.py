"""Reader / writer for individual ``T-XXX.json`` task files.

Primary storage is JSON for AI agent consumption. Markdown generation
is preserved as an export-only feature via :meth:`TaskFile.to_markdown`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .schema import TaskData, Subtask, CriteriaBlock


class TaskFile:
    """Wraps a single ``T-XXX.json`` task file on disk."""

    def __init__(self, filepath: Path) -> None:
        self._path = Path(filepath)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> TaskData:
        """Read and parse a ``T-XXX.json`` file into a :class:`TaskData` object."""
        if not self._path.is_file():
            return TaskData()
        raw = self._path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return TaskData()
        return TaskData.from_dict(data)

    def write(self, task: TaskData) -> None:
        """Serialize *task* to JSON and write to disk.

        Automatically calls :meth:`TaskData.touch` to refresh the timestamp.
        """
        task.touch()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self) -> bool:
        """Remove the task file from disk. Returns ``False`` if it did not exist."""
        if self._path.exists():
            self._path.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_next_id(tasks_dir: str | Path) -> str:
        """Scan *tasks_dir* for ``T-NNN.json`` files and return the next available ID."""
        tasks_dir = Path(tasks_dir)
        max_num = 0
        if tasks_dir.is_dir():
            for p in tasks_dir.glob("T-*.json"):
                try:
                    num = int(p.stem.split("-", 1)[-1])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        # Also check .md files (migration coexistence)
        if tasks_dir.is_dir():
            for p in tasks_dir.glob("T-*.md"):
                try:
                    num = int(p.stem.split("-", 1)[-1])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        return f"T-{max_num + 1:03d}"

    # ------------------------------------------------------------------
    # Markdown export (human-readable, not used for storage)
    # ------------------------------------------------------------------

    @staticmethod
    def to_markdown(task: TaskData) -> str:
        """Generate a human-readable markdown representation of *task*.

        This is NOT used for storage — only for export/generation.
        The primary storage format is JSON.
        """
        lines: list[str] = []

        # Title
        lines.append(f"# {task.id}: {task.title}" if task.id else f"# {task.title}")
        lines.append("")

        # Metadata
        lines.append("## Metadata")
        if task.id:
            lines.append(f"- **ID:** {task.id}")
        if task.phase:
            lines.append(f"- **Phase:** {task.phase}")
        if task.category:
            lines.append(f"- **Category:** {task.category}")
        if task.priority:
            lines.append(f"- **Priority:** {task.priority}")
        if task.dependencies:
            lines.append(f"- **Dependencies:** {', '.join(task.dependencies)}")
        if task.parent_task_id:
            lines.append(f"- **Parent Task:** {task.parent_task_id}")
        if task.child_task_ids:
            lines.append(f"- **Child Tasks:** {', '.join(task.child_task_ids)}")
        if task.complexity:
            lines.append(f"- **Complexity:** {task.complexity}")
        if task.estimated_hours:
            lines.append(f"- **Estimate:** {task.estimated_hours} hours")
        lines.append(f"- **Created:** {task.created_at}")
        lines.append(f"- **Updated:** {task.updated_at}")
        lines.append("")

        # Status
        lines.append(f"## Status: {task.status}")
        lines.append("")

        # Log
        if task.log_entries:
            lines.append("## Log")
            for entry in task.log_entries:
                suffix = ""
                if entry.from_status == "In Review" and entry.to_status == "Analyze":
                    suffix = " (rejected)"
                lines.append(f"### {entry.timestamp[:10]} — {entry.from_status} → {entry.to_status}{suffix}")
                if entry.validation_result:
                    lines.append(f"- Transition validation: {entry.validation_result}")
                if entry.note:
                    for note_line in entry.note.split("\n"):
                        lines.append(f"- {note_line}")
            lines.append("")

        # Description
        if task.description.strip():
            lines.append("## Description")
            lines.append(task.description.strip())
            lines.append("")

        # Phase blocks
        for phase_name, phase_key in [("Analyze", "analyze"), ("Implementation", "implementation"),
                                        ("In Review", "in_review"), ("Done", "done")]:
            block = getattr(task, phase_key, None)
            if block:
                lines.append(f"## {phase_name}")
                if block.input_criteria:
                    lines.append("### Input Criteria")
                    for c in block.input_criteria:
                        lines.append(f"- [ ] {c}")
                if block.output_criteria:
                    lines.append("### Output Criteria (-> ...)")
                    for c in block.output_criteria:
                        lines.append(f"- [ ] {c}")
                if block.findings:
                    lines.append(block.findings.strip())
                lines.append("")

        # Subtasks
        if task.subtasks:
            lines.append("### Subtasks")
            for st in task.subtasks:
                mark = "x" if st.status == "done" else " "
                lines.append(f"- [{mark}] {st.title}")
            lines.append("")

        return "\n".join(lines) + "\n"

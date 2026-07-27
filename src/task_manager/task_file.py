"""Reader / writer for individual ``T-XXX.md`` task files.

Every task file follows the Task File Template specification:

.. code-block:: markdown

    # T-001: Task Title

    ## Metadata
    - **ID:** T-001
    - **Phase:** 1
    - **Dependencies:** T-002, T-003
    ...

    ## Status: ToDo | Analyze | Implementation | In Review | Done

    ## Analyze
    ### Input Criteria
    - [ ] ...
    ### Output Criteria (-> Implementation)
    - [ ] ...

    ## Implementation
    ...

    ## Done
    - [ ] Task completed
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .schema import TaskData, Subtask, CriteriaBlock, LogEntry


# ---------------------------------------------------------------------------
# Constants – regex patterns used during parsing
# ---------------------------------------------------------------------------

_RE_HEADER = re.compile(r"^#\s+(T-\d{3,}):\s*(.*)$")
_RE_META_LINE = re.compile(r"^-\s+\*\*(.+?)\*\*\s*(.*)$")
_RE_STATUS = re.compile(r"^##\s+Status:\s*(.+)$")
_RE_SECTION = re.compile(r"^##\s+(Analyze|Implementation|In Review|Done)$", re.IGNORECASE)
_RE_INPUT = re.compile(r"^###\s+Input Criteria$", re.IGNORECASE)
_RE_OUTPUT = re.compile(r"^###\s+Output Criteria.*$", re.IGNORECASE)
_RE_CHECKBOX = re.compile(r"^-\s+\[(.)\]\s+(.+)$")
_RE_DESC_START = re.compile(r"^##\s+Description$", re.IGNORECASE)
_RE_LOG_START = re.compile(r"^##\s+Log$", re.IGNORECASE)
_RE_LOG_ENTRY = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(.+?)\s*→\s*(.+)$")
_RE_SUBTASK_START = re.compile(r"^###\s+Subtasks", re.IGNORECASE)

_META_KEY_MAP: dict[str, str] = {
    "id":            "id",
    "phase":         "phase",
    "dependencies":  "dependencies",
    "parent task":   "parent_task_id",
    "child tasks":   "child_task_ids",
    "estimate":      "estimated_hours",
    "category":      "category",
    "priority":      "priority",
    "complexity":    "complexity",
    "estimated hours": "estimated_hours",
    "created":       "created_at",
    "updated":       "updated_at",
}


class TaskFile:
    """Wraps a single ``T-XXX.md`` task file on disk."""

    def __init__(self, filepath: Path) -> None:
        self._path = Path(filepath)
        self._text: Optional[str] = None  # cached raw content

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> TaskData:
        """Parse the markdown file and return a :class:`TaskData` object."""
        if self._text is None or not self._path.exists():
            raw = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
            self._text = raw
        else:
            raw = self._text
        return self.parse_markdown(raw)

    def write(self, task: TaskData) -> None:
        """Serialize *task* to markdown and write to disk.

        Automatically calls :meth:`TaskData.touch` to refresh the timestamp.
        """
        task.touch()
        markdown = self.generate_markdown(task)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(markdown, encoding="utf-8")
        self._text = markdown

    def delete(self) -> bool:
        """Remove the task file from disk.  Returns ``False`` if it did not exist."""
        if self._path.exists():
            self._path.unlink()
            self._text = None
            return True
        return False

    def rename(self, new_id: str) -> None:
        """Move the file to a new ``T-XXX.md`` path.

        .. warning:: Does **not** update the internal ``TaskData.id``.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"{self._path} does not exist")
        new_path = self._path.with_name(f"{new_id}.md")
        self._path.rename(new_path)
        self._path = new_path

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_next_id(tasks_dir: str | Path) -> str:
        """Scan *tasks_dir* for ``T-NNN.md`` files and return the next available ID."""
        tasks_dir = Path(tasks_dir)
        max_num = 0
        if tasks_dir.is_dir():
            for p in tasks_dir.glob("T-*.md"):
                # Try extracting number from filename first (most reliable)
                name = p.stem  # "T-001" -> extract "001"
                try:
                    num = int(name.split("-", 1)[-1])
                    if num > max_num:
                        max_num = num
                    continue
                except ValueError:
                    pass
                # Fallback: read header from file content
                if p.stat().st_size > 0:
                    header = p.read_text(encoding="utf-8").split("\n", 1)[0]
                    m = _RE_HEADER.match(header)
                    if m:
                        try:
                            num = int(m.group(1).split("-", 1)[-1])
                            if num > max_num:
                                max_num = num
                        except (ValueError, IndexError):
                            pass
        return f"T-{max_num + 1:03d}"

    @staticmethod
    def generate_markdown(task: TaskData) -> str:
        """Render a :class:`TaskData` into the ``T-XXX.md`` template format."""
        lines: list[str] = []

        # Title line
        lines.append(f"# {task.id}: {task.title}" if task.id else f"# {task.title}")
        lines.append("")

        # Metadata block
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
            deps = ", ".join(task.dependencies)
            lines.append(f"- **Dependencies:** {deps}")
        if task.parent_task_id:
            lines.append(f"- **Parent Task:** {task.parent_task_id}")
        if task.child_task_ids:
            children = ", ".join(task.child_task_ids)
            lines.append(f"- **Child Tasks:** {children}")
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

        # Log (transition history)
        if task.log_entries:
            lines.append("## Log")
            for entry in task.log_entries:
                suffix = ""
                if entry.from_status == "In Review" and entry.to_status == "Implementation":
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
        if task.analyze:
            lines.append("## Analyze")
            lines.extend(TaskFile._format_criteria_block(task.analyze))
            lines.append("")
        if task.implementation:
            lines.append("## Implementation")
            lines.extend(TaskFile._format_criteria_block(task.implementation))
            lines.append("")
        if task.in_review:
            lines.append("## In Review")
            lines.extend(TaskFile._format_criteria_block(task.in_review))
            lines.append("")
        if task.done:
            lines.append("## Done")
            lines.extend(TaskFile._format_criteria_block(task.done))
            lines.append("")

        # Subtasks
        if task.subtasks:
            lines.append("### Subtasks")
            for st in task.subtasks:
                mark = "x" if st.status == "done" else " "
                lines.append(f"- [{mark}] {st.title}")
            lines.append("")

        return "\n".join(lines) + "\n"

    @staticmethod
    def parse_markdown(content: str) -> TaskData:
        """Parse a ``T-XXX.md`` file content into a :class:`TaskData` object."""
        task = TaskData()
        if not content.strip():
            return task

        lines = content.split("\n")

        # State machine
        current_section: Optional[str] = None      # "analyze", "implementation", ...
        current_block: Optional[str] = None         # "input" or "output"
        current_criteria: list[str] = []
        in_description = False
        in_subtasks = False
        in_log = False
        description_lines: list[str] = []
        current_log_entry: Optional[LogEntry] = None
        log_note_lines: list[str] = []

        for line in lines:
            # Match title header: # T-001: Title
            m = _RE_HEADER.match(line)
            if m:
                task.id = m.group(1)
                task.title = m.group(2).strip()
                continue

            # Metadata inline: - **Key:** Value
            m = _RE_META_LINE.match(line)
            if m and current_section is None and not in_description and not in_subtasks:
                key, value = m.group(1).strip().lower(), m.group(2).strip()
                _set_meta(task, key, value)
                continue

            # ## Status: ...
            m = _RE_STATUS.match(line)
            if m:
                task.status = m.group(1).strip()
                continue

            # ## Description section
            if _RE_DESC_START.match(line):
                _flush_log(task, current_log_entry, log_note_lines)
                current_log_entry = None
                log_note_lines = []
                current_section = None
                current_block = None
                in_description = True
                in_subtasks = False
                in_log = False
                continue

            # ## Subtasks section
            if _RE_SUBTASK_START.match(line):
                _flush_log(task, current_log_entry, log_note_lines)
                current_log_entry = None
                log_note_lines = []
                in_description = False
                in_subtasks = True
                in_log = False
                current_section = None
                current_block = None
                continue

            # ## Log section
            if _RE_LOG_START.match(line):
                in_description = False
                in_subtasks = False
                in_log = True
                current_section = None
                current_block = None
                continue

            # ### YYYY-MM-DD — From → To (log entry header)
            m = _RE_LOG_ENTRY.match(line)
            if m and in_log:
                # Flush previous entry
                if current_log_entry is not None:
                    current_log_entry.note = "\n".join(log_note_lines).strip()
                    task.log_entries.append(current_log_entry)
                current_log_entry = LogEntry(
                    timestamp=m.group(1).strip(),
                    from_status=m.group(2).strip(),
                    to_status=m.group(3).strip().replace(" (rejected)", ""),
                )
                log_note_lines = []
                continue

            # - Note: ... or - Transition validation: ... inside log entry
            if in_log and current_log_entry is not None and line.strip().startswith("- "):
                text = line.strip()[2:].strip()
                if text.lower().startswith("transition validation:"):
                    current_log_entry.validation_result = text.split(":", 1)[1].strip()
                else:
                    log_note_lines.append(text)
                continue

            # ## Analyze / Implementation / In Review / Done
            m = _RE_SECTION.match(line)
            if m:
                # Flush previous criteria
                _flush_criteria(task, current_section, current_block, current_criteria)
                _flush_log(task, current_log_entry, log_note_lines)
                current_log_entry = None
                log_note_lines = []
                current_section = m.group(1).lower().replace(" ", "_")
                current_block = None
                current_criteria = []
                in_description = False
                in_subtasks = False
                in_log = False
                continue

            # ### Input Criteria / ### Output Criteria
            if current_section:
                if _RE_INPUT.match(line):
                    # Flush previous if any
                    _flush_criteria(task, current_section, current_block, current_criteria)
                    current_block = "input"
                    current_criteria = []
                    continue
                if _RE_OUTPUT.match(line):
                    _flush_criteria(task, current_section, current_block, current_criteria)
                    current_block = "output"
                    current_criteria = []
                    continue

            # Checkbox lines
            m = _RE_CHECKBOX.match(line)
            if m:
                checked = m.group(1) in ("x", "X")
                text = m.group(2).strip()
                if in_subtasks:
                    task.subtasks.append(Subtask(title=text, status="done" if checked else "todo"))
                elif current_section and current_block:
                    current_criteria.append(text)
                continue

            # Description lines (everything else between ## Description and next ##)
            if in_description and not in_subtasks and not line.startswith("#"):
                if line.strip():
                    description_lines.append(line.strip())
                continue

        # Flush remaining
        _flush_criteria(task, current_section, current_block, current_criteria)

        if current_log_entry is not None:
            current_log_entry.note = "\n".join(log_note_lines).strip()
            task.log_entries.append(current_log_entry)

        if description_lines:
            task.description = "\n".join(description_lines).strip()

        return task

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_criteria_block(block: CriteriaBlock) -> list[str]:
        result: list[str] = []
        if block.input_criteria:
            result.append("### Input Criteria")
            for c in block.input_criteria:
                result.append(f"- [ ] {c}")
        if block.output_criteria:
            result.append("### Output Criteria (-> ...)")
            for c in block.output_criteria:
                result.append(f"- [ ] {c}")
        return result


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _set_meta(task: TaskData, key: str, value: str) -> None:
    """Apply a parsed metadata field to *task*."""
    # Strip trailing colon that is part of the bold markdown (e.g. "**ID:**")
    key = key.strip().rstrip(":").strip().lower()
    mapped = _META_KEY_MAP.get(key, key)
    if mapped == "dependencies":
        task.dependencies = [d.strip() for d in value.split(",") if d.strip()]
    elif mapped == "child_task_ids":
        task.child_task_ids = [d.strip() for d in value.split(",") if d.strip()]
    elif mapped == "estimated_hours":
        try:
            # Accept both "4 hours" format and integer
            task.estimated_hours = int(value.split()[0]) if value else 0
        except (ValueError, IndexError):
            task.estimated_hours = 0
    elif mapped == "complexity":
        task.complexity = value
    elif hasattr(task, mapped):
        setattr(task, mapped, value)


def _flush_criteria(
    task: TaskData,
    section: Optional[str],
    block: Optional[str],
    criteria: list[str],
) -> None:
    """Persist collected criteria lines into the right block on *task*."""
    if not section or not block or not criteria:
        return

    # Lazily create CriteriaBlock
    attr_name = section
    existing: Optional[CriteriaBlock] = getattr(task, attr_name, None)
    if existing is None:
        existing = CriteriaBlock()

    if block == "input":
        existing.input_criteria.extend(criteria)
    elif block == "output":
        existing.output_criteria.extend(criteria)

    setattr(task, attr_name, existing)


def _flush_log(
    task: TaskData,
    entry: Optional[LogEntry],
    note_lines: list[str],
) -> None:
    """Persist a pending log entry into *task*."""
    if entry is not None:
        entry.note = "\n".join(note_lines).strip()
        task.log_entries.append(entry)

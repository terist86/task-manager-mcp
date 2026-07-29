"""Data models for the task-manager package.

Defines ProjectMetadata for project-level details and TaskData for
individual task files, plus supporting types (Subtask, CriteriaBlock).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------

@dataclass
class ProjectMetadata:
    """Stored as ``project.json`` inside each project directory."""

    name: str
    path: str = ""
    language: str = ""
    build_system: str = ""
    description: str = ""
    git_repository: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def touch(self) -> None:
        """Update ``updated_at`` to now."""
        self.updated_at = _now_iso()


# ---------------------------------------------------------------------------
# Subtask
# ---------------------------------------------------------------------------

@dataclass
class Subtask:
    """A single subtask, tracked with a checkbox."""
    title: str
    status: str = "todo"  # "todo" | "done"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subtask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Criteria blocks (for Analyze / Implementation / In Review sections)
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A single transition log entry (stored in the ``## Log`` section)."""

    timestamp: str = field(default_factory=_now_iso)
    from_status: str = ""
    to_status: str = ""
    note: str = ""
    validation_result: str = "✅ PASS"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Criteria blocks (for Analyze / Implementation / In Review sections)
# ---------------------------------------------------------------------------

@dataclass
class CriteriaBlock:
    """Checklist block for a phase section."""
    input_criteria: List[str] = field(default_factory=list)
    output_criteria: List[str] = field(default_factory=list)
    findings: str = ""  # Analysis summary, implementation notes, review findings

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriteriaBlock":
        return cls(
            input_criteria=data.get("input_criteria", []),
            output_criteria=data.get("output_criteria", []),
            findings=data.get("findings", ""),
        )


# ---------------------------------------------------------------------------
# Task data (mapped to a single T-XXX.md file)
# ---------------------------------------------------------------------------

@dataclass
class TaskData:
    """Full representation of a single ``T-XXX.md`` task file.

    Compatible with the Task File Template specification.
    """

    id: str = ""  # e.g. "T-001"
    title: str = ""
    description: str = ""
    category: str = ""
    priority: str = "P2"
    dependencies: List[str] = field(default_factory=list)
    complexity: str = ""
    estimated_hours: int = 0
    phase: str = ""  # Phase number or name (optional, from template)
    status: str = "ToDo"  # ToDo | In Progress | Analyze | Implementation | In Review | Done | Canceled
    subtasks: List[Subtask] = field(default_factory=list)

    # Parent-child task references (for expand_task file-mode)
    parent_task_id: Optional[str] = None  # e.g. "T-001"
    child_task_ids: List[str] = field(default_factory=list)  # e.g. ["T-003", "T-004"]

    # Per-phase criteria blocks
    analyze: Optional[CriteriaBlock] = None
    implementation: Optional[CriteriaBlock] = None
    in_review: Optional[CriteriaBlock] = None
    done: Optional[CriteriaBlock] = None

    # Timestamps
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # Transition log
    log_entries: List[LogEntry] = field(default_factory=list)

    # Helpers -----------------------------------------------------------

    STATUS_ORDER: Dict[str, int] = field(default_factory=lambda: {
        "ToDo": 0,
        "In Progress": 1,
        "Analyze": 2,
        "Implementation": 3,
        "In Review": 4,
        "Done": 5,
        "Canceled": 6,
    }, repr=False, compare=False)

    @property
    def status_order(self) -> int:
        return self.STATUS_ORDER.get(self.status, -1)

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Remove STATUS_ORDER from serialisation output
        data.pop("STATUS_ORDER", None)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskData":
        # Handle nested objects
        kwargs: Dict[str, Any] = {}
        field_names = {f.name for f in cls.__dataclass_fields__.values()}

        for key, value in data.items():
            if key not in field_names:
                continue
            if key == "subtasks" and isinstance(value, list):
                kwargs[key] = [Subtask.from_dict(s) for s in value]
            elif key == "log_entries" and isinstance(value, list):
                kwargs[key] = [LogEntry.from_dict(e) for e in value]
            elif key in ("analyze", "implementation", "in_review", "done"):
                kwargs[key] = CriteriaBlock.from_dict(value) if isinstance(value, dict) else value
            else:
                kwargs[key] = value

        return cls(**kwargs)

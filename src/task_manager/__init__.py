"""Task Manager — multi-project directory-based task storage for MCP."""

from .schema import ProjectMetadata, TaskData, Subtask, CriteriaBlock
from .task_file import TaskFile
from .project_manager import ProjectManager
from .task_manager import TaskManager
from .migration import MigrationTool

__all__ = [
    "ProjectMetadata",
    "TaskData",
    "Subtask",
    "CriteriaBlock",
    "TaskFile",
    "ProjectManager",
    "TaskManager",
    "MigrationTool",
]
